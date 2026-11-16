"""Chapter 10: a stub engine with GPU-shaped timing.

No GPU required: prefill costs time proportional to prompt tokens (compute
bound), decode costs a fixed time per step (bandwidth bound). That is enough to
exercise admission, chunking and preemption.
"""

from __future__ import annotations

import time


class StubEngine:
    def __init__(self, prefill_tok_per_s: float = 20_000, decode_step_ms: float = 5.0):
        self.prefill_rate = prefill_tok_per_s
        self.decode_ms = decode_step_ms
        self.prefill_tokens = 0
        self.decode_steps = 0

    def prefill(self, req, start: int, count: int) -> None:
        time.sleep(count / self.prefill_rate)
        self.prefill_tokens += count

    def decode(self, batch) -> list[int]:
        time.sleep(self.decode_ms / 1000.0)
        self.decode_steps += 1
        return [self._next_token(r) for r in batch]

    @staticmethod
    def _next_token(req) -> int:
        # deterministic fake vocabulary: cycle so EOS is reachable
        return 0 if req.generated + 1 >= req.max_new_tokens else (req.generated % 100) + 1
