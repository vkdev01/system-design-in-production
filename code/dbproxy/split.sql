-- Chapter 03, step 3: the physical shard split, chunked.
-- Never OFFSET: chunk on a monotonic column so each batch is a fresh index scan.
COPY (
  SELECT * FROM files
  WHERE org_id >= :'lo' AND org_id < :'hi'
    AND updated_at >= :'chunk_start' AND updated_at < :'chunk_end'
) TO STDOUT WITH (FORMAT csv);
