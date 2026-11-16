# Chapter 07 - realtime messaging

```bash
go run ./code/realtime/cmd/gateway --ring=cs-0,cs-1,cs-2
go run ./code/realtime/cmd/slowclient      # drill: a client that never reads
```

| File | Role |
|---|---|
| `ring.go` | consistent hash ring with virtual nodes and a version |
| `gateway.go` | sockets, bounded outbound queues, slow-consumer policy |
| `subscribe.go` | subscription setup, jittered retries, drain on SIGTERM |
| `channelserver.go` | ownership check, ring-version check, bounded fan-out |
| `types.go` | the gRPC seams and the metrics |

The two invariants: a channel server writes only what it owns, and never blocks
on a slow gateway.
