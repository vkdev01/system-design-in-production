"""Chapter 15: build an index, query it, and measure.

    python bench.py --docs 20000 --queries 200

Reports index size, p50/p99 query latency, and recall@20 against a brute-force
scan -- because approximate top-k is only acceptable if you measure the recall.
"""

from __future__ import annotations

import argparse
import random
import statistics
import time

from cluster import Cluster
from index import Index, analyse

WORDS = ("postgres redis kafka scylla shard cache index latency timeout retry "
         "queue lease lock idempotency partition replica quorum compaction "
         "vector embedding retrieval rerank chunk token context agent budget").split()


def make_doc(rng: random.Random, n_terms: int = 120) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n_terms))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=20000)
    ap.add_argument("--queries", type=int, default=200)
    args = ap.parse_args()

    rng = random.Random(7)
    cluster = Cluster(shards=3)
    t0 = time.perf_counter()
    for i in range(args.docs):
        cluster.add(f"doc{i}", make_doc(rng))
    build_ms = (time.perf_counter() - t0) * 1000

    stats = cluster.stats()
    print(f"docs {stats['docs']:,}  terms {stats['terms']:,}  shards {stats['shards']}")
    print(f"build {build_ms:,.0f} ms  ({build_ms / args.docs:.3f} ms per doc)")

    queries = [" ".join(rng.sample(WORDS, 2)) for _ in range(args.queries)]
    times = []
    for q in queries:
        t = time.perf_counter()
        cluster.search(q, k=20)
        times.append((time.perf_counter() - t) * 1000)

    times.sort()
    print(f"query p50 {statistics.median(times):.2f} ms   p99 {times[int(0.99 * len(times))]:.2f} ms")

    # recall against a brute-force scan of one shard's documents
    shard = cluster.shards[0]
    hits = 0
    for q in queries[:50]:
        terms = analyse(q)
        truth = sorted(
            ((d, shard.bm25(d, terms)) for d in shard.lengths if d not in shard.tombstones),
            key=lambda kv: -kv[1],
        )[:20]
        got = [d for d, _ in shard.search(q, k=20)]
        hits += len(set(got) & {d for d, _ in truth}) / max(1, len(truth))
    print(f"recall@20 {hits / 50:.3f}")


if __name__ == "__main__":
    main()
