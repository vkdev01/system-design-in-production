"""Chapter 04: the key store as a state machine.

Arbitration order matters. Fingerprint mismatch is checked before replay,
because replaying a stored response to a request that asked for something
different is a lie.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg

LEASE_SECONDS = 30

CLAIM_SQL = """
INSERT INTO idempotency_keys
    (account_id, key, request_method, request_path, request_hash,
     state, locked_at, lease_expires_at)
VALUES (%s, %s, %s, %s, %s, 'in_progress', now(), now() + interval '%s seconds')
ON CONFLICT (account_id, key) DO NOTHING
RETURNING id
"""

SELECT_SQL = """
SELECT id, request_hash, state, lease_expires_at, response_code, response_body
FROM idempotency_keys
WHERE account_id = %s AND key = %s
FOR UPDATE
"""


@dataclass
class Claim:
    kind: str                      # execute | replay | in_progress | params_mismatch
    id: int | None = None
    code: int | None = None
    body: Any = None

    @classmethod
    def execute(cls, row_id: int) -> "Claim":
        return cls(kind="execute", id=row_id)

    @classmethod
    def replay(cls, code: int, body: Any) -> "Claim":
        return cls(kind="replay", code=code, body=body)

    @classmethod
    def in_progress(cls) -> "Claim":
        return cls(kind="in_progress")

    @classmethod
    def params_mismatch(cls) -> "Claim":
        return cls(kind="params_mismatch")


def fingerprint(payload: dict[str, Any]) -> bytes:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).digest()


def claim(conn: psycopg.Connection, account: str, key: str, method: str,
          path: str, fp: bytes) -> Claim:
    """Claim a key, or explain why we cannot."""
    with conn.transaction():
        row = conn.execute(
            CLAIM_SQL, (account, key, method, path, fp, LEASE_SECONDS)
        ).fetchone()
        if row:
            return Claim.execute(row[0])

        existing = conn.execute(SELECT_SQL, (account, key)).fetchone()
        if existing is None:
            # Deleted by the reaper between our insert and select: retry once.
            return Claim.in_progress()

        _id, req_hash, state, lease, code, body = existing

        if bytes(req_hash) != fp:
            return Claim.params_mismatch()

        if state in ("succeeded", "terminal"):
            return Claim.replay(code, body)

        now = datetime.now(timezone.utc)
        if state == "in_progress" and lease is not None and lease > now:
            return Claim.in_progress()

        # Lease expired: the previous worker died mid-flight. Take over.
        conn.execute(
            """UPDATE idempotency_keys
                  SET locked_at = now(),
                      lease_expires_at = now() + interval '%s seconds'
                WHERE id = %s""",
            (LEASE_SECONDS, _id),
        )
        return Claim.execute(_id)


def finish(conn: psycopg.Connection, row_id: int, state: str, code: int, body: Any) -> None:
    conn.execute(
        """UPDATE idempotency_keys
              SET state = %s, response_code = %s, response_body = %s,
                  updated_at = now(), lease_expires_at = NULL
            WHERE id = %s""",
        (state, code, json.dumps(body), row_id),
    )
    conn.commit()
