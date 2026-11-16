"""Chapter 13: deterministic replay.

Every external effect is served from the recording. An unrecorded call raises,
because a silently non-deterministic eval is worse than a failing one.
"""

from __future__ import annotations

import hashlib

# How often the stub system gets an example right, per config. Deterministic on
# the example id, so a run is reproducible and the pass rate is a real estimate.
ACCURACY = {"baseline": 0.60, "better": 0.80, "sneaky": 0.85}


def _is_correct(example_id: str, rate: float) -> bool:
    h = int(hashlib.sha256(example_id.encode()).hexdigest()[:8], 16) % 100
    return h < rate * 100


class UnrecordedToolCall(RuntimeError):
    pass


class RecordedTools:
    def __init__(self, recorded: list[str]):
        self.recorded = list(recorded)
        self.calls: list[str] = []

    def call(self, name: str, **kwargs) -> dict:
        if name not in self.recorded:
            raise UnrecordedToolCall(f"{name} was not in the recording")
        self.calls.append(name)
        return {"ok": True, "tool": name, "recorded": True}


def replay(example: dict, config: str) -> dict:
    """Run the 'system under test'. The config knob stands in for a prompt change."""
    tools = RecordedTools(example.get("tools", []))
    text = example["input"].lower()

    right = _is_correct(example["id"], ACCURACY[config])
    if config == "sneaky" and example["slice"] == "actions":
        right = False                       # the regression the slice check exists for

    output = (
        example["expected"] + " (see docs)" if right
        else "I don't have enough information to answer that."
    )

    for name in example.get("tools", []):
        tools.call(name)

    return {"output": output, "tools": tools.calls}
