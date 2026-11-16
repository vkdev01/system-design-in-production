"""Chapter 12: the durable agent loop.

The model is a scripted stub so the run is reproducible; everything that makes
it production-grade is real: lease, append-before-act, cached tool results,
budgets, and resume from the log.
"""

from __future__ import annotations

from policy import allows, mark_untrusted_read, reset
from store import Store
from tools import TOOLS

MAX_STEPS = 200
MAX_COST = 5.0
COST_PER_STEP = 0.05


class ScriptedModel:
    """A fake model: a fixed plan, so the test is deterministic."""

    def __init__(self, plan: list[dict], final: str = "done"):
        self.plan = plan
        self.final = final

    def complete(self, ctx: dict) -> dict:
        i = ctx["step_index"]
        if i < len(self.plan):
            return {"type": "tool", "call": self.plan[i], "tokens": 1200}
        return {"type": "final", "content": self.final, "tokens": 800}


def build_context(store: Store, run: dict) -> dict:
    history = store.steps(run["id"])
    return {
        "task": run["task"],
        "step_index": len([s for s in history if s["kind"] == "model"]),
        "history": history[-10:],
        "summary": run["summary"],
    }


def execute(store: Store, run: dict, model: ScriptedModel) -> str:
    if not store.claim(run["id"]):
        return "leased_elsewhere"

    ctx = build_context(store, run)
    msg = model.complete(ctx)

    # 1. log the model output BEFORE any side effect
    seq = store.append(run["id"], "model", msg)

    if msg["type"] == "final":
        store.finish(run["id"], "succeeded")
        return "succeeded"

    call = msg["call"]
    ok, why = allows(call["name"])
    if not ok:
        store.append(run["id"], "denied", {"call": call, "why": why})
        store.release(run["id"])
        return "continue"

    # 2. idempotent tool execution, keyed on (run, seq, index)
    key = f"{run['id']}:{seq}:0"
    cached = store.cache_get(key)
    if cached is None:
        result = TOOLS[call["name"]](**call.get("args", {}))
        store.cache_put(key, result)
    else:
        result = cached
    store.append(run["id"], "tool", result, tool_name=call["name"])

    if call["name"] == "read_web":
        mark_untrusted_read()

    # 3. budgets, checked every step
    run = store.get(run["id"])
    if run["steps"] >= min(run["max_steps"], MAX_STEPS) or run["steps"] * COST_PER_STEP > run["max_cost_usd"]:
        store.finish(run["id"], "budget_exhausted")
        return "budget_exhausted"

    store.release(run["id"])          # step finished; hand the lease back
    return "continue"


def repair(store: Store, model: ScriptedModel) -> list[str]:
    """Resume every run whose lease expired."""
    resumed = []
    for rid in store.stuck():
        store.db.execute("UPDATE runs SET lease_expires=NULL WHERE id=?", (rid,))
        run = store.get(rid)
        while True:
            outcome = execute(store, run, model)
            if outcome != "continue":
                break
            run = store.get(rid)
        resumed.append(rid)
    return resumed
