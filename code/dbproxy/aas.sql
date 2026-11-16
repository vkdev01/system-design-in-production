-- Chapter 03, step 1: average active sessions by table.
-- This is how Figma ranked tables for vertical partitioning: sample
-- pg_stat_activity every 10ms and aggregate by table name.
SELECT
  COALESCE((regexp_match(query, 'FROM\s+"?([a-z_]+)"?', 'i'))[1], 'other') AS table_name,
  count(*)                       AS samples,
  round(count(*) * 0.01, 2)      AS approx_active_seconds,
  count(DISTINCT pid)            AS distinct_backends
FROM pg_stat_activity
WHERE state = 'active'
  AND query NOT ILIKE '%pg_stat_activity%'
  AND backend_type = 'client backend'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 25;
