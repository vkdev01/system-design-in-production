"""Chapter 05: deterministic fault injection for the drills.

  python faults.py --mode timeout-after-charge
  python faults.py --mode outage --seconds 120
  python faults.py --mode decline
"""

from __future__ import annotations

import argparse
import time

from service import Provider, create_payment


class FaultyProvider(Provider):
    def __init__(self, mode: str, until: float | None = None):
        self.mode = mode
        self.until = until

    def charge(self, amount_minor: int, currency: str, idempotency_key: str) -> str:
        if self.mode == "outage" and self.until and time.time() < self.until:
            raise ConnectionError("provider unavailable")
        if self.mode == "decline":
            raise PermissionError("card_declined")
        ref = super().charge(amount_minor, currency, idempotency_key)
        if self.mode == "timeout-after-charge":
            # The money moved, the answer did not come back. The worst case.
            raise TimeoutError("response lost after capture")
        return ref


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True,
                    choices=["timeout-after-charge", "outage", "decline"])
    ap.add_argument("--seconds", type=int, default=60)
    args = ap.parse_args()

    provider = FaultyProvider(args.mode, until=time.time() + args.seconds)
    result = create_payment(
        account_id="acme",
        idem_key=f"drill-{args.mode}-{int(time.time())}",
        amount_minor=49900,
        currency="INR",
        provider=provider,
    )
    print(result)
    print("Now run repair.py and confirm exactly one charge exists.")


if __name__ == "__main__":
    main()
