-- Chapter 02: verify a backfill. Run against the monolith and the sharded
-- fleet; the digests must match for the same watermark.
SELECT count(*)                                                  AS rows,
       sum(('x' || substr(md5(id::text), 1, 8))::bit(32)::bigint) AS id_digest,
       max(updated_at)                                           AS newest
FROM block
WHERE updated_at < :'watermark';
