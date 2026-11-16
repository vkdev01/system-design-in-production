-- Chapter 02, drill: a query without the routing key must fail loudly.
-- In the real router this raises "missing routing key workspace_id" and
-- increments dbproxy_unroutable_total. It must never fan out to all shards.
SELECT id, type FROM block WHERE space_id = gen_random_uuid() LIMIT 10;
