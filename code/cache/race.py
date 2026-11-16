"""Chapter 16: why writers delete instead of setting.

    python race.py --strategy set
    python race.py --strategy delete

Same interleaving both times: a reader starts a slow database read and sees v1,
a writer commits v2 in the middle, then the reader finishes and installs what it
read. With `set` the cache ends up holding v1 forever; with `delete` plus a lease
check the stale write is rejected.
"""

from __future__ import annotations

import argparse
import time

from aside import Cache


class DB:
    def __init__(self, value):
        self.value = value

    def read(self, key):
        snapshot = self.value
        time.sleep(0.05)              # the slow read that opens the window
        return snapshot

    def write(self, key, value):
        self.value = value


def run(strategy: str) -> str:
    cache = Cache()
    db = DB("v1")

    # t0: reader misses and starts a slow read (sees v1)
    token = cache.acquire_lease("k", ttl=10)
    reader_value = db.read("k")       # 50 ms passes here

    # t1: writer commits v2
    db.write("k", "v2")
    if strategy == "set":
        cache.set("k", "v2", ttl=300)     # writer installs v2 ...
    else:
        cache.delete("k")                 # ... or removes the key

    # t2: the reader tries to install what it read
    if strategy == "set":
        cache.set("k", reader_value, ttl=300)   # v1 overwrites v2 -> stale forever
    else:
        # a set is only accepted while the lease is live; the write killed it
        if cache.leases.get("k", 0) > time.time():
            cache.set("k", reader_value, ttl=300)

    cache.release_lease("k", token)
    cached = cache.get("k")
    return cached if cached is not None else db.read("k")   # next read fetches v2


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="set", choices=["set", "delete"])
    args = ap.parse_args()
    final = run(args.strategy)
    verdict = "STALE" if final == "v1" else "correct"
    print(f"strategy={args.strategy:7} final cache value={final:8} {verdict}")
