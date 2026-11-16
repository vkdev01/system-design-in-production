# Chapter 13 - evals as a production system

```bash
cd code/evals
python run.py --config baseline
python run.py --config better  --baseline baseline
python run.py --config sneaky  --baseline baseline
```

Actual output on the 20-example set:

```
baseline  pass rate 0.750  CI [0.550, 0.900]   verdict: pass
better    pass rate 0.950  CI [0.850, 1.000]   verdict: no measurable change
          - overall CI [0.85,1.0] overlaps baseline
sneaky    pass rate 0.800  CI [0.600, 0.950]   verdict: fail
          - slice 'actions' down 0.75
```

Three lessons in three runs:

1. `better` is a 20-point improvement that a 20-example set **cannot resolve** —
   the gate refuses to call it a win. That is the whole argument for sample
   size.
2. `sneaky` improves the average and still fails, because one slice collapsed.
3. Both verdicts are reproducible: the stub system's correctness is a hash of
   the example id, and the judge's wobble is a hash too.

- `harness.py` - bootstrap CI, slice grouping, overlap test, verdict.
- `judge.py` - deterministic stub judge (threshold 0.55) with a small wobble.
- `replay.py` - recorded tool outputs; an unrecorded call fails loudly.
- `dataset.jsonl` - 20 examples across 5 slices.
