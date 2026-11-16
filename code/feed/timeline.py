"""Chapter 14: the timeline store and the bounded merge.

Redis ZSET semantics in memory: score is the post timestamp, member is the post
id. The store keeps only the head of each timeline, because the head is what
gets read; older pages backfill from the post store.
"""

from __future__ import annotations

import heapq


class TimelineStore:
    def __init__(self, cap: int = 800):
        self.cap = cap
        self.z: dict[str, dict[str, float]] = {}

    def add(self, user: str, post_id: str, ts: float) -> None:
        z = self.z.setdefault(user, {})
        z[post_id] = ts
        if len(z) > self.cap:                       # keep the head only
            for pid, _ in sorted(z.items(), key=lambda kv: kv[1])[: len(z) - self.cap]:
                del z[pid]

    def head(self, user: str, k: int) -> list[tuple[str, float]]:
        return sorted(self.z.get(user, {}).items(), key=lambda kv: -kv[1])[:k]

    def size(self, user: str) -> int:
        return len(self.z.get(user, {}))


def kway_merge(sources: list[list[tuple[str, float]]], k: int = 20) -> list[str]:
    """Merge N newest-first lists into one, holding at most k items.

    A user following 8 celebrities costs 8 heap pushes per returned item, not a
    sort of everything -- which is what keeps p99 independent of graph size.
    """
    heap: list[tuple[float, str, int, int]] = []
    for i, src in enumerate(sources):
        if src:
            pid, ts = src[0]
            heapq.heappush(heap, (-ts, pid, i, 0))

    out: list[str] = []
    while heap and len(out) < k:
        _, pid, i, idx = heapq.heappop(heap)
        out.append(pid)
        nxt = idx + 1
        if nxt < len(sources[i]):
            pid2, ts2 = sources[i][nxt]
            heapq.heappush(heap, (-ts2, pid2, i, nxt))
    return out
