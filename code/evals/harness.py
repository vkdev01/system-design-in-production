"""Chapter 13: pass rate with a confidence interval, per slice, plus a gate."""

from __future__ import annotations

import random
import statistics


def bootstrap_ci(flags: list[bool], n: int = 2000, seed: int = 7) -> dict:
    """Resample the pass/fail vector; report the 2.5th and 97.5th percentiles."""
    if not flags:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    rng = random.Random(seed)
    k = len(flags)
    means = []
    for _ in range(n):
        sample = [flags[rng.randrange(k)] for _ in range(k)]
        means.append(sum(sample) / k)
    means.sort()
    return {
        "mean": round(sum(flags) / k, 3),
        "lo": round(means[int(0.025 * n)], 3),
        "hi": round(means[int(0.975 * n)], 3),
        "n": k,
    }


def group_by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def overlaps(a: dict, b: dict) -> bool:
    return not (a["hi"] < b["lo"] or b["hi"] < a["lo"])


def evaluate(rows: list[dict], baseline: dict | None = None, slice_drop: float = 0.03) -> dict:
    overall = bootstrap_ci([r["passed"] for r in rows])
    slices = {name: bootstrap_ci([r["passed"] for r in group])
              for name, group in group_by(rows, "slice").items()}

    verdict = "pass"
    reasons: list[str] = []
    if baseline:
        if overlaps(overall, baseline["overall"]):
            verdict = "no measurable change"
            reasons.append(f"overall CI [{overall['lo']},{overall['hi']}] overlaps baseline")
        for name, ci in slices.items():
            base = baseline["slices"].get(name)
            if base and ci["mean"] < base["mean"] - slice_drop:
                verdict = "fail"
                reasons.append(f"slice '{name}' down {base['mean'] - ci['mean']:.2f}")

    return {"overall": overall, "slices": slices, "verdict": verdict, "reasons": reasons}
