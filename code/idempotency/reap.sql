-- Chapter 04, step 4: the reaper.
-- Batched so it never holds a lock on the hot table. 72 hours covers a weekend
-- incident; Stripe's API v1 keeps keys for 24 hours, v2 for 30 days.
DELETE FROM idempotency_keys
WHERE id IN (
    SELECT id FROM idempotency_keys
    WHERE created_at < now() - interval '72 hours'
    ORDER BY created_at
    LIMIT 10000
);
