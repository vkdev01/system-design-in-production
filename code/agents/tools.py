"""Chapter 12: fake tools with an external effect counter.

`EFFECTS` is the ground truth for the drill: after a kill-and-resume, it must
still be 1. A second execution is a duplicate side effect, which is exactly the
bug the tool cache exists to prevent.
"""

from __future__ import annotations

import time

EFFECTS: dict[str, int] = {}
CALLS: list[str] = []


def write_file(path: str, content: str = "") -> dict:
    CALLS.append(f"write_file:{path}")
    EFFECTS[path] = EFFECTS.get(path, 0) + 1
    return {"ok": True, "path": path, "bytes": len(content)}


def run_tests(suite: str = "unit") -> dict:
    CALLS.append(f"run_tests:{suite}")
    return {"ok": True, "passed": 42, "failed": 0}


def slow_tool(seconds: float = 0.2) -> dict:
    """Simulates a tool that does its work and then times out."""
    time.sleep(seconds)
    return {"ok": True, "slept": seconds}


TOOLS = {"write_file": write_file, "run_tests": run_tests, "slow_tool": slow_tool}
