-- Chapter 05: intent, ledger, outbox.
CREATE TABLE IF NOT EXISTS payments (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id       text NOT NULL,
    idempotency_key  text NOT NULL,
    amount_minor     bigint NOT NULL,          -- paise: never floats for money
    currency         char(3) NOT NULL,
    provider         text NOT NULL,
    provider_ref     text,
    state            text NOT NULL CHECK (state IN
                       ('pending','succeeded','failed_retryable','failed_terminal','unknown')),
    lease_expires_at timestamptz,
    attempts         integer NOT NULL DEFAULT 0,
    last_error       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS payments_stuck_idx
    ON payments (lease_expires_at)
    WHERE state IN ('pending','unknown');

CREATE TABLE IF NOT EXISTS ledger_entries (
    id           bigserial PRIMARY KEY,
    payment_id   uuid NOT NULL REFERENCES payments(id),
    account      text NOT NULL,
    direction    char(1) NOT NULL CHECK (direction IN ('debit','credit')),
    amount_minor bigint NOT NULL CHECK (amount_minor > 0),
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outbox (
    id           bigserial PRIMARY KEY,
    aggregate_id uuid NOT NULL,
    topic        text NOT NULL,
    payload      jsonb NOT NULL,
    published_at timestamptz,
    attempts     integer NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outbox_unpublished_idx
    ON outbox (id) WHERE published_at IS NULL;
