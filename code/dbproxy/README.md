# Chapter 03 - scaling Postgres without rewriting the app

```bash
go run ./code/dbproxy            # reads SHARD_MAP_PATH, default /etc/shardmap/map.json
```

- `shardmap.go` - the routing decision, plus the refusal to downgrade a map
- `main.go` - pools per shard, 250ms query timeout, `dbproxy_unroutable_total`
- `map.json` - an example shard map (table -> shard key, shard -> DSN)
- `aas.sql` - average active sessions per table, how Figma ranked tables
- `split.sql`, `schema_migrations.sql` - the physical split and cross-shard DDL
