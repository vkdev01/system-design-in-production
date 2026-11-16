"""Chapter 10: naive vs paged scheduling, on a stub engine.

    python bench.py --requests 200 --arrival-rate 8 --max-len 2048

Prints tokens/s, time-to-first-token percentiles, KV utilisation and
preemptions for both modes. On the stub the paged scheduler should show roughly
2-3x the throughput and >90% KV utilisation against ~35% for the naive one --
the same shape as the published result, without a GPU.
"""

from __future__ import annotations

import argparse
import random
import statistics
import time

from blocks import BlockAllocator
from engine import StubEngine
from scheduler import Request, Scheduler


def run_paged(n: int, arrival_rate: float, max_len: int, num_blocks: int, block_size: int):
    alloc = BlockAllocator(num_blocks=num_blocks, block_size=block_size)
    engine = StubEngine()
    sched = Scheduler(alloc, engine, chunk_size=512)
    rng = random.Random(7)

    t0 = time.perf_counter()
    pending = [(i, t0 + i / arrival_rate) for i in range(n)]
    util_samples: list[float] = []
    i = 0
    while len(sched.completed) < n:
        now = time.perf_counter()
        while i < n and pending[i][1] <= now:
            rid = pending[i][0]
            prompt = rng.choice([128, 512, 1024, 2048, 4096])
            sched.submit(Request(rid=rid, prompt_len=min(prompt, max_len), max_new_tokens=128))
            i += 1
        sched.step(now)
        util_samples.append(alloc.utilisation())
        if i >= n and not sched.batch and not sched.queue:
            break
    elapsed = time.perf_counter() - t0
    done = sched.completed
    ttfts = [r.first_token_at - t0 for r in done if r.first_token_at]
    return {
        "mode": "paged",
        "tokens_per_s": round(sum(r.generated for r in done) / elapsed, 1),
        "ttft_p50_ms": round(statistics.median(ttfts) * 1000, 1) if ttfts else 0,
        "ttft_p95_ms": round(sorted(ttfts)[int(0.95 * len(ttfts))] * 1000, 1) if ttfts else 0,
        "kv_util": round(sum(util_samples) / len(util_samples), 3),
        "preemptions": sched.preemptions,
    }


def run_naive(n: int, arrival_rate: float, max_len: int, num_blocks: int, block_size: int):
    """One request at a time, reserving max_len worth of cache up front."""
    engine = StubEngine()
    rng = random.Random(7)
    alloc = BlockAllocator(num_blocks=num_blocks, block_size=block_size)

    t0 = time.perf_counter()
    tokens = 0
    ttfts = []
    waste: list[float] = []
    for i in range(n):
        prompt = rng.choice([128, 512, 1024, 2048, 4096])
        prompt = min(prompt, max_len)
        reserved = alloc.blocks_for(max_len)            # the naive reservation
        used = alloc.blocks_for(prompt)
        waste.append(used / reserved)
        alloc.allocate(min(reserved, alloc.free_blocks()))
        engine.prefill(None, 0, prompt)
        start = time.perf_counter()
        for _ in range(128):
            engine.decode([type("R", (), {"generated": 0, "max_new_tokens": 128})()])
        ttfts.append(start - t0)
        tokens += 128
        alloc.free_all(list(alloc.ref_count.keys()))
        time.sleep(1 / arrival_rate)
    elapsed = time.perf_counter() - t0
    return {
        "mode": "naive",
        "tokens_per_s": round(tokens / elapsed, 1),
        "ttft_p50_ms": round(statistics.median(ttfts) * 1000, 1),
        "ttft_p95_ms": round(sorted(ttfts)[int(0.95 * len(ttfts))] * 1000, 1),
        "kv_util": round(sum(waste) / len(waste), 3),
        "preemptions": 0,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=60)
    ap.add_argument("--arrival-rate", type=float, default=8.0)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--blocks", type=int, default=512)
    ap.add_argument("--block-size", type=int, default=16)
    args = ap.parse_args()

    for row in (
        run_naive(args.requests, args.arrival_rate, args.max_len, args.blocks, args.block_size),
        run_paged(args.requests, args.arrival_rate, args.max_len, args.blocks, args.block_size),
    ):
        print("  ".join(f"{k}={v}" for k, v in row.items()))
