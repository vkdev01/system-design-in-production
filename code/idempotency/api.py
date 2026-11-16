"""Chapter 04: the endpoint, with the phase boundary respected.

No database transaction is held across gateway.charge(), and the response is
persisted before it is returned, so a retry replays instead of recharging.
"""

from __future__ import annotations

import os
import time
from typing import Any

import psycopg
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

from store import claim, fingerprint, finish

app = FastAPI(title="idempotent-payments")
DSN = os.environ["DATABASE_URL"]
LEASE_SECONDS = int(os.environ.get("IDEMPOTENCY_LEASE_SECONDS", "30"))


class ChargeRequest(BaseModel):
    account_id: str
    amount: int
    currency: str = "inr"
    customer: str


class Gateway:
    """Stand-in for the provider. Swap for the real client."""

    def charge(self, amount: int, customer: str, idempotency_key: str) -> dict[str, Any]:
        time.sleep(0.05)
        return {"id": "ch_" + idempotency_key[:12], "amount": amount,
                "customer": customer, "status": "succeeded"}


gateway = Gateway()


@app.post("/v1/charges", status_code=201)
def create_charge(req: ChargeRequest, response: Response,
                  idempotency_key: str | None = Header(default=None)) -> Any:
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required on POST")

    fp = fingerprint(req.model_dump())
    with psycopg.connect(DSN, autocommit=True) as conn:
        c = claim(conn, req.account_id, idempotency_key, "POST", "/v1/charges", fp)

    if c.kind == "params_mismatch":
        raise HTTPException(
            409,
            "Keys for idempotent requests can only be used with the same "
            "parameters they were first used with",
        )
    if c.kind == "in_progress":
        raise HTTPException(409, "A request with this Idempotency-Key is already in progress")
    if c.kind == "replay":
        response.headers["Idempotent-Replayed"] = "true"
        return c.body

    # ---- RPC: no transaction open ----
    try:
        result = gateway.charge(req.amount, req.customer, idempotency_key)
        state, code = "succeeded", 201
    except TimeoutError:
        result, state, code = {"error": "provider timeout"}, "retryable", 503
    except Exception as exc:  # noqa: BLE001 - provider errors are classified explicitly
        result, state, code = {"error": str(exc)}, "terminal", 402

    # ---- POST-RPC: store the answer ----
    with psycopg.connect(DSN, autocommit=True) as conn:
        finish(conn, c.id, state, code, result)

    if code >= 400:
        raise HTTPException(code, result.get("error", "payment failed"))
    return result
