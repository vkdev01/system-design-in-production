"""Chapter 15: shard routing and a scatter-gather that returns at most k per shard."""

from __future__ import annotations

import heapq
import zlib
from itertools import chain


class Cluster:
    def __init__(self, shards: int = 3):
        self.shards = [__import__("index").Index() for _ in range(shards)]

    def shard_for(self, doc_id: str) -> int:
        return zlib.crc32(doc_id.encode()) % len(self.shards)

    def add(self, doc_id: str, text: str, **fields) -> None:
        self.shards[self.shard_for(doc_id)].add(doc_id, text, **fields)

    def search(self, query: str, k: int = 20) -> list[tuple[str, float]]:
        per_shard = [s.search(query, k) for s in self.shards]     # at most k each
        merged = heapq.nlargest(k, chain.from_iterable(per_shard), key=lambda x: x[1])
        return merged

    def stats(self) -> dict:
        return {
            "shards": len(self.shards),
            "docs": sum(len(s.lengths) for s in self.shards),
            "terms": sum(len(s.postings) for s in self.shards),
        }
