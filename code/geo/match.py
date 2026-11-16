"""Chapter 08: the expansion loop and the offer lock.

Ring distance is quantised, so expand rings to *find* candidates and rank by
real distance to *choose* one. And an offer must be atomic: two riders offering
the same driver is a duplicate-class bug.
"""

from __future__ import annotations

import os

import h3
import psycopg
import redis

RES_INDEX = 9
MATCH_SQL = open(os.path.join(os.path.dirname(__file__), "match.sql")).read()


def find_candidates(conn: psycopg.Connection, lat: float, lng: float, city: str,
                    want: int = 10, max_k: int = 5) -> tuple[list[tuple], int]:
    """Expand 1 -> 2 -> 3 -> max_k rings until we have enough candidates."""
    cell = h3.latlng_to_cell(lat, lng, RES_INDEX)
    rows: list[tuple] = []
    k = 0
    for k in (1, 2, 3, max_k):
        rows = conn.execute(MATCH_SQL, (lat, lng, city, want, k)).fetchall()
        if len(rows) >= want:
            return rows, k
    return rows, k


def offer_trip(r: redis.Redis, rider_id: str, driver_id: str, ttl: int = 12) -> bool:
    """Exactly-once offer. SET NX is the atomic primitive; the TTL is the lease."""
    return bool(r.set(f"offer:{driver_id}", rider_id, nx=True, ex=ttl))


def accept_trip(r: redis.Redis, rider_id: str, driver_id: str) -> bool:
    """Idempotent on the offer: the same rider may accept twice, and must win once."""
    current = r.get(f"offer:{driver_id}")
    if current is None:
        return False
    if current.decode() != rider_id:
        return False
    r.delete(f"offer:{driver_id}")
    r.set(f"trip:{rider_id}", driver_id, ex=3600)
    return True


if __name__ == "__main__":
    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/geo")
    with psycopg.connect(dsn) as conn:
        candidates, k = find_candidates(conn, 19.0670, 72.8680, "mumbai")
        print(f"found {len(candidates)} candidates at k={k}")
        for row in candidates[:5]:
            print(f"  {row[0]} {row[1]} {int(row[2])} m (cell {row[3]})")
