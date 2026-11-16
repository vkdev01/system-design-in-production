"""Chapter 05: the repair loop - what makes the whole thing exactly-once.

Picks up rows whose lease has expired and asks the provider what actually
happened. FOR UPDATE SKIP LOCKED lets several workers run without fighting.
"""

from __future__ import annotations

import os
import time

import psycopg

from service import Outcome, Provider

DSN = os.environ["DATABASE_URL"]

STUCK_SQL = """
SELECT id, provider, amount_minor
FROM payments
WHERE state IN ('pending', 'unknown')
  AND lease_expires_at < now() - interval '10 seconds'
ORDER BY updated_at
LIMIT %s
FOR UPDATE SKIP LOCKED
"""


def repair_once(batch: int = 200) -> int:
    provider = Provider()
    fixed = 0
    with psycopg.connect(DSN) as conn:
        rows = conn.execute(STUCK_SQL, (batch,)).fetchall()
        conn.commit()

    for payment_id, _prov, _amount in rows:
        key = f"pay-{payment_id}"
        try:
            remote = provider.get_by_key(key)
        except Exception:                        # provider still unreachable
            continue

        status = remote.get("status")
        if status == "captured":
            outcome = Outcome.succeeded(remote["ref"])
        elif status == "not_found":
            outcome = Outcome.retryable("provider has no record; safe to retry")
        else:
            outcome = Outcome.terminal(f"provider says {status}")

        with psycopg.connect(DSN) as conn, conn.transaction():
            conn.execute(
                """UPDATE payments
                      SET state = %s, provider_ref = COALESCE(%s, provider_ref),
                          last_error = %s, lease_expires_at = NULL, updated_at = now()
                    WHERE id = %s""",
                (outcome.state, outcome.body.get("provider_ref"),
                 outcome.body.get("error"), payment_id),
            )
        fixed += 1
    return fixed


if __name__ == "__main__":
    while True:
        n = repair_once()
        print(f"repaired {n} payment(s)", flush=True)
        time.sleep(5)
