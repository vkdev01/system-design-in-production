# Chapter 10 - LLM inference serving

```bash
cd code/inference
python bench.py --requests 60 --arrival-rate 8
# mode=naive  tokens_per_s=150.7  ttft_p50_ms=16582  kv_util=0.503  preemptions=0
# mode=paged  tokens_per_s=738.0  ttft_p50_ms=2706   kv_util=0.831  preemptions=5
```

- `blocks.py` - paged KV allocator with a `check()` invariant; unit-test it.
- `scheduler.py` - continuous batching: admit on free blocks, chunked prefill,
  preempt the youngest request.
- `engine.py` - stub engine whose timing has the right *shape* (prefill compute
  bound, decode fixed per step), so the scheduler is testable without a GPU.
- `bench.py` - naive (one at a time, reserve max_len) versus paged.

Read the chapter: `docs/chapters/10-llm-inference-serving.md`.
