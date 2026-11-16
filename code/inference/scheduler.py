"""Chapter 10: continuous batching.

One scheduler iteration per *decode step*, not per request. Admit whenever free
blocks allow, chunk prefill so a long prompt cannot stall everyone's next token,
and preempt the youngest request when memory runs out.
"""

from __future__ import annotations

import collections
import dataclasses

from blocks import BlockAllocator, OutOfBlocks


@dataclasses.dataclass
class Request:
    rid: int
    prompt_len: int
    max_new_tokens: int = 128
    generated: int = 0
    prefill_cursor: int = 0
    blocks: list[int] = dataclasses.field(default_factory=list)
    first_token_at: float | None = None
    finished_at: float | None = None
    preempted: int = 0

    def needs_new_page(self, block_size: int) -> bool:
        return (self.generated + 1) % block_size == 0

    def finished(self) -> bool:
        return self.generated >= self.max_new_tokens


class Scheduler:
    def __init__(self, alloc: BlockAllocator, engine, chunk_size: int = 512):
        self.alloc = alloc
        self.engine = engine
        self.chunk_size = chunk_size
        self.queue: collections.deque[Request] = collections.deque()
        self.batch: list[Request] = []
        self.completed: list[Request] = []
        self.preemptions = 0

    def submit(self, req: Request) -> None:
        self.queue.append(req)

    def step(self, now: float) -> None:
        # 1. admit while memory allows
        while self.queue:
            head = self.queue[0]
            need = self.alloc.blocks_for(head.prompt_len) - len(head.blocks)
            if need > self.alloc.free_blocks():
                break
            self.queue.popleft()
            head.blocks += self.alloc.allocate(need)
            self.batch.append(head)

        # 2. chunked prefill, so decode is not starved by a 30k-token prompt
        for r in list(self.batch):
            if r.prefill_cursor < r.prompt_len:
                chunk = min(self.chunk_size, r.prompt_len - r.prefill_cursor)
                self.engine.prefill(r, r.prefill_cursor, chunk)
                r.prefill_cursor += chunk

        # 3. one decode step for everyone past prefill
        decoders = [r for r in self.batch if r.prefill_cursor >= r.prompt_len]
        if decoders:
            for r, tok in zip(decoders, self.engine.decode(decoders)):
                if r.first_token_at is None:
                    r.first_token_at = now
                if r.needs_new_page(self.alloc.block_size):
                    try:
                        r.blocks += self.alloc.allocate(1)
                    except OutOfBlocks:
                        self._preempt(r, now)
                        continue
                r.generated += 1
                if r.finished():
                    self.alloc.free_all(r.blocks)
                    r.finished_at = now
                    self.batch.remove(r)
                    self.completed.append(r)

        # 4. dry and work waiting: preempt the youngest, but never the only
        #    request in the batch -- there is nothing to gain and it livelocks.
        if self.alloc.free_blocks() == 0 and self.queue and len(self.batch) > 1:
            victim = min(self.batch, key=lambda r: r.generated)
            self._preempt(victim, now)

    def _preempt(self, req: Request, now: float) -> None:
        self.preemptions += 1
        req.preempted += 1
        self.alloc.free_all(req.blocks)
        req.blocks = []
        req.prefill_cursor = 0
        req.generated = 0
        if req in self.batch:
            self.batch.remove(req)
        self.queue.appendleft(req)          # resume from the front
