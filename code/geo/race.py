"""Chapter 08, drill 4: two riders, one driver.

Exactly one SET NX must win; the other must fall through to the next candidate.
Run against a real Redis:
    python race.py --concurrent 2
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf

import redis

from match import accept_trip, offer_trip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrent", type=int, default=2)
    args = ap.parse_args()

    r = redis.Redis(host="localhost", port=6379, decode_responses=False)
    r.delete("offer:driver-1")

    with cf.ThreadPoolExecutor(max_workers=args.concurrent) as pool:
        futures = [pool.submit(offer_trip, r, f"rider-{i}", "driver-1")
                   for i in range(args.concurrent)]
        results = [f.result() for f in futures]

    winners = sum(1 for ok in results if ok)
    print(f"offers={results} winners={winners}")
    assert winners == 1, "the offer lock is not atomic"
    print("one winner, as required")


if __name__ == "__main__":
    main()
