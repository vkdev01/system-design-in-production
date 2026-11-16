-- Chapter 01, drill 3: the bug that stalled Discord's migration at 99.9999%.
-- Deleting a large range inside one partition creates a tombstone range that
-- every subsequent read must scan. Run this, then read the partition and watch
-- the latency (and the tombstone warnings) in the logs.

DELETE FROM chat.messages
WHERE channel_id = 1001 AND bucket = 19000
  AND message_id > 0 AND message_id < 5000000;

-- The fix is compaction of that token range; in a running cluster:
--   nodetool compact chat messages <token-range>
SELECT * FROM chat.messages WHERE channel_id = 1001 AND bucket = 19000 LIMIT 10;
