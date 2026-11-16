# Chapter 01 - chat message storage

```bash
docker compose -f deploy/compose/chat-storage.yml up --build
curl 'localhost:8080/messages?channel_id=1001&limit=50'
k6 run --vus 200 --duration 60s code/chat-storage/loadtest/hot_channel.js
```

- `schema.cql` - the primary key is the design: `((channel_id, bucket), message_id)`.
- `coalesce.go` - N concurrent readers of one row become one query.
- `main.go` - the data service: one endpoint per query, no business logic.
- `migration/` - shadow-read validation and the tombstone-storm drill.

Read the chapter: `docs/chapters/01-chat-message-storage.md`.
