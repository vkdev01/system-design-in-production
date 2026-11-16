"""Chapter 11: the harness that decides whether a change ships.

    python eval_recall.py --config dense_only
    python eval_recall.py --config hybrid
    python eval_recall.py --config hybrid_contextual_rerank

Prints recall@20 and recall@5 on the golden set, which is the number the whole
chapter is about.
"""

from __future__ import annotations

import argparse
import time

from corpus import build, golden
from rerank import StubReranker, rerank
from retrieve import BM25, Dense, hybrid


def run(config: str) -> dict:
    contextual = "contextual" in config
    chunks = build(contextualised=contextual)
    by_id = {c.cid: c for c in chunks}
    questions = golden(chunks)

    dense = Dense(chunks)
    bm25 = BM25(chunks)
    ranker = StubReranker()

    hits20 = hits5 = 0
    t0 = time.perf_counter()
    for item in questions:
        if config == "dense_only":
            ranked = dense.search(item["q"], k=20)
        elif config in ("hybrid", "hybrid_contextual"):
            ranked = hybrid(item["q"], dense, bm25)[:20]
        else:
            shortlist = hybrid(item["q"], dense, bm25)
            ranked = rerank(item["q"], shortlist, by_id, ranker, top_k=20)
        ids = [cid for cid, _ in ranked]
        hits20 += item["gold"] in ids
        hits5 += item["gold"] in ids[:5]
    elapsed = (time.perf_counter() - t0) * 1000 / len(questions)

    return {
        "config": config,
        "chunks": len(chunks),
        "questions": len(questions),
        "recall@20": round(hits20 / len(questions), 3),
        "recall@5": round(hits5 / len(questions), 3),
        "ms_per_query": round(elapsed, 1),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="all",
                    choices=["dense_only", "hybrid", "hybrid_contextual",
                             "hybrid_contextual_rerank", "all"])
    args = ap.parse_args()
    configs = (["dense_only", "hybrid", "hybrid_contextual", "hybrid_contextual_rerank"]
               if args.config == "all" else [args.config])
    for c in configs:
        print(run(c))
