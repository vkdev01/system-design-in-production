"""Chapter 12: the only test that matters.

    python test_resume.py

Kills the worker after N steps, runs the repair loop, then asserts:
  * the run reaches a terminal state
  * the external effect counter is exactly 1  <- no duplicate side effects
"""

from __future__ import annotations

import argparse

import policy
import tools
from runtime import ScriptedModel, execute, repair
from store import Store

PLAN = [
    {"name": "write_file", "args": {"path": "solution.py", "content": "x = 1"}},
    {"name": "run_tests", "args": {"suite": "unit"}},
    {"name": "slow_tool", "args": {"seconds": 0.05}},
    {"name": "write_file", "args": {"path": "README.md", "content": "done"}},
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kill-after", type=int, default=2)
    args = ap.parse_args()

    tools.EFFECTS.clear()
    tools.CALLS.clear()
    policy.reset()

    store = Store()
    rid = store.create("fix the failing test")
    model = ScriptedModel(PLAN, final="all tests pass")

    # --- phase 1: run until the "crash" ---
    for _ in range(args.kill_after):
        execute(store, store.get(rid), model)
    print(f"killed after {args.kill_after} steps; state={store.get(rid)['state']}")

    # --- phase 2: the lease expires, the repair loop resumes ---
    store.db.execute("UPDATE runs SET lease_expires = 0 WHERE id=?", (rid,))
    repair(store, model)

    run = store.get(rid)
    effects = tools.EFFECTS.get("solution.py", 0) + tools.EFFECTS.get("README.md", 0)

    print(f"final state      : {run['state']}")
    print(f"steps logged     : {run['steps']}")
    print(f"external effects : {effects}  (must be 2: one write per file)")
    print(f"tool calls       : {len(tools.CALLS)}")

    assert run["state"] == "succeeded", run["state"]
    assert effects == 2, f"duplicate side effect: {tools.EFFECTS}"
    print("OK: resumed once, every effect applied exactly once")


if __name__ == "__main__":
    main()
