"""Chapter 19: home-region ownership. Reads local, writes home, async replication."""

from __future__ import annotations

import zlib

REGIONS = ("ap-south-1", "ap-southeast-1")


def home_region(key: str) -> str:
    return REGIONS[zlib.crc32(key.encode()) % len(REGIONS)]


class RegionRouter:
    def __init__(self, local: str, local_store, peer_store):
        self.local = local
        self.local_store = local_store
        self.peer_store = peer_store
        self.failover: dict[str, str] = {}        # down region -> promoted region
        self.cross_region_reads = 0

    def home(self, key: str) -> str:
        h = home_region(key)
        return self.failover.get(h, h)

    def accepts_writes(self, key: str) -> bool:
        return self.home(key) == self.local

    def write(self, key, value):
        if not self.accepts_writes(key):
            return ("redirect", self.home(key))
        self.local_store[key] = value
        return ("ok", self.local)

    def read(self, key, consistency: str = "local"):
        if consistency == "local" or self.home(key) == self.local:
            return self.local_store.get(key)
        self.cross_region_reads += 1
        return self.peer_store.get(key)

    def promote(self, down: str, up: str) -> None:
        self.failover[down] = up
