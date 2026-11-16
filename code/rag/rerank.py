"""Chapter 11: reranking as a budget.

A real cross-encoder scores (query, chunk) pairs in one forward pass. The stub
here uses weighted token overlap so the harness runs on a laptop; the interface
is the same, so swapping in a real model is one class.
"""

from __future__ import annotations

from corpus import Chunk, tokenize


class StubReranker:
    def score_batch(self, pairs: list[tuple[str, str]]) -> list[float]:
        out = []
        for query, text in pairs:
            q = set(tokenize(query))
            t = tokenize(text)
            if not q or not t:
                out.append(0.0)
                continue
            overlap = len(q & set(t)) / len(q)
            density = len(q & set(t)) / (len(t) ** 0.5)
            out.append(0.7 * overlap + 0.3 * density)
        return out


def rerank(query: str, hits: list[tuple[str, float]], by_id: dict[str, Chunk],
           ranker: StubReranker, top_k: int = 20, batch: int = 32):
    scored: list[tuple[str, float]] = []
    for i in range(0, len(hits), batch):
        window = hits[i : i + batch]
        pairs = [(query, by_id[cid].indexed_text) for cid, _ in window]
        for (cid, _), s in zip(window, ranker.score_batch(pairs)):
            scored.append((cid, s))
    return sorted(scored, key=lambda kv: -kv[1])[:top_k]
