"""Chapter 08, drill 1: the airport hotspot.

Put 2,000 drivers in ONE res-9 cell, then match 1,000 riders and watch the
candidate-set size explode. The cap and the ranking step must keep latency flat.
"""

from __future__ import annotations

import argparse
import random
import time

import h3

RES = 9


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drivers", type=int, default=2000)
    ap.add_argument("--riders", type=int, default=1000)
    ap.add_argument("--one-cell", action="store_true", help="all drivers in one cell")
    ap.add_argument("--max-candidates", type=int, default=40)
    args = ap.parse_args()

    base_lat, base_lng = 19.0896, 72.8656  # Mumbai airport
    cell = h3.latlng_to_cell(base_lat, base_lng, RES)

    drivers = []
    for _ in range(args.drivers):
        if args.one_cell:
            drivers.append(cell)
        else:
            drivers.append(h3.latlng_to_cell(
                base_lat + random.uniform(-0.05, 0.05),
                base_lng + random.uniform(-0.05, 0.05), RES))

    by_cell: dict[str, int] = {}
    for c in drivers:
        by_cell[c] = by_cell.get(c, 0) + 1

    print(f"drivers={len(drivers)} in {len(by_cell)} cells; "
          f"busiest cell holds {max(by_cell.values())}")

    t0 = time.perf_counter()
    total = 0
    for _ in range(args.riders):
        rider_cell = cell if args.one_cell else h3.latlng_to_cell(
            base_lat + random.uniform(-0.05, 0.05),
            base_lng + random.uniform(-0.05, 0.05), RES)
        for k in (1, 2, 3, 5):
            found = sum(by_cell.get(c, 0) for c in h3.grid_disk(rider_cell, k))
            if found >= 10:
                total += min(found, args.max_candidates)
                break
    dt = (time.perf_counter() - t0) * 1000
    print(f"{args.riders} matches in {dt:.1f} ms ({dt / args.riders:.3f} ms/match), "
          f"avg candidates returned {total / args.riders:.1f}")


if __name__ == "__main__":
    main()
