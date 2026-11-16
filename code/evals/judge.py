"""Chapter 13: a judge you can calibrate.

A real judge is an LLM with a rubric. This stub scores token overlap against the
expected answer and adds a deterministic pseudo-random wobble, so:
  * runs are reproducible (same input, same verdict)
  * the judge is imperfect, like a real one, which is the point
Swap `StubJudge` for a model call and the harness is unchanged.
"""

from __future__ import annotations

import hashlib
import re


def tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


class StubJudge:
    def __init__(self, threshold: float = 0.55, noise: float = 0.08):
        self.threshold = threshold
        self.noise = noise

    def _wobble(self, example_id: str) -> float:
        h = int(hashlib.sha256(example_id.encode()).hexdigest()[:8], 16)
        return (h % 1000) / 1000.0 * self.noise      # 0..noise, deterministic

    def score(self, example: dict, output: str) -> dict:
        exp = tokens(example["expected"])
        got = tokens(output)
        overlap = len(exp & got) / max(1, len(exp))
        value = min(1.0, overlap + self._wobble(example["id"]))
        return {"passed": value >= self.threshold, "score": round(value, 3)}
