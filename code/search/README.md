# Chapter 15 - search: inverted index to ranking

```bash
cd code/search
python bench.py --docs 8000 --queries 100
```

```
docs 8,000  terms 81  shards 3
build 2,213 ms  (0.277 ms per doc)
query p50 44.94 ms   p99 67.63 ms
recall@20 0.956
```

The latency here is Python, not the algorithm: a real engine skips candidates
with block-max WAND instead of scoring all of them. What the numbers do show is
the part that matters — **recall@20 of 0.956**, which is the measurement that
makes approximate top-k defensible.

- `index.py` - postings with positions, tombstones, BM25 with the formula the
  chapter names, and a bounded heap for top-k.
- `cluster.py` - hash-sharded indexes with a scatter-gather that returns at most
  k per shard.
- `bench.py` - build cost, p50/p99 query latency, and recall@20 against a brute
  force scan (the number that makes approximate top-k defensible).
