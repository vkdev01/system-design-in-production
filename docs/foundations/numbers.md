# Numbers you must know

You cannot design a system you cannot size. This page is the arithmetic kit for
the rest of the manual: unit conversions, hardware limits, and the soft ceilings
of the databases and brokers these thirteen chapters use. Everything is either a
published figure (linked in [Appendix C](../appendices/sources.md)) or arithmetic
you can redo on paper.

## Unit conversions, memorised

| Question | Answer | How to get it fast |
|---|---|---|
| 1 million per minute | 16,667 per second | ÷ 60 |
| 1 billion per day | 11,574 per second | ÷ 86,400 |
| 1 million per day | 11.6 per second | ÷ 86,400 |
| 1 billion per day, 5× peak | ~58,000 per second | × 5 |
| 1 TB per day | 11.6 MB/s sustained | ÷ 86,400 |
| 100k writes/s × 1 KB | 100 MB/s, 8.6 TB/day | × 86,400 |
| 1 year of seconds | 31.5 million | 365 × 86,400 |
| 1 KB × 1 billion rows | 1 TB | before replication |
| Replication factor 3 | ×3 storage | plus compaction overhead |

Two conversions cover most interview arithmetic: **divide per-day by 86,400** and
**multiply per-second by 86,400** for daily volume.

## Latency numbers, in the units that matter

Approximate, and the *ratios* matter more than the digits.

| Operation | Latency | Note |
|---|---|---|
| L1 cache reference | ~1 ns | |
| Main memory reference | ~100 ns | |
| Redis GET (same AZ) | ~0.2–0.5 ms | single round trip, in-process Lua adds ~0.1 ms |
| SSD random read (4 KB) | ~100 µs | NVMe local |
| Postgres simple indexed read (same AZ) | ~0.5–2 ms | warm cache |
| Postgres commit (synchronous, same AZ) | ~1–5 ms | fsync-bound; `synchronous_commit=off` trades durability |
| Kafka produce ack (acks=1, same AZ) | ~2–5 ms | |
| Round trip within an AZ | ~0.3–0.5 ms | |
| Round trip Mumbai ↔ Singapore | ~55–75 ms | approximate, varies with path |
| Round trip Mumbai ↔ us-east-1 | ~200–250 ms | approximate |
| Same-region S3 PUT p99 | ~50–100 ms | |

The rule that follows: **anything cross-region cannot be in a synchronous request
path with a 100 ms budget.** Replicate asynchronously and make the client sticky
to a region — which is exactly what Slack does with Gateway Servers deployed per
region.

## The soft ceilings of Postgres

These are the numbers that decide when you must shard. None of them are hard
limits; all of them are where operations start to hurt.

| Limit | Value | Why it matters |
|---|---|---|
| Comfortable table size | ~500 GB | Notion's own planning ceiling per table |
| Comfortable database size | ~10 TB | Notion's ceiling per physical database |
| `autovacuum` behaviour | degrades well before hardware limits | Notion's VACUUM began stalling, which is what forced the decision |
| TXID space | 2³¹ ≈ 2.1 billion transactions | wraparound stops **all writes**; Notion called it an existential threat |
| Practical single-node writes | ~5k–20k simple row writes/s | fsync + index maintenance bound |
| Practical single-node reads | ~10k–50k simple indexed reads/s | depends entirely on cache hit rate |
| Connections before trouble | a few hundred | hence PgBouncer; 96 databases × direct connections is not a plan |
| Replica lag under load | 10s of ms to 10s of seconds | why idempotency reads go to the **primary** (chapter 04/05) |
| Table size for a safe `ALTER TABLE` | under ~10 GB | above that, use `ALTER ... NOT VALID` + `VALIDATE CONSTRAINT` |

## The soft ceilings of the other stores

| System | Published / typical figure | Source or caveat |
|---|---|---|
| Cassandra at Discord, 2022 | 177 nodes, trillions of messages, ~4 TB disk/node | Discord |
| ScyllaDB at Discord, after migration | 72 nodes, 9 TB disk/node, 15 ms p99 read, 5 ms p99 write | Discord |
| Discord migration throughput | up to 3.2 million messages/second | Rust migrator with SQLite checkpoints |
| ScyllaDB partition guidance | keep partitions under ~100 MB, ideally under 10 MB | general rule; keeps compaction and reads sane |
| Redis single node | ~100k–200k ops/s, sub-ms | Lua scripts are atomic, one at a time |
| ElastiCache cluster mode | shard by key; each shard has its own primary | plan for `CLUSTER SLOTS` in your client |
| Kafka per broker | ~100–500 MB/s with batching, depends on disk | MSK sizing is disk- and network-bound |
| Firebase Cloud Messaging over XMPP | **100 pending requests per connection** | Discord's hard constraint in chapter 09 |
| Slack channel servers | ~16 million channels per host, message delivery in 500 ms globally | Slack |
| Slack CS replacement | new CS serving traffic in **under 20 seconds** | Slack |
| Notion shard plan | 480 logical shards over 32 physical DBs (15 each), later 96 DBs (5 each) | Notion |
| Figma before sharding | single RDS instance, ~65% CPU at peak, DB traffic growing ~3×/year | Figma |
| Figma vertical partitioning | a dozen partitioned DBs, largest at ~10% CPU, ~30 s partial availability per move | Figma |
| Uber H3 resolution 7 | 5.16 km² average hexagon, ~98.8 million cells globally | H3 docs |
| Uber H3 resolution 9 | 0.105 km² average (≈ a city block cluster) | H3 docs |

## Worked example 1: sizing a message store

Discord-like assumptions: 2 billion messages/day, average message row 200 bytes
of payload, 3× replication.

```
2e9 msgs/day × 200 B            = 400 GB/day of raw payload
+ primary key, bucket, indexes  ≈ 1.4× overhead → 560 GB/day
× replication factor 3          = 1.7 TB/day on disk
× 365 days                      = 615 TB/year
```

Compare with the real thing: 72 nodes × 9 TB = 648 TB. The arithmetic lands in the
same order of magnitude as the production cluster, which is the point of doing it
— you do not need precision, you need to know whether you are buying 6 nodes or
600.

Then check the write rate: 2e9 / 86,400 ≈ 23,000 writes/s average. With a 5× peak
that is 116,000 writes/s. Across 72 nodes that is ~1,600 writes/s per node, which
is comfortable for ScyllaDB and is exactly why the node count is 72 and not 12.

## Worked example 2: what a design decision costs

```
648 TB of gp3 EBS at $0.08/GB-month = 648,000 GB × $0.08 ≈ $51,800/month
                                     ≈ ₹45 lakh/month at ₹88/$
```

Now the counterfactual: keep 177 Cassandra nodes at 4 TB each = 708 TB, *plus* the
on-call toil of the "gossip dance" and GC tuning. The migration to fewer, denser
nodes was a cost decision as much as a latency decision. When you argue for a
design in a review, put the monthly rupee number in the slide — it changes the
conversation faster than a latency chart.

!!! tip "Do this in the interview"
    Say the arithmetic out loud, including the assumption you chose. "I'll assume
    200 bytes per message, 3× replication, so about 600 TB a year, which is
    roughly 70 nodes at 9 TB each. If messages are 1 KB instead, that's 5× the
    fleet, so the payload size is the first thing I'd check." Interviewers score
    the reasoning, not the digits.

## Connection and concurrency budget

The most common production outage in this manual's chapters is not CPU; it is
running out of connections or in-flight slots.

```
required in-flight = QPS × p99 latency (Little's Law)
example: 5,000 QPS × 0.05 s = 250 concurrent requests
```

| Resource | Typical safe limit | Guard |
|---|---|---|
| Postgres connections per instance | ~100–300 | PgBouncer in transaction mode, pool 20–50 per service |
| HTTP client keep-alive pool per dependency | 50–200 | cap it; never unbounded |
| Go goroutines per pod | 100k is fine, but bound the work behind them | semaphore or worker pool |
| WebSocket connections per gateway pod | 20k–100k depending on memory and fan-out | measure per-connection RSS (~10–50 KB) |
| Redis connections | a few per app instance | never one per request |

## Timeout budgets, written down

A chain of five calls with a 300 ms p99 SLO and a 1 s hard deadline:

| Hop | Timeout | Retries | Worst case |
|---|---|---|---|
| Edge / ingress | 1,000 ms | 0 | 1,000 ms |
| API service | 800 ms | 0 | 800 ms |
| Internal service | 300 ms | 1 retry, 50 ms backoff | 650 ms |
| Cache / Redis | 20 ms | 1 | 40 ms |
| Database statement | 250 ms | 0 | 250 ms |
| External provider | 2,000 ms | 2, exponential + jitter | outside the request path |

The invariant: **each hop's timeout is strictly smaller than its caller's**, and
retries only happen where the operation is idempotent (chapter 04). An external
provider that needs 2 s does not belong inside a 300 ms request; it belongs in an
outbox worker, which is chapter 05's whole argument.
