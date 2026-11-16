-- Chapter 12: the durable run log.
CREATE TABLE IF NOT EXISTS runs (
    id            text PRIMARY KEY,
    task          text NOT NULL,
    state         text NOT NULL DEFAULT 'pending'
                  CHECK (state IN ('pending','running','waiting_approval',
                                   'succeeded','failed','budget_exhausted')),
    steps         integer NOT NULL DEFAULT 0,
    tokens        bigint  NOT NULL DEFAULT 0,
    cost_usd      numeric(10,4) NOT NULL DEFAULT 0,
    max_steps     integer NOT NULL DEFAULT 200,
    max_cost_usd  numeric(10,4) NOT NULL DEFAULT 5,
    lease_expires timestamptz,
    summary       text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS steps (
    run_id     text NOT NULL REFERENCES runs(id),
    seq        integer NOT NULL,
    kind       text NOT NULL CHECK (kind IN ('model','tool','denied','error')),
    tool_name  text,
    payload    jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, seq)          -- append-only and idempotent
);

CREATE TABLE IF NOT EXISTS tool_cache (
    key        text PRIMARY KEY,        -- run_id:seq:index
    result     jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS runs_lease_idx ON runs (lease_expires)
    WHERE state = 'running';
