-- Chapter 02, step 1: which tables hang off `block`?
-- Everything reachable by a foreign key must live on the same shard, or you
-- introduce cross-database consistency bugs (Notion's block/comment example).
WITH RECURSIVE reachable(oid) AS (
    SELECT 'block'::regclass::oid
    UNION
    SELECT con.conrelid
    FROM pg_constraint con
    JOIN reachable r ON con.confrelid = r.oid
    WHERE con.contype = 'f'
)
SELECT oid::regclass AS table_name
FROM reachable
ORDER BY 1;
