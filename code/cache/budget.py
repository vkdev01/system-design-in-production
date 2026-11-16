"""Chapter 16: miss rate -> database load, which is the only cache number that
matters at 3 a.m.

    python budget.py --reads 100000 --db-capacity 2000
"""

from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reads", type=int, default=100_000)
    ap.add_argument("--db-capacity", type=int, default=2_000)
    args = ap.parse_args()

    print(f"reads {args.reads:,}/s   database capacity {args.db_capacity:,} q/s")
    for miss in (0.005, 0.01, 0.02, 0.05, 0.10):
        qps = args.reads * miss
        load = qps / args.db_capacity
        verdict = "OK" if load < 0.6 else "AT THE EDGE" if load <= 1.0 else "OUTAGE"
        print(f"  miss {miss * 100:>4.1f}%  ->  {qps:>8,.0f} q/s  "
              f"{load * 100:>5.0f}% of capacity  {verdict}")


if __name__ == "__main__":
    main()
