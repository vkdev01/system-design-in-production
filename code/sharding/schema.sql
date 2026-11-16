-- Chapter 02: one logical shard. Run once per shard with the schema name
-- templated (schema001 ... schema015 on each physical database).
--
-- psql -v schema=schema001 -f code/sharding/schema.sql

\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS :"schema";

CREATE TABLE IF NOT EXISTS :"schema".space (
    id           uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    name         text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS :"schema".block (
    id           uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,          -- denormalised routing key, on every table
    space_id     uuid NOT NULL REFERENCES :"schema".space(id),
    parent_id    uuid,
    type         text NOT NULL,
    properties   jsonb NOT NULL DEFAULT '{}',
    alive        boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS block_space_alive_idx
    ON :"schema".block (workspace_id, space_id, id)
    WHERE alive;

CREATE TABLE IF NOT EXISTS :"schema".discussion (
    id           uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    block_id     uuid NOT NULL REFERENCES :"schema".block(id),
    resolved     boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS :"schema".comment (
    id            uuid PRIMARY KEY,
    workspace_id  uuid NOT NULL,
    discussion_id uuid NOT NULL REFERENCES :"schema".discussion(id),
    author_id     uuid NOT NULL,
    body          text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Every shard records which migrations it has seen.
CREATE TABLE IF NOT EXISTS :"schema".schema_migrations (
    version    integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now(),
    duration_ms integer
);
