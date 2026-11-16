"""Chapter 05: three phases, two short transactions, one network call.

Rules enforced here, in code:
  1. no network calls in the pre-RPC and post-RPC phases
  2. no database work during the RPC
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

DSN = os.environ["DATABASE_URL"]
LEASE_SECONDS = 30
PROVIDER_TIMEOUT_S = 2.0


@dataclass
class Outcome:
    state: str            # succeeded | failed_terminal | failed_retryable | unknown
    code: int
    body: dict[str, Any]

    @classmethod
    def succeeded(cls, ref: str) -> "Outcome":
        return cls("succeeded", 201, {"provider_ref": ref})

    @classmethod
    def terminal(cls, msg: str) -> "Outcome":
        return cls("failed_terminal", 402, {"error": msg})

    @classmethod
    def retryable(cls, msg: str) -> "Outcome":
        return cls("failed_retryable", 503, {"error": msg})

    @classmethod
    def unknown(cls, msg: str) -> "Outcome":
        return cls("unknown", 202, {"error": msg, "state": "unknown"})


class Provider:
    """Stand-in for an acquiring bank. faults.py can make it misbehave."""

    def charge(self, amount_minor: int, currency: str, idempotency_key: str) -> str:
        return "prov_" + idempotency_key[-8:]

    def get_by_key(self, idempotency_key: str) -> dict[str, Any]:
        return {"status": "captured", "ref": "prov_" + idempotency_key[-8:]}


def create_payment(account_id: str, idem_key: str, amount_minor: int,
                   currency: str, provider: Provider) -> dict[str, Any]:
    # ---------- PRE-RPC ----------
    with psycopg.connect(DSN) as conn, conn.transaction():
        row = conn.execute(
            """INSERT INTO payments
                 (account_id, idempotency_key, amount_minor, currency, provider,
                  state, lease_expires_at)
               VALUES (%s, %s, %s, %s, 'stub', 'pending',
                       now() + interval '%s seconds')
               ON CONFLICT (account_id, idempotency_key) DO NOTHING
               RETURNING id""",
            (account_id, idem_key, amount_minor, currency, LEASE_SECONDS),
        ).fetchone()

        if row is None:
            existing = conn.execute(
                """SELECT id, state, provider_ref FROM payments
                    WHERE account_id = %s AND idempotency_key = %s""",
                (account_id, idem_key),
            ).fetchone()
            return {"id": str(existing[0]), "state": existing[1],
                    "provider_ref": existing[2], "replayed": True}
        payment_id = row[0]

    # ---------- RPC (no transaction open) ----------
    provider_key = f"pay-{payment_id}"
    try:
        ref = provider.charge(amount_minor, currency, provider_key)
        outcome = Outcome.succeeded(ref)
    except TimeoutError as exc:
        outcome = Outcome.unknown(f"timeout: {exc}")
    except PermissionError as exc:          # provider 4xx analogue
        outcome = Outcome.terminal(str(exc))
    except Exception as exc:                # noqa: BLE001
        outcome = Outcome.unknown(f"unexpected: {exc}")

    # ---------- POST-RPC ----------
    with psycopg.connect(DSN) as conn, conn.transaction():
        conn.execute(
            """UPDATE payments
                  SET state = %s, provider_ref = %s, last_error = %s,
                      lease_expires_at = NULL, updated_at = now(),
                      attempts = attempts + 1
                WHERE id = %s""",
            (outcome.state, outcome.body.get("provider_ref"),
             outcome.body.get("error"), payment_id),
        )
        if outcome.state == "succeeded":
            conn.execute(
                """INSERT INTO ledger_entries (payment_id, account, direction, amount_minor)
                   VALUES (%s, 'provider_clearing', 'debit', %s),
                          (%s, 'customer_receivable', 'credit', %s)""",
                (payment_id, amount_minor, payment_id, amount_minor),
            )
        conn.execute(
            """INSERT INTO outbox (aggregate_id, topic, payload)
               VALUES (%s, %s, %s)""",
            (payment_id,
             "payments.settled" if outcome.state == "succeeded" else "payments.needs_review",
             Jsonb({"payment_id": str(payment_id),
                                       "state": outcome.state,
                                       "amount_minor": amount_minor})),
        )

    return {"id": str(payment_id), "state": outcome.state, **outcome.body}
