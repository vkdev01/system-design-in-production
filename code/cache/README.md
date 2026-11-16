# Chapter 16 - the cache tier

```bash
cd code/cache
python race.py --strategy set      # strategy=set     final cache value=v1     STALE
python race.py --strategy delete   # strategy=delete  final cache value=v2     correct
python budget.py --reads 100000 --db-capacity 2000
```

- `aside.py` - cache-aside with a single-flight lease and jittered TTLs.
- `race.py` - the set-versus-delete race, executable: same interleaving, two
  outcomes.
- `budget.py` - the miss-rate table to paste into the alert description.
