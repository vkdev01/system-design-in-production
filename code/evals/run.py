"""Chapter 13: the eval run, as CI would call it.

    python run.py --config baseline
    python run.py --config better --baseline baseline
    python run.py --config sneaky --baseline baseline
"""

from __future__ import annotations

import argparse
import json

from harness import evaluate
from judge import StubJudge
from replay import UnrecordedToolCall, replay


def load(path: str = "dataset.jsonl") -> list[dict]:
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def run(config: str, judge: StubJudge | None = None) -> list[dict]:
    judge = judge or StubJudge()
    rows = []
    for ex in load():
        try:
            res = replay(ex, config)
        except UnrecordedToolCall as e:
            rows.append({**ex, "passed": False, "error": str(e)})
            continue
        verdict = judge.score(ex, res["output"])
        rows.append({**ex, "passed": verdict["passed"], "score": verdict["score"]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="baseline", choices=["baseline", "better", "sneaky"])
    ap.add_argument("--baseline", default=None, choices=["baseline", "better", "sneaky"])
    args = ap.parse_args()

    rows = run(args.config)
    baseline = None
    if args.baseline:
        base_rows = run(args.baseline)
        baseline = evaluate(base_rows)

    report = evaluate(rows, baseline)
    o = report["overall"]
    print(f"config      : {args.config}")
    print(f"pass rate   : {o['mean']:.3f}  95% CI [{o['lo']:.3f}, {o['hi']:.3f}]  n={o['n']}")
    print("slices      : " + "  ".join(f"{k}={v['mean']:.2f}" for k, v in sorted(report["slices"].items())))
    print(f"verdict     : {report['verdict']}")
    for r in report["reasons"]:
        print(f"  - {r}")


if __name__ == "__main__":
    main()
