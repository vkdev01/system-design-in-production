"""Chapter 19: a failover that can say no.

    python failover.py --down ap-south-1 --lag-ms 300 --rpo-ms 500
    python failover.py --down ap-south-1 --lag-ms 900 --rpo-ms 500   # refuses
"""

from __future__ import annotations

import argparse

DETECT_S = 30        # 3 health checks x 10 s
DNS_S = 60           # TTL
PROMOTE_S = 2
FREEZE_S = 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--down", default="ap-south-1")
    ap.add_argument("--up", default="ap-southeast-1")
    ap.add_argument("--lag-ms", type=int, default=300)
    ap.add_argument("--rpo-ms", type=int, default=500)
    ap.add_argument("--budget-s", type=int, default=300)
    args = ap.parse_args()

    if args.lag_ms > args.rpo_ms:
        print(f"REFUSED: peer is {args.lag_ms} ms behind, RPO allows {args.rpo_ms} ms")
        print("promoting now would lose more data than the promise allows")
        return

    steps = [
        ("detect (health checks)", DETECT_S),
        ("promote peer", PROMOTE_S),
        ("DNS flip (TTL 60)", DNS_S),
        ("freeze old region writes", FREEZE_S),
    ]
    total = sum(s for _, s in steps)
    for label, s in steps:
        print(f"  {label:26} {s:>4} s")
    print(f"  {'total':26} {total:>4} s   (budget {args.budget_s} s)")
    print(f"promoted {args.up}; {args.down} frozen for writes; "
          f"data-loss window <= {args.lag_ms} ms")
    print("cooldown: refuse to fail back for 30 minutes")


if __name__ == "__main__":
    main()
