# Chapter 02 - sharding Postgres

```bash
# 1. Create 15 logical shards inside one physical database.
for i in $(seq -w 1 15); do
  psql "$DATABASE_URL" -v schema="schema$i" -f schema.sql
done

# 2. Check the router's distribution.
python router.py

# 3. Plan the migration: walk the foreign-key graph.
psql "$DATABASE_URL" -f fk_graph.sql

# 4. Verify a backfill window.
psql "$DATABASE_URL" -v watermark="2026-01-01" -f verify.sql
```

The router is deliberately boring: SHA-256 of the workspace UUID, modulo 480,
then integer division to pick a physical database. No central lookup on the hot
path, no cache to go stale, and the same function in every language.
