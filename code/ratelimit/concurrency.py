"""Chapter 06: the concurrency limiter.

Rate is not the only way to saturate a service. A CPU-heavy endpoint dies from
in-flight work, not from requests per second, so limit both.

The sorted set is scored by start time; stale entries are reaped so a crashed
worker cannot permanently consume a slot.
"""

from __future__ import annotations

import time
import uuid

ACQUIRE = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local token = ARGV[3]
local stale = now - 60
redis.call('ZREMRANGEBYSCORE', key, '-inf', stale)
if redis.call('ZCARD', key) >= limit then return 0 end
redis.call('ZADD', key, now, token)
redis.call('PEXPIRE', key, 120000)
return 1
"""


class ConcurrencyLimiter:
    def __init__(self, redis, limit: int = 20):
        self.redis = redis
        self.limit = limit

    def acquire(self, user: str, token: str | None = None) -> str | None:
        token = token or uuid.uuid4().hex
        ok = self.redis.eval(ACQUIRE, 1, f"cc:{{{user}}}", time.time(), self.limit, token)
        return token if ok else None

    def release(self, user: str, token: str) -> None:
        # Always call in a finally block: a leaked slot reduces the user's
        # capacity until the 60s reaper cleans it up.
        self.redis.zrem(f"cc:{{{user}}}", token)

    def in_flight(self, user: str) -> int:
        return int(self.redis.zcard(f"cc:{{{user}}}"))
