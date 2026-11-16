-- Chapter 04, step 2: the atomic claim.
-- One statement, no read-then-write race. A returned row means you own the work.
INSERT INTO idempotency_keys
    (account_id, key, request_method, request_path, request_hash,
     state, locked_at, lease_expires_at)
VALUES ($1, $2, $3, $4, $5, 'in_progress', now(), now() + interval '30 seconds')
ON CONFLICT (account_id, key) DO NOTHING
RETURNING id, state;
