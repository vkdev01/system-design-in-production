"""Chapter 06: the fleet usage load shedder.

Reserves a fraction of the fleet for critical methods. Non-critical traffic
above its share gets 503. This is an emergency valve, not a fairness mechanism:
it is coarse on purpose, and it is what keeps charge creation working while
everything else is on fire.
"""

from __future__ import annotations

import redis

CRITICAL = {
    "POST /v1/charges",
    "POST /v1/refunds",
    "POST /v1/payouts",
    "POST /v1/auth/token",
}

RESERVED_FRACTION = 0.20


class FleetShedder:
    def __init__(self, r: redis.Redis, fleet_capacity: int,
                 reserved_fraction: float = RESERVED_FRACTION):
        self.r = r
        self.capacity = fleet_capacity
        self.reserved = reserved_fraction

    def _inflight(self, cls: str) -> int:
        return int(self.r.get(f"fleet:inflight:{cls}") or 0)

    def admit(self, method_path: str, cls: str) -> bool:
        if method_path in CRITICAL:
            return True
        non_critical_capacity = self.capacity * (1 - self.reserved)
        return (self._inflight("critical") + self._inflight(cls)) <= non_critical_capacity

    def enter(self, cls: str) -> None:
        self.r.incr(f"fleet:inflight:{cls}")

    def exit(self, cls: str) -> None:
        self.r.decr(f"fleet:inflight:{cls}")
