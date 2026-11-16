"""Chapter 19: why replication is asynchronous, in four lines of arithmetic.

    python latency.py --rtt-ms 70 --budget-ms 200
"""

from __future__ import annotations

import argparse

LOCAL_MS = 5


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtt-ms", type=float, default=70)
    ap.add_argument("--budget-ms", type=float, default=200)
    args = ap.parse_args()

    hops = [
        ("local commit", 0),
        ("+ sync to 1 peer", 1),
        ("+ sync to a 2nd peer", 2),
        ("+ one read-back across regions", 3),
    ]
    print(f"cross-region RTT {args.rtt_ms:.0f} ms   write budget {args.budget_ms:.0f} ms")
    for label, n in hops:
        total = LOCAL_MS + n * args.rtt_ms
        verdict = "OK" if total <= args.budget_ms else "BREACHES BUDGET"
        print(f"  {label:32} {total:>7.0f} ms   {verdict}")
    print()
    print(f"=> at {args.rtt_ms:.0f} ms per round trip you get "
          f"{int((args.budget_ms - LOCAL_MS) // args.rtt_ms)} synchronous hops, then nothing else")


if __name__ == "__main__":
    main()
