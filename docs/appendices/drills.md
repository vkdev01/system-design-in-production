# Appendix B · Failure drills and interview scripts

Two things make a design answer land: you can break the system on purpose, and you
can say the answer in two minutes. This appendix is the cheat sheet for both.

---

## Part 1 — The nine scripts, condensed

Each is the two-minute answer with the numbers kept and the prose trimmed. Read
these the night before an interview.

### 01 · Chat app (Discord)

> Append-only log per channel. Primary key `((channel_id, bucket), message_id)` with
> Snowflake IDs, so a scrollback is one ordered partition scan and the time bucket
> bounds partition size. Failure mode is skew, not size: a 500k-member server writes
> orders of magnitude more than a group chat, and at quorum reads one slow node
> slows every query touching it. Discord hit exactly that at 177 Cassandra nodes,
> trillions of messages, 40–125 ms p99 reads and 5–70 ms inserts. Fix was two-part:
> ScyllaDB on local NVMe mirrored by RAID — 72 nodes at 9 TB instead of 177 at 4 TB,
> 15 ms p99 read, flat 5 ms write — plus a data service in front with one gRPC
> endpoint per query and no business logic, coalescing duplicate reads and
> consistent-hash routing on channel ID so a million readers of one announcement
> become one disk read. Migration: dual write, token-range backfill with SQLite
> checkpoints at 3.2 M messages/s, shadow-read validation, flip. Nine days, no
> downtime.

### 02 · Postgres is full (Notion)

> Shard when maintenance breaks, not when disk fills: their `VACUUM` stalled and
> TXID wraparound — 2³¹ transactions, then Postgres refuses all writes — became
> existential. Application-level sharding, not Citus, so routing is explicit. Shard
> everything reachable from `block` by foreign key, keyed by `workspace_id`, because
> users work inside one workspace so cross-shard joins mostly disappear. Ceilings:
> 500 GB per table, 10 TB per database, ≥60k IOPS. **480 logical shards over 32
> physical databases** — 480 not 512 because it divides by 40, 48, 60, 80, 96, so you
> grow the fleet in 25% steps instead of doubling. Separate tables per schema, not
> partitioned tables, so there is exactly one routing step. Migration: backfill by
> primary key, dual write, continuous catch-up, a five-minute window to verify
> digests and flip. They re-sharded 32 → 96 databases in 2023 without touching the
> 480.

### 03 · Scale without rewriting the app (Figma)

> Climb the ladder: one instance at 65% CPU with 3× annual growth → cache and read
> replicas → **vertical partitioning** (move table groups to their own databases) →
> horizontal sharding. Vertical partitioning is cheap and reversible: ~30 s of
> partial availability and ~2% dropped requests per move, largest partition down to
> ~10% CPU. The enabler is a query routing service — DBProxy — so thousands of call
> sites keep asking the same question while the answer behind it changes. Then
> **logical sharding before physical**: the app behaves as if the table is split and
> every routing path is exercised, but the data is still on one host, so rollback is
> a config change. Nine months for the first table; the first flip cost 10 s of
> partial availability on primaries, nothing on replicas. Costs: no cross-shard
> joins or transactions, no FK or global unique index enforcement, partial commit
> failures become a product concern, and DDL runs across N shards.

### 04 · Payment API (Stripe idempotency)

> Client-generated `Idempotency-Key`, UUID per logical operation, reused on retries,
> payload never mutated. Server side it is one row: key, request fingerprint, state
> (in-progress / succeeded / terminal / retryable), lease expiry, stored response.
> Claim with `INSERT ... ON CONFLICT DO NOTHING` so there is no read-then-write
> race. Arbitrate in fixed order: different fingerprint → 409 (replaying another
> request's answer is a lie); finished → replay with `Idempotent-Replayed`; live
> lease → 409 and back off; expired lease → take over, the worker died. Lease 30 s
> for a 2 s provider call: longer than the RPC, shorter than the client retry.
> Reads go to the **primary** — two seconds of replica lag is a double charge. The
> key table grows with write throughput, so a batched reaper; Stripe keeps v1 keys
> 24 hours, v2 for 30 days, in-house 72 hours so a Friday bug still has its keys on
> Monday.

### 05 · Charged twice (Airbnb)

> Request idempotency is not enough when a third party moves the money. Three
> phases: a pre-RPC transaction that records intent and takes a lease; the RPC with
> **no** database transaction open; a post-RPC transaction that records the outcome,
> writes ledger entries and an outbox event. Two short transactions, one network
> call, and a crash between them is an expected state. The two rules: no network
> calls in the pre/post phases (that is how you exhaust the connection pool during a
> provider incident) and no database work during the RPC. After a timeout the state
> is honestly `unknown`; a repair worker picks up expired leases with `FOR UPDATE
> SKIP LOCKED` and asks the provider "what happened to key pay-123?" — that query,
> not the retry, is what makes it exactly-once, which is why I send my own key to the
> provider. Error classification must fail safe: default non-retryable, opt in to
> retries, because a 4xx labelled retryable is a double charge. Plus a daily
> reconciliation against the settlement file.

### 06 · Rate limiter (Stripe)

> Four limiters, in order of cost. A request rate limiter: token bucket per user in
> Redis via Lua so read-modify-write is atomic, N/s with 5× burst capacity, and a
> per-request **cost** so a batch endpoint debits more than a read — that rejects
> millions of requests a month at Stripe. A concurrency limiter, because CPU-bound
> endpoints saturate on in-flight work not request rate: "20 in progress", a Redis
> sorted set scored by start time with stale entries reaped. A fleet usage shedder
> reserving ~20% of the fleet for critical methods, returning 503 for non-critical
> traffic over its 80% share. A per-box worker utilization shedder as the last line
> of defence: no network call, four classes, shed test mode first, then GETs, then
> POSTs, and shed gradually so you do not flap. Two rules: everything **fails open**
> if Redis dies, with a metric and an alert, because a limiter must never be the
> reason the API is down; and every limiter has a kill switch behind a feature flag,
> dark-launched first.

### 07 · Slack

> Separate ownership of a conversation from ownership of a socket. Channel Servers
> are stateful and in-memory, each owning a subset of channels by consistent hash —
> ~16 M channels per host at peak — holding a recent history window and being the
> only writer for its channels. Gateway Servers hold client WebSockets, deployed per
> region so clients connect to the nearest one. An Admin Server is stateless and
> routes from the web app to the owning CS; Presence Servers hash users. One message
> is one write plus N subscription deliveries, ~500 ms globally. Typing indicators
> skip all of it — gateway straight to CS, nothing persisted. CHARM ring managers
> publish the ring via Consul; a replacement CS serves in under 20 s, so a node loss
> costs the affected teams under 20 s of elevated latency, and they rehearse it by
> partitioning 25% of channel servers. Details that matter: virtual nodes, a ring
> version in every routing call, bounded outbound queues per client, jittered
> reconnects, PDB `maxUnavailable: 1` on the ring tier.

### 08 · Driver matching (Uber H3)

> Stop thinking in coordinates, start thinking in cells. H3 tiles the earth with
> hexagons on 16 resolutions — 5.16 km² at res 7, 0.74 km² at 8, 0.105 km² at 9 —
> so every location is a 64-bit cell ID and "who is near here" becomes an indexed
> equality lookup plus a ring expansion. Index driver positions at res 9 (a few
> blocks), use res 7 for surge and demand zones (~5 km²). Query `h3_grid_disk(cell,
> k)` for k = 1, 2, 3, expanding until enough candidates with a hard cap — 7 cells,
> 37, 91 — then rank by real distance or ETA, because ring distance is quantised.
> Hexagons because all six neighbours are equidistant, so ring expansion adds a
> uniform band instead of biasing toward diagonals. PostGIS/h3-pg as truth with a
> `bigint` cell column and a partial index on available drivers, Redis for the hot
> path, sharded by city. Watch: index cell disagreeing with position (unmatchable
> driver), stale pings (ghost drivers, 2-minute cutoff), airport hotspot (cap the
> candidate set), and two riders offering one driver (atomic `SET NX` on the offer).

### 09 · Notification system (Discord)

> A bounded queue between an unbounded producer and a rate-limited consumer. Bursts
> over a million a minute — ~16,700/s — against a provider allowing 100 pending per
> connection; at ~50 ms per send that is 2,000/s per connection, so about nine
> connections minimum, more for headroom. Two stages: a collector per machine with a
> bounded buffer, and many pushers that **demand** work in batches of 100 so they
> never exceed the provider limit — that inversion turns the provider limit into
> backpressure all the way to the producer. When the buffer fills, the collector
> sheds, and that is a deliberate product decision: dropping a few notifications is
> acceptable, an outage is not. In their incident a five-minute burst filled the
> buffer, a few notifications were dropped, nothing else was affected. My additions:
> SQS with KEDA on queue depth (HPA cannot see a backlog), collapse keys per
> user-thread-window, priority classes where transactional pushes are never shed, a
> presence check to skip pushes for active users, jittered retries, dead-token
> deletion on 4xx, and a DLQ.

---

## Part 2 — The follow-up matrix

Interviewers converge on the same eight follow-ups. Have a number in each answer.

| Follow-up | Where it is answered |
|---|---|
| "What breaks first?" | Each chapter's flow chart has a failure column. Answer with the *specific* node, not "the database". |
| "How do you know it is broken?" | Appendix A §10: one business metric plus RED/USE per pattern. |
| "What about a node/AZ loss?" | RF=3 + `LOCAL_QUORUM` (01), Multi-AZ + proxy reconnect (02/03), PDB + ring heal < 20 s (07). |
| "How do you deploy this?" | Appendix A: StatefulSet + PDB + `maxUnavailable: 0` for gateways, drain hooks, KEDA for workers. |
| "What does it cost?" | Appendix A §11: 648 TB gp3 ≈ ₹45 lakh/month; node count and storage topology dominate. |
| "Why not a managed service?" | Chapter 03's ladder: managed first, partition second, shard third. Say which rung and why. |
| "How do you test it?" | Part 3 of this appendix — one command per failure. |
| "Exactly-once?" | Never for delivery. At-most-once effects plus repair (05), or at-least-once plus dedupe (09). |

---

## Part 3 — Drill commands

Run these against the manifests in `deploy/`. Each one takes minutes and teaches
more than a week of reading.

| # | Drill | Command |
|---|---|---|
| 01 | Hot channel | `k6 run code/chat-storage/loadtest/hot_channel.js` |
| 01 | Kill a node mid-write | `kubectl -n chat delete pod messages-ap-south-1a-2` |
| 01 | Tombstone storm | `cqlsh -f code/chat-storage/migration/tombstone_storm.cql` |
| 02 | Unroutable query | `psql -f code/sharding/test_unroutable.sql` |
| 02 | TXID runway | `psql -c "select datname, age(datfrozenxid) from pg_database order by 2 desc limit 3"` |
| 03 | Stale shard map | `kubectl -n data rollout restart deploy/dbproxy` with an old ConfigMap |
| 03 | Abort a split | `kubectl -n data delete job shard-split-07` then restart it |
| 04 | Crash mid-request | `kubectl -n payments delete pod -l app=payments-api` during load |
| 04 | Replay correctness | `for i in $(seq 100); do curl -H "Idempotency-Key: K1" ...; done` |
| 05 | Timeout after success | `python code/payments-outbox/faults.py --mode timeout-after-charge` |
| 05 | Provider outage | `python code/payments-outbox/faults.py --mode outage --seconds 120` |
| 06 | Kill Redis | `kubectl -n api scale deploy/ratelimit-redis --replicas=0` |
| 06 | Burst | `k6 run code/ratelimit/loadtest/burst.js` |
| 06 | Kill switch | `curl -X POST localhost:8080/admin/ratelimit?enabled=false` |
| 07 | Kill a channel server | `kubectl -n realtime delete pod cs-3` |
| 07 | Slow consumer | `go run ./code/realtime/cmd/slowclient` |
| 07 | Partition 25% | `kubectl -n realtime cordon` + drain three of twelve |
| 08 | Airport hotspot | `python code/geo/loadtest.py --drivers 2000 --one-cell` |
| 08 | Double offer | `python code/geo/race.py --concurrent 2` |
| 09 | Million-push burst | `go run ./code/notify/cmd/burst --rate 17000 --seconds 60` |
| 09 | Breach the provider limit | `go run ./code/notify --provider-inflight 500` (stub caps at 100) |

---

## Part 4 — A 45-minute mock

| Minute | Prompt | What a strong answer contains |
|---|---|---|
| 0–3 | "Design a chat app" | constraints table, 2e9 msgs/day, 200 B, RF=3 |
| 3–12 | deep dive | partition key, bucket, coalescing, hot partition |
| 12–20 | "Now design payments" | idempotency state machine, lease, primary-only reads |
| 20–28 | "Rate limit it" | token bucket Lua, cost, fail open, kill switch |
| 28–36 | "Fan out notifications" | 100 in-flight, 9 connections, bounded buffer, shed |
| 36–45 | "What breaks at 10×?" | name the first wall and the cheapest rung on the ladder |

---

## Part 5 — Self-test

Answer without notes. If you cannot, re-read that chapter's §2 and §3.

1. Why is the time bucket in the partition key, and what does it cost?
2. What is the p99 read latency before and after Discord's migration?
3. Why 480 logical shards rather than 512?
4. Name the three Postgres soft limits that force sharding.
5. What are the three phases of a payment request, and which one may not touch the
   database?
6. Why must the idempotency read go to the primary?
7. What does a token bucket's `capacity` control, and what does `rate` control?
8. Why does a rate limiter fail open but an idempotency store fail closed?
9. How many channels can one Slack Channel Server hold, and how fast is a
   replacement serving traffic?
10. What is the average hexagon area at H3 resolution 7 and 9?
11. Why hexagons rather than squares for ring expansion?
12. What is the provider in-flight limit in Discord's push system, and how many
    connections does 16,700/s need?
13. What is the drop policy when the notification buffer is full, and who decides
    it?
14. Which two numbers decide almost every design in this manual?
