-- Chapter 04: the idempotency key store.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    id               bigserial PRIMARY KEY,
    account_id       text        NOT NULL,
    key              text        NOT NULL,
    request_method   text        NOT NULL,
    request_path     text        NOT NULL,
    request_hash     bytea       NOT NULL,
    state            text        NOT NULL DEFAULT 'in_progress'
                     CHECK (state IN ('in_progress','succeeded','terminal','retryable')),
    locked_at        timestamptz,
    lease_expires_at timestamptz,
    response_code    integer,
    response_body    jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, key)
);

CREATE INDEX IF NOT EXISTS idempotency_keys_created_idx
    ON idempotency_keys (created_at);

CREATE INDEX IF NOT EXISTS idempotency_keys_lease_idx
    ON idempotency_keys (lease_expires_at)
    WHERE state = 'in_progress';
