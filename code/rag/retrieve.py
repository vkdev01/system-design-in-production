"""Chapter 11: hybrid retrieval with reciprocal rank fusion.

Two retrievers with different failure modes -- a trigram-hash dense proxy that
is robust to phrasing, and BM25 which is exact on identifiers -- fused by rank,
because their scores are not comparable.
"""

from __future__ import annotations

import math
import zlib
from collections import Counter

from corpus import Chunk, tokenize

DIM = 2048


def dense_vector(text: str) -> dict[int, float]:
    """Character-trigram hashing: a cheap stand-in for an embedding model."""
    toks = tokenize(text)
    grams = [t[i : i + 3] for t in toks for i in range(max(1, len(t) - 2))]
    vec: Counter[int] = Counter()
    for g in grams:
        vec[zlib.crc32(g.encode()) % DIM] += 1
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def cosine(a: dict[int, float], b: dict[int, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class BM25:
    def __init__(self, docs: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = docs
        self.tokens = [tokenize(d.indexed_text) for d in docs]
        self.avgdl = sum(len(t) for t in self.tokens) / max(1, len(self.tokens))
        self.df: Counter[str] = Counter()
        for toks in self.tokens:
            self.df.update(set(toks))

    def search(self, query: str, k: int = 100) -> list[tuple[str, float]]:
        q = tokenize(query)
        n = len(self.docs)
        scores = []
        for doc, toks in zip(self.docs, self.tokens):
            tf = Counter(toks)
            dl = len(toks)
            s = 0.0
            for term in q:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                s += idf * (tf[term] * (self.k1 + 1)) / (
                    tf[term] + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                )
            scores.append((doc.cid, s))
        return sorted(scores, key=lambda kv: -kv[1])[:k]


class Dense:
    def __init__(self, docs: list[Chunk]):
        self.docs = docs
        self.vectors = {d.cid: dense_vector(d.indexed_text) for d in docs}

    def search(self, query: str, k: int = 100) -> list[tuple[str, float]]:
        qv = dense_vector(query)
        scored = [(cid, cosine(qv, v)) for cid, v in self.vectors.items()]
        return sorted(scored, key=lambda kv: -kv[1])[:k]


def rrf(ranked_lists: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal rank fusion. Ranks are comparable; scores are not."""
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (cid, _score) in enumerate(ranked):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(fused.items(), key=lambda kv: -kv[1])


def hybrid(query: str, dense: Dense, bm25: BM25, k: int = 100, shortlist: int = 150):
    return rrf([dense.search(query, k), bm25.search(query, k)])[:shortlist]
