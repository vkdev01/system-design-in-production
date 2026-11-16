"""Insert a sizing + benchmark section into each chapter.

Sits between "4. The flow chart" and "5. Build it": the flow chart says which
components exist, this section says how big each one is and what it must
benchmark at. Sections after it are renumbered.
"""

import pathlib
import re

SECTIONS = {
"chapters/01-chat-message-storage.md": """
## 5. Sizing the components

The flow chart tells you which boxes exist; this is where each box gets a number. Every figure
below comes from the peak demand in section 2, so if the assumptions change the table changes.

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| Data service | coalesced read request | ~20k req/s per 8-vCPU pod | 400k req/s (4× writes) | 24 pods, `c7g.2xlarge` | 1.2× |
| ScyllaDB nodes | one 200 B row, RF=3 | ~1,600 writes/s per node at 15 ms p99 | 116k writes/s | 72 nodes, 9 TB NVMe | 1.6× on throughput; sized by storage |
| Storage queries | 1 query per coalesced key | 8:1 coalescing on hot channels | 50k queries/s | same 72 nodes | 14× |
| Ingest | 1.7 TB/day on disk | 9 TB per node, ~5 days hot | 615 TB/year | 72 nodes = 648 TB | ~1 year before a new rack |
| Compaction | 1-day time windows | ≤ 1 h backlog | 1.7 TB/day rewritten | `TimeWindowCompactionStrategy` | the metric that matters |

**Bytes on the wire.** Little's Law again, but counted in bytes rather than requests:

- client → API: 116k writes/s × 350 B = **41 MB/s**
- API → data service: 400k reads/s × 120 B request = **48 MB/s in**, 400k × 1.5 KB = **600 MB/s out**
- data service → ScyllaDB: 50k coalesced queries/s × 1.5 KB = **75 MB/s** (this is the 8:1 saving)
- ScyllaDB replication: 116k writes/s × 200 B × 3 replicas = **70 MB/s of cross-node traffic**

The gap between 600 MB/s and 75 MB/s is the entire argument for the coalescing tier. Quote those
two numbers together in a review and nobody asks why the extra service exists.

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| p99 history read | k6 against `/messages`, one channel | ≤ 15 ms | the number the migration was for |
| p99 insert | same load test, write path | ≤ 5 ms | protects the 200 ms end-to-end budget |
| Coalescing ratio | `coalescer_hits / storage_queries` | ≥ 8:1 on hot channels | routing is actually working |
| Dropped mutations | `scylla_database_dropped_mutations` | 0 | the cluster is shedding writes it cannot absorb |
| Compaction backlog | pending compaction bytes | < 1 h of ingest | the death spiral starts here |
""",

"chapters/02-sharding-postgres.md": """
## 5. Sizing the components

Sharding moves the bottleneck from one machine to a fleet, so the sizing question changes from
"how big is the instance" to "how many, and what is the per-shard number".

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| Physical databases | one query | 16k provisioned IOPS | 312 queries/s each | 96 × `db.r6g.4xlarge` | 25× on IOPS |
| Logical shards | one schema | 5 shards per database | 62 queries/s each | 480 shards | — |
| Storage | one block row ≈ 1 KB | 500 GB per table, 10 TB per DB | 200 B rows ≈ 200 TB | 96 DBs × 2 TB | 2.1 TB used of 10 TB |
| Per-shard table | `block` per schema | 416 GB per shard's block table | 200 TB total | under the 500 GB cap | 1.2× |
| PgBouncer | client connection | 25 server connections per DB | 4,000 app connections | 8 pods, transaction pooling | 3× |
| Backfill | row copy | ~5k rows/s per worker | 200 B rows | 200 workers | ~2.3 days |

The arithmetic worth showing: 200 TB ÷ 96 databases = **2.1 TB per database**, and ÷ 5 shards =
**416 GB per shard's `block` table** — just under the 500 GB ceiling. That is not a coincidence;
it is how the shard count was chosen.

**Bytes on the wire.**

- app → PgBouncer: 30k queries/s × 1.5 KB request = **45 MB/s in**, 30k × 2 KB = **60 MB/s out**
- PgBouncer → Postgres: same 60 MB/s, but over only ~2,400 server connections instead of 4,000
- Multi-AZ replication: 1.5× the write volume, ~**15 MB/s** per database at peak

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| p99 query | `pg_stat_statements` histogram per shard | ≤ 20 ms | user-visible latency |
| Replica lag | `pg_last_wal_replay_lsn` age | < 1 s | stale reads, and idempotency bugs (ch 04) |
| TXID age | `age(datfrozenxid)` | < 1.5 B | wraparound is the existential risk |
| Autovacuum | dead-tuple % and vacuum duration | never stalling | the exact signal that forced sharding |
| Shard skew | queries per shard, max ÷ average | < 2× | a bad key makes one shard the new monolith |
""",

"chapters/03-scaling-postgres-figma.md": """
## 5. Sizing the components

The proxy adds a hop, so it needs its own capacity plan — and the plan has to be expressed per
shard, because that is the unit you scale.

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| DBProxy | one routed query | ~5k queries/s per pod | 15k queries/s | 6 pods | 2× |
| Server connections | one pooled connection | 40 per shard per pod | 8 files shards | 6 × 320 = 1,920 | 160 per shard, against 800 |
| `files` shards | one query | 750 queries/s per shard | 6k queries/s (40% of traffic) | 8 × `db.r6g.8xlarge` | 4× |
| Vertical partitions | one database | — | 15k queries/s total | 4 databases, sized per table group | largest at ~10% CPU |
| Schema migrations | one DDL per shard | — | 12 shards | orchestrator, canary first | — |

**Bytes on the wire.**

- app → DBProxy: 15k queries/s × 2 KB = **30 MB/s in**, 15k × 4 KB = **60 MB/s out**
- DBProxy adds ~1.2 KB of framing per query at the wire-protocol level: **+18 MB/s**, which is why
  the proxy is scaled on connections rather than CPU
- replication to standbys: 1.5× write volume per partition

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| Added proxy latency | compare p99 with and without DBProxy | < 1 ms | the hop must be invisible |
| Unroutable queries | `dbproxy_unroutable_total` | 0 | a code path forgot the shard key |
| Cross-shard queries | `dbproxy_cross_shard_queries` | 0 on the request path | scatter-gather appeared |
| Per-shard AAS skew | average active sessions, max ÷ avg | < 2× | the shard key is skewed |
| Shard-split impact | partial availability during a flip | < 30 s | the number to quote before you flip |
""",

"chapters/04-idempotent-payment-api.md": """
## 5. Sizing the components

An idempotency layer adds one write per phase to the hottest path you own, so size it as a write
system, not as a cache.

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| Claim | 1 `INSERT … ON CONFLICT` | ~6k key writes/s per `r6g.2xlarge` | 3,000 ops/s (500 charges × 1.5 retries) | 1 primary, `r6g.4xlarge` | 3× |
| Finish | 1 `UPDATE` + stored response | same | 500/s | same primary | 12× |
| Key table | ~500 B per row | 72 h retention | 43.2 M rows/day | ~130 M rows, 65 GB | flat, if the reaper runs |
| Reaper | batched `DELETE` | 100k rows per batch | 43.2 M rows/day to expire | every 3 min | 1.1× |
| Provider calls | 1 per new key | 300 ms p99 | 500/s | 500 × 0.3 = 150 in flight | 4 pods × 50 conns |

The row that surprises people is the reaper: at 500 charges/second you are inserting
**43.2 million rows a day**, so a batch every fifteen minutes cannot keep up. It needs to run every
three minutes, or the key table becomes the largest table in the database and starts to hurt the
primary it was meant to protect.

**Bytes on the wire.**

- client → API: 500 charges/s × 1.2 KB = **0.6 MB/s**; retries push it to ~1 MB/s
- API → provider: 500/s × 800 B = **0.4 MB/s out**, responses ~600 B
- API → Postgres: 3,000 key ops/s × 500 B = **1.5 MB/s**, which is trivial — the cost is latency, not bandwidth

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| Claim p99 | histogram around the `INSERT` | ≤ 5 ms | it sits on every payment |
| Replay p99 | retry an already-finished key | ≤ 5 ms | retries must be cheaper than work |
| Duplicate provider calls | provider stub call log, asserted in CI | 0 | the only number that matters |
| 409 rate | `http_requests_total{code="409"}` | < 2% | concurrent retries, not abuse |
| Key table growth | table size, week over week | flat | the reaper is alive |
""",

"chapters/05-double-payment-prevention.md": """
## 5. Sizing the components

The three-phase request means you hold a database connection *and* a thread for the duration of an
external call — so the connection pool is sized by concurrency, not by request rate.

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| Payments API | 2 transactions + 1 RPC | ~100 charges/s per pod | 1,000/s | 10 pods | 1.5× |
| Connections during RPC | 1 held per in-flight request | 1,000/s × 2 s timeout = **2,000 in flight** | 2,000 | PgBouncer transaction pool, 200 server conns | 10× |
| Repair worker | 1 provider query per stuck row | 200 rows per 5 s batch | < 10 stuck rows steady state | 2 pods | 40 rows/s |
| Ledger | 2 append-only rows per payment | — | 2,000 rows/s | same primary | ~20% of write capacity |
| Outbox publisher | batches of 500 | 50 in flight | 1,000 events/s | 2 pods | 2× |

That 2,000-connection row is the whole reason PgBouncer appears in this chapter: 2,000 direct
connections would exceed a `db.r6g.2xlarge`'s `max_connections` of 800, and the service would
fail during a provider slowdown — precisely when it must not.

**Bytes on the wire.**

- client → API: 1,000 charges/s × 1.2 KB = **1.2 MB/s**
- API → provider: 1,000/s × 700 B = **0.7 MB/s out**, responses ~600 B = **0.6 MB/s in**
- repair → provider: 40 queries/s, negligible bandwidth but 2 s each

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| `unknown` age | `max(now() - updated_at)` where state is unknown | < 5 min | money is in limbo |
| Duplicate provider refs | daily reconciliation against settlement file | 0 per day | the one that pages a human |
| Outbox lag | `max(now() - created_at)` unpublished | < 60 s | downstream consumers are stale |
| Repair throughput | rows fixed per second | ≥ 40/s | the loop keeps up with a provider incident |
| Provider error rate | 5xx ÷ total | < 2% | above this, stop retrying into the outage |
""",

"chapters/06-rate-limiting.md": """
## 5. Sizing the components

A rate limiter adds a network round trip to every request, so it has two budgets: Redis capacity,
and the milliseconds it is allowed to consume.

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| API pods | 1 `EVAL` + handler | ~2,500 req/s per pod | 100k req/s | 40 pods | 1.5× |
| Redis (cluster) | one Lua `EVAL`, 2 keys | ~150k ops/s per shard | 100k ops/s | 3 shards (33k each) | 4.5× |
| Concurrency limiter | `ZADD` + `ZREM` | 2 ops per request | 20k requests in flight | same cluster | — |
| Fleet shedder | 1 counter read | cached 1 s per pod | 40 reads/s | same cluster | negligible |
| Limiter budget | 1 round trip | ~0.3 ms same-AZ | — | 20 ms timeout, fail open | 60× |

If every request also read the fleet counters from Redis you would triple the op count; caching
them for one second per pod turns 100k ops/s into 40. That is the kind of change that decides
whether one Redis shard is enough.

**Bytes on the wire.**

- API → Redis: 100k ops/s × 220 B command = **22 MB/s in**, ~100 B response = **10 MB/s out**
- The limiter itself never touches the request body — it only needs the account id and a cost

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| Limiter overhead | p99 with limiter minus p99 without | < 1 ms | it must be invisible |
| Degraded rate | `ratelimit_degraded_total` ÷ requests | < 0.1% | you are running unprotected |
| Redis p99 | client-side command latency | < 5 ms | the limiter is about to be the bottleneck |
| 429 rate per user | p99 across accounts | < 5% | limits set too low, or abuse |
| Shed rate | worker shedder rejections | 0 at steady state | above zero, you are in an incident |
""",

"chapters/07-realtime-messaging.md": """
## 5. Sizing the components

WebSocket servers are sized by memory and file descriptors, not CPU; channel servers are sized by
memory. Both numbers are easy to get wrong by an order of magnitude.

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| Gateway pods | 1 socket + fan-out | ~40k sockets, ~10k sends/s per pod | 500k sockets | 16 pods (8 per region) | 1.3× on sockets |
| Channel servers | message fan-out | ~16.7k msgs/s per pod | 50k msgs/s | 12 pods | 3.9× |
| CS memory | 100 messages × 300 B per **active** channel | 2 M active channels = 60 GB | 12 × 8 GB = 96 GB | 1.6× |
| Subscriptions | channel → socket map | ~30k entries per gateway pod | 500k sockets × 50 channels | 16 pods | — |
| Ring members | one CS per hash slot | 160 virtual nodes each | 12 pods | `maxUnavailable: 1` | survives one loss |

The memory row is where designs go wrong: keeping a 500-message window for *every* channel would
need terabytes per host. Keeping 100 messages for the ~2 M channels with recent activity is 60 GB
across the fleet — which is why "history window" in section 6 is a bounded number, not a promise.

**Bytes on the wire.**

- client → gateway: 50k msgs/s × 300 B = **15 MB/s in**
- gateway → channel server: same 15 MB/s, plus 1 MB/s of typing events
- channel server → gateways: 50k × 300 B × fan-out 3 = **45 MB/s out**, ~2.8 MB/s per gateway pod
- ping/pong keepalive: 500k sockets × 40 B / 30 s = **0.7 MB/s**, but 16k frames/s of CPU

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| Delivery p99 | timestamp at send, timestamp at client | < 500 ms | the end-to-end SLO |
| Ring heal | time from CS kill to full re-subscribe | < 20 s | the blast radius of a node loss |
| Slow-consumer drops | `gateway_slow_consumer_drops_total` | < 0.1% of clients | fan-out is not keeping up |
| CS resident memory | container RSS | < 8 GB | OOMKill risk on the ring |
| Reconnect rate | new sockets ÷ active sockets per minute | < 5% | a region or CS is failing |
""",

"chapters/08-geospatial-matching.md": """
## 5. Sizing the components

Location updates dominate the write path by two orders of magnitude over matching, so the system is
sized for pings and only *budgeted* for matches.

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| Location ingest | 1 driver ping | 60 B, every ~4 s | 100k drivers = **25k pings/s** | 4 pods | 2× |
| Redis geo | `GEOADD` / `SREM`+`SADD` | ~100k ops/s per shard | 25k ops/s | 3 shards, by city | 4× |
| Postgres upsert | 1 row upsert | ~5k rows/s per node | 25k/s, batched every 5 s | 1 × `r6g.4xlarge` | 5× |
| Matcher | 1 ring query, ≤ 40 candidates | 2 ms p99 on Redis | 500 matches/s per city | 9 pods | 6× |
| Offer lock | `SET NX EX` | 0.2 ms | 500/s | same Redis | — |

A ping every four seconds from 100,000 drivers is 25,000 writes a second per city. Sending that
straight to Postgres would be the whole database budget spent on positions nobody reads; batching
to one upsert every five seconds cuts it to 5,000 rows/s and leaves the primary for trips.

**Bytes on the wire.**

- driver → ingest: 25k pings/s × 60 B = **1.5 MB/s**
- ingest → Redis: 25k ops/s × 80 B = **2 MB/s**
- ingest → Postgres: 5k rows/s × 120 B = **0.6 MB/s** after batching
- matcher → client: 500 matches/s × 2 KB candidate list = **1 MB/s**

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| Match p99 | histogram in the matcher | < 50 ms | riders are waiting |
| Zero-candidate rate | matches returning 0 rows | < 2% | supply is thin, or the index is stale |
| Ingest lag | now − last ping timestamp | < 15 s | you are matching ghosts |
| Offer acceptance | accepted ÷ offered | > 60% | ETAs are wrong, or the wrong drivers are offered |
| Double offers | offers to one driver in one window | 0 | the `SET NX` lock is working |
""",

"chapters/09-notification-fanout.md": """
## 5. Sizing the components

Everything in this chapter falls out of one external number — the provider's in-flight limit — so
the sizing table is really a derivation of the connection count.

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| Provider connections | 100 in flight per connection | 100 ÷ 0.05 s = **2,000 sends/s** | 16,700/s | 13 connections | 1.6× |
| Fan-out workers | 4 connections each | 8,000 sends/s per pod | 16,700/s | 4 pods | 2× |
| Collector buffer | 0.5 s of burst | 8,350 per pod | 16,700/s | 8,000 per pod | sheds at 0.5 s |
| Dedupe | 1 `SETNX` | ~0.3 ms | 16,700/s | Redis cluster | 6× |
| Queue | 1 message per push | — | 1 M messages in a 60 s burst | SQS standard | — |

Show the derivation out loud, because it is the whole design:
16,700 ÷ (100 in flight ÷ 0.05 s) = **8.4 connections minimum**, so 13 for headroom, which at four
connections per pod is **4 pods** — and each pod's buffer is half a second of the burst.

**Bytes on the wire.**

- workers → provider: 16,700/s × 1 KB payload = **17 MB/s out**
- provider → workers: 16,700/s × 200 B ack = **3 MB/s in**
- queue → workers: 16,700/s × 400 B = **7 MB/s**, and that is the number that sets SQS throughput cost

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| Shed rate | `notify_shed_total` ÷ enqueued | < 1% | the burst exceeded capacity |
| Queue age | now − oldest message timestamp | < 60 s | delivery is now a product problem |
| Provider 429 rate | 429s ÷ sends | < 1% | in-flight limit set too high |
| DLQ depth | dead-letter messages ÷ traffic | < 0.5% | dead device tokens are accumulating |
| Transactional latency | p99 for priority=transactional during a burst | flat | the shed policy is wired to the right classes |
""",
}


def renumber(text: str) -> str:
    """Bump `## N.` headings at or above 5 by one."""
    def sub(m):
        n = int(m.group(1))
        return f"## {n + 1}." if n >= 5 else m.group(0)
    return re.sub(r"^## (\d+)\.", sub, text, flags=re.MULTILINE)


def main() -> None:
    for rel, block in SECTIONS.items():
        path = pathlib.Path("docs") / rel
        text = path.read_text()
        if "## 5. Sizing the components" in text:
            print("skip (already inserted):", rel)
            continue
        text = renumber(text)
        marker = "## 6. Build it"
        assert marker in text, f"no Build-it section in {rel}"
        text = text.replace(marker, block.strip() + "\n\n" + marker, 1)
        path.write_text(text)
        print("inserted:", rel)


if __name__ == "__main__":
    main()
