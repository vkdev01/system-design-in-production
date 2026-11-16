-- Chapter 03, step 4: schema changes across N shards.
-- One row per (shard, version). The orchestrator applies to a canary shard,
-- soaks, then batches of 10 with a concurrency cap, and halts on first error.
CREATE TABLE IF NOT EXISTS schema_migrations (
    shard       text        NOT NULL,
    version     integer     NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    duration_ms integer,
    PRIMARY KEY (shard, version)
);

-- Which shards are behind?
SELECT version, count(*) AS shards, min(applied_at) AS first, max(applied_at) AS last
FROM schema_migrations
GROUP BY version
ORDER BY version DESC;
