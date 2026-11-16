# Chapter 12 - the agent runtime

```bash
cd code/agents
python test_resume.py --kill-after 2
```

Expected output:

```
killed after 2 steps; state=running
final state      : succeeded
steps logged     : 9
external effects : 2  (must be 2: one write per file)
OK: resumed once, every effect applied exactly once
```

- `store.py` - run/step/cache tables (SQLite here, Postgres in `migrations/`),
  with `claim()` as a lease and `append()` as write-before-act.
- `runtime.py` - the loop: log the model output, execute the tool under a cache
  key, check budgets, resume from the log.
- `policy.py` - deny-by-default tool policy, plus the untrusted-read taint.
- `tools.py` - fake tools with an external effect counter, so duplicates show up.
- `test_resume.py` - kill, repair, assert exactly-once effects.
