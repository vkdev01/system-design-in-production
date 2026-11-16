-- Chapter 01: shadow-read validation.
-- Run the same query against Cassandra and ScyllaDB, diff the digests.
-- Discord validated with a small percentage of live reads before cutover.

SELECT channel_id,
       bucket,
       count(*)        AS n,
       sum(message_id) AS id_sum,
       max(edited_at)  AS newest_edit
FROM chat.messages
WHERE channel_id = ? AND bucket = ?
GROUP BY channel_id, bucket;
