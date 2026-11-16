"""Chapter 16: cache-aside with single-flight leases.

The lease is the mechanism that turns a stampede into one database query plus N
short waits. Without it, a hot key's expiry is a self-inflicted outage.
"""

from __future__ import annotations

import random
import time


class Cache:
    def __init__(self):
        self.data: dict[str, tuple[object, float]] = {}
        self.leases: dict[str, float] = {}

    def get(self, key):
        item = self.data.get(key)
        if item is None:
            return None
        value, expires = item
        if expires < time.time():
            del self.data[key]
            return None
        return value

    def set(self, key, value, ttl: float):
        self.data[key] = (value, time.time() + ttl)

    def delete(self, key):
        """Invalidate the value AND any outstanding lease: a reader that started
        before this write must not be allowed to install what it read."""
        self.data.pop(key, None)
        self.leases.pop(key, None)

    def acquire_lease(self, key, ttl: float) -> str | None:
        now = time.time()
        holder = self.leases.get(key)
        if holder is not None and holder > now:
            return None                      # someone else is already fetching
        token = f"{key}:{now}"
        self.leases[key] = now + ttl
        return token

    def release_lease(self, key, token):
        """Releasing also rejects a stale set: the reader that held the lease is
        the only one allowed to have installed a value."""
        self.leases.pop(key, None)


class CacheAside:
    def __init__(self, cache: Cache, db, ttl: float = 300, lease_ttl: float = 10):
        self.cache, self.db = cache, db
        self.ttl, self.lease_ttl = ttl, lease_ttl
        self.stats = {"hit": 0, "waited": 0, "miss": 0, "fallback": 0}

    def _jitter(self, ttl: float) -> float:
        return ttl * random.uniform(0.9, 1.1)      # no synchronised expiry

    def get(self, key):
        hit = self.cache.get(key)
        if hit is not None:
            self.stats["hit"] += 1
            return hit

        token = self.cache.acquire_lease(key, self.lease_ttl)
        if token is None:
            time.sleep(0.01)                       # bounded wait, then retry
            hit = self.cache.get(key)
            if hit is not None:
                self.stats["waited"] += 1
                return hit
            self.stats["fallback"] += 1
            return self.db.read(key)

        value = self.db.read(key)                  # exactly one query per key
        self.cache.set(key, value, self._jitter(self.ttl))
        self.cache.release_lease(key, token)
        self.stats["miss"] += 1
        return value

    def write(self, key, value):
        self.db.write(key, value)
        self.cache.delete(key)                     # DELETE, never SET
