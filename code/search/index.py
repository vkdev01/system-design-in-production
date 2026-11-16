"""Chapter 15: an inverted index with positions, tombstones and BM25."""

from __future__ import annotations

import heapq
import math
import re
from collections import Counter

STOP = {"the", "a", "an", "of", "to", "and", "in", "is", "it", "for", "on"}


def analyse(text: str) -> list[str]:
    """Tokenise, lowercase, drop stopwords. The SAME function must run on both
    the document and the query, or search silently returns nothing."""
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


class Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.postings: dict[str, dict[str, list[int]]] = {}
        self.docs: dict[str, dict] = {}
        self.lengths: dict[str, int] = {}
        self.tombstones: set[str] = set()
        self.k1, self.b = k1, b
        self._total_terms = 0            # kept incrementally: avgdl() must be O(1),
        self._avgdl = 0.0                # not O(documents) inside the scoring loop

    def add(self, doc_id: str, text: str, **fields) -> None:
        terms = analyse(text)
        self._total_terms += len(terms) - self.lengths.get(doc_id, 0)
        self._avgdl = self._total_terms / max(1, len(self.lengths) or 1)
        self.lengths[doc_id] = len(terms)
        self._avgdl = self._total_terms / max(1, len(self.lengths))
        self.docs[doc_id] = {"text": text, **fields}
        for pos, term in enumerate(terms):
            self.postings.setdefault(term, {}).setdefault(doc_id, []).append(pos)

    def remove(self, doc_id: str) -> None:
        self.tombstones.add(doc_id)          # gone from results, still on disk

    def avgdl(self) -> float:
        return self._avgdl

    def idf(self, term: str) -> float:
        n = len(self.postings.get(term, {}))
        N = len(self.lengths)
        return math.log(1 + (N - n + 0.5) / (n + 0.5))

    def bm25(self, doc_id: str, terms: list[str]) -> float:
        dl = self.lengths.get(doc_id, 0)
        avg = self.avgdl() or 1
        score = 0.0
        for t in terms:
            plist = self.postings.get(t, {})
            if doc_id not in plist:
                continue
            tf = len(plist[doc_id])
            score += self.idf(t) * (tf * (self.k1 + 1)) / (
                tf + self.k1 * (1 - self.b + self.b * dl / avg)
            )
        return score

    def search(self, query: str, k: int = 20) -> list[tuple[str, float]]:
        terms = analyse(query)
        if not terms:
            return []
        # rarest term first: intersecting 50 docs beats intersecting a million
        terms = sorted(set(terms), key=lambda t: len(self.postings.get(t, {})))
        candidates = set(self.postings.get(terms[0], {})) - self.tombstones
        for t in terms[1:]:
            candidates &= set(self.postings.get(t, {}))
            if not candidates:
                return []
        heap: list[tuple[float, str]] = []
        for doc_id in candidates:
            s = self.bm25(doc_id, terms)
            if len(heap) < k:
                heapq.heappush(heap, (s, doc_id))
            elif s > heap[0][0]:
                heapq.heapreplace(heap, (s, doc_id))
        return [(d, round(s, 3)) for s, d in sorted(heap, reverse=True)]
