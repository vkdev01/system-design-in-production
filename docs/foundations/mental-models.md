# The 9 mental models

Every chapter in this manual is a variation on nine ideas. Learn these and you can
rebuild any of the nineteen systems from first principles in an interview, because you
will be deriving the design instead of recalling it.

Each model below has: the one-sentence claim, the symptom you see when you violate
it, the fix, and where it shows up in this repo.

---

## 1. Every system is a queue with a bound

**Claim.** Throughput is not the thing that kills you; *unbounded concurrency* is.
Little's Law says the number of requests in flight equals arrival rate times time
in system:

$$
L = \lambda \times W
$$

| Symbol | Read as | Unit |
|---|---|---|
| \(L\) | concurrency: requests being served right now | requests in flight |
| \(\lambda\) (lambda) | arrival rate: requests per second reaching the system | requests/second |
| \(W\) | time in system: how long one request takes end to end | seconds |

At 20,000 requests per second with a 50 ms p99:

$$
L = 20{,}000 \times 0.05 = 1{,}000 \text{ requests in flight}
$$

Same symbols, in the units that matter: \(\lambda = 20{,}000\) requests/second,
\(W = 0.05\) seconds (50 ms, so the 0.05 is milliseconds divided by 1,000), and
\(L = 1{,}000\) — that is how many connections, threads or goroutines you must have
open at that instant.

If latency doubles, in-flight doubles with no change in traffic, and now you are
out of connections, memory or threads, so latency triples, so in-flight triples.
That is the cascade.

**Symptom.** Latency graph goes vertical while request rate is flat. Thread pools
saturate, connection pools empty, and health checks start timing out on a service
that is doing "no more work than before".

**Fix.** Bound the queue *and* shed at the front. Concurrency limits on the client
side of every dependency, a timeout shorter than the caller's timeout, and a
bounded buffer with a documented drop policy. See chapters
[06](../chapters/06-rate-limiting.md) and [09](../chapters/09-notification-fanout.md).

---

## 2. Latency is a distribution; the p99 is the product

**Claim.** Users do not experience your mean. One slow shard, one garbage
collection pause, one hot partition sets the p99 for everyone hitting it, and at
fan-out scale the p99 *becomes* the mean.

If a request touches 100 services and each has a 1% chance of being slow:

$$
P(\text{at least one slow}) = 1 - 0.99^{100} = 63\%
$$

| Symbol | Read as | Unit |
|---|---|---|
| \(P(\cdot)\) | probability of the event in brackets | 0 to 1, shown as % |
| \(0.99\) | chance one dependency answers fast, i.e. it is outside its own p99 | probability |
| \(100\) | fan-out: how many dependencies one user request touches | count |
| \(1 - x\) | complement: "at least one" is one minus "none" | probability |
| \(63\%\) | the answer: about two in three page loads hit a slow tail | probability |

So the arithmetic is \(0.99^{100} = 0.37\) chance that *every* dependency is fast,
and \(1 - 0.37 = 0.63\) that at least one is not.

This is why
Discord's move from Cassandra to ScyllaDB mattered so much: the win was not
average speed, it was deleting the 40–125 ms p99 tail for reads and the 5–70 ms
p99 tail for writes, replacing both with a flat 15 ms and 5 ms.

**Symptom.** "It's fast in Grafana but users complain." You are looking at p50.

**Fix.** Alert on p99 and on the *rate of requests exceeding the SLO*, not on
averages. Budget the tail: if your SLO is 300 ms p99 and you make 5 sequential
calls, each gets ~60 ms, and one of them may not use its whole budget.

---

## 3. Hot partitions, not big databases, are what kills you

**Claim.** Data size is a capacity problem you can buy your way out of. Skew is a
correctness problem: one key that gets 1,000× the traffic of the average key will
take down a node, and in a quorum system it takes the *cluster's* latency with it.

Discord's message table was partitioned by `(channel_id, bucket)`. A server with
half a million members writes orders of magnitude more than a five-person group
chat, so one partition pair received a disproportionate share of reads. Since
reads are served at quorum, that one node's slowness propagated to every query
touching it.

**Symptom.** One node at 100% CPU while the fleet sits at 20%. p99 climbs across
the board while throughput is flat.

**Fix.** Three levers, in order of cost: (a) coalesce reads so N users asking for
the same row become one query; (b) route by key so all requests for a hot key land
on the same instance and can be coalesced; (c) re-key the data, adding a bucket or
a random suffix. Chapters [01](../chapters/01-chat-message-storage.md) and
[07](../chapters/07-realtime-messaging.md).

---

## 4. Writes are cheap, reads are expensive (in an LSM)

**Claim.** In Cassandra/ScyllaDB/RocksDB-style storage, a write appends to a commit
log and a memtable; a read may have to consult the memtable plus several SSTables
on disk. So the read/write cost ratio is not 1:1, and a design that "just reads
more" is a design that falls over first.

This is why message stores are optimised for *scan a recent window of one
channel* (a single partition, in order, from cache) and not for "search all
messages from this user".

**Symptom.** Compaction backlog grows, read latency climbs, and the node starts
falling behind on maintenance. Discord's team literally had to take nodes out of
rotation to let them compact ("the gossip dance").

**Fix.** Design the primary key around the access pattern; keep partitions
bounded (time buckets); push filtering to write time via denormalised tables; put
a coalescing layer in front so duplicate reads never reach storage.

---

## 5. Idempotency is a state machine, not a boolean

**Claim.** "Have I seen this key?" is the wrong question. The right one is "what
state is this key in, and what is legal from here?" The states are: *new*,
*in progress (leased)*, *finished successfully*, *finished with a retryable
error*, *finished with a terminal error*.

A boolean dedupe flag cannot express "the first attempt is still running, tell the
client 409 and back off" versus "the first attempt succeeded, replay the stored
response" versus "the first attempt failed permanently, replay that failure".
Stripe and Airbnb both model the full machine, and both store the response, not
just the key.

**Symptom.** Retries either double-charge (flag set too late) or permanently
strand a payment (flag set too early and never cleared).

**Fix.** One row per key, with a state, a fingerprint of the request, a lease
expiry, and the stored response. Claim atomically. Chapters
[04](../chapters/04-idempotent-payment-api.md) and
[05](../chapters/05-double-payment-prevention.md).

---

## 6. Never mix network calls with database transactions

**Claim.** An open transaction holds a database connection; a network call holds a
thread. Do both at once and you have coupled the latency of a third party to the
size of your connection pool. When the third party slows down, your pool drains
and your whole service dies, not just that endpoint.

Airbnb's Orpheus library enforces this with two rules: no service interaction over
the network during the pre-RPC and post-RPC phases, and no database interaction
during the RPC phase. Each phase is its own transaction.

**Symptom.** Connection pool exhaustion alerts during a downstream incident.
`pg_stat_activity` full of `idle in transaction`.

**Fix.** The pattern: *commit intent, then act, then commit outcome*, with an
outbox or a recovery point so a crash in the middle is recoverable. Never
`BEGIN; call external API; COMMIT;`.

---

## 7. Vertical before horizontal; logical before physical

**Claim.** Scaling moves come in a fixed order of cost. First make the query
faster and the cache bigger. Then split by *table group* onto separate databases
(vertical partitioning) — cheap, reversible, no application rewrite. Only then
split one table across machines (horizontal sharding), which costs you joins,
foreign keys and cross-shard transactions.

Figma did exactly this: a single RDS instance in 2020 → caching, read replicas and
a dozen vertically partitioned databases by end of 2022 → first horizontally
sharded table in September 2023, nine months of work for one table. And inside
horizontal sharding they split *logical* sharding (an application-level change,
rollback = a config flip) from *physical* sharding (copy the data, re-route
traffic), so they could de-risk each independently.

**Symptom.** Teams reach for Vitess or Citus at 200 GB and spend a year on
plumbing they did not need.

**Fix.** Write down the limit that is actually binding (CPU, IOPS, table size,
vacuum, connection count, TXID age) and the runway in months. Climb one rung at a
time. Chapters [02](../chapters/02-sharding-postgres.md) and
[03](../chapters/03-scaling-postgres-figma.md).

---

## 8. Fail open or fail closed is a per-feature decision

**Claim.** When a control-plane dependency (Redis, the rate limiter, the feature
flag service) is unavailable, you must have decided *in advance* whether that
feature allows traffic or blocks it. Stripe's rate limiter fails **open** —
requests pass if Redis is down, because a rate limiter exists to protect the API,
not to become a second way to take it down. Their observed failure rate is 0.01%,
and they alert on it.

A payment idempotency store fails **closed** (or rather, refuses to proceed
without a durable claim), because the alternative is charging twice.

**Symptom.** An ElastiCache blip takes down the entire API because middleware
threw.

**Fix.** Wrap the dependency, catch everything, choose the default, and emit a
metric that pages you if the fallback is being used. Chapter
[06](../chapters/06-rate-limiting.md).

---

## 9. Consistent hashing moves the blast radius; it does not remove it

**Claim.** Hashing keys to nodes gives you O(1) routing and no central lookup, but
it makes the servers stateful, so a node's death is an event: its keys are
reassigned and their in-memory state must be rebuilt. The design question is not
"how do I avoid node loss" but "how big is the blast radius and how fast does it
heal".

Slack's Channel Servers hold up to ~16 million channels each, mapped by consistent
hash. Their CHARM ring managers replace an unhealthy CS in under 20 seconds, and
the teams whose channels lived there see elevated latency for less than 20
seconds. They also rehearse it: their chaos programme deliberately partitioned 25%
of channel servers to prove Consul re-routed correctly.

**Symptom.** A single pod restart produces a global latency spike because every
client re-subscribes at once.

**Fix.** Replication factor ≥ 2 for stateful hash-ring members, a documented
hand-off window, jittered client reconnect, and a PodDisruptionBudget so a rolling
deploy never takes two ring members at once. Chapter
[07](../chapters/07-realtime-messaging.md).

---

## The two numbers rule

Before you draw anything, get two numbers: **peak QPS** and **p99 budget**. Every
design decision in these nineteen chapters is downstream of those two numbers. When an
interviewer gives you vague requirements, propose them yourself and say why:

> "Let me assume 50 million daily active users, 40 messages per user per day, with
> a 5× peak-to-average ratio. That is 2 billion messages a day, about 23,000 per
> second average, roughly 115,000 per second at peak. With a 200 ms p99 budget on
> send-to-delivery, I need the write path under 20 ms and the fan-out to be
> asynchronous."

That single paragraph is worth more than three diagrams, because it proves you
know which numbers change the answer.
