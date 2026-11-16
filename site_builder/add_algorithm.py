"""Insert an end-to-end algorithm section into each chapter.

Sits between "5. Sizing the components" and "6. Build it": sizing says how big
each box is, this says what actually happens to one request, in order, with the
pseudocode and the invariants that must hold. Later sections are renumbered.
"""

import pathlib
import re

SECTIONS = {
"chapters/01-chat-message-storage.md": """
## 6. The algorithm, end to end

Sizing gave each box a number. This is the part in between: one message, from a
client's keystroke to another client's screen, in order, with the invariants that
make it correct. Read this before the code in section 7 — the code is only this
algorithm spelled in Go.

| # | Who | What happens | Durable afterwards | If this step fails |
|---|---|---|---|---|
| 1 | Client | mints a Snowflake ID (time-ordered, unique per worker) and sends `POST /channels/:id/messages` | nothing | client retries with the same ID; the write is idempotent |
| 2 | API | checks membership from a cache, computes `bucket = window(message_id)` | nothing | 403/500; no state to unwind |
| 3 | API | `INSERT` at `LOCAL_QUORUM` into `((channel_id, bucket), message_id)` | commitlog on ≥2 of 3 replicas | 503; client retries, same row, same result |
| 4 | ScyllaDB | coordinator hashes the partition key → replicas; memtable + commitlog; quorum ack | yes | one replica slow → quorum still met; two slow → write fails, retry |
| 5 | API | publishes `message.created` to the fan-out path (chapter 07) | no — best effort | message is stored but not pushed; the client's next fetch finds it |
| 6 | Reader | `GET /channels/:id/messages?after=&limit=` → data service with routing key `channel_id` | nothing | retry; read path holds no state |
| 7 | Data service | coalesces on `(channel, bucket, after, limit)`; one query per key, not per reader | no (in-flight only) | coalescer entry dies with the pod; the query just runs again |
| 8 | ScyllaDB | single-partition ordered scan, `message_id DESC` | — | if the window is empty, the caller reads `bucket - 1` |
| 9 | Data service | if `len(rows) < limit`, merges the previous bucket | no | partial page returned; the next request continues from the last ID |

```text
function readMessages(channel, after, limit):
    bucket = windowOf(after)                      # static 10-day window
    key    = "chan:" + channel + ":b:" + bucket

    return coalesce(key, function () {            # N readers -> 1 query
        rows = scylla.query(channel, bucket, after, limit)     # 1 partition, ordered
        if length(rows) < limit:                  # straddle the window boundary
            rows += scylla.query(channel, bucket - 1, after, limit - length(rows))
        return rows
    })

function writeMessage(channel, message):
    bucket = windowOf(message.id)
    scylla.insert(channel, bucket, message, consistency = LOCAL_QUORUM)
    publish("message.created", { channel, message })   # async, not on the write path
```

**Invariants the design depends on.**

- **Ordering is per channel, not global.** The partition `(channel_id, bucket)` with
  `message_id` as the clustering key gives a total order inside one window; two
  channels have no relative order, and nobody needs one.
- **The write is idempotent by construction.** The primary key contains the message
  ID, so a retried insert overwrites a row with identical values. No dedupe table.
- **Reads never see a hole.** A read that straddles a bucket boundary merges both
  windows before returning, so pagination cannot skip a message.
- **Coalescing never changes the answer.** It is keyed on the exact query
  parameters; two different queries never share a result.

| Edge case | What the algorithm does |
|---|---|
| Message sent exactly on a bucket boundary | `windowOf` is a floor division, so it belongs to the later window; a reader straddling it merges both |
| Client retries after a timeout | Same Snowflake ID → same primary key → one row |
| Channel with 500k members, 20k reads/s | Coalescing collapses them to one query per window; the shard's concurrency cap protects the node |
| Reader asks for a window older than retention | Data service returns the cold-tier pointer; object storage serves it |
| Two clients send at the same millisecond | Different Snowflake sequence numbers → different clustering keys → stable order |
""",

"chapters/02-sharding-postgres.md": """
## 6. The algorithm, end to end

The whole system reduces to one function — workspace ID to physical database and
schema — plus a set of rules about what you are allowed to ask once you get there.
Everything else in this chapter is consequence.

| # | Who | What happens | If this step fails |
|---|---|---|---|
| 1 | App | receives a request that names a workspace (from the session or the URL) | 400: the request is unrouteable by construction |
| 2 | Router | `sha256(workspace_id) mod 480` → logical shard; integer division → physical database | pure function, cannot fail |
| 3 | Router | checks `shard_map_version` against the row's version | reject the write: a stale map writes one workspace to two shards |
| 4 | PgBouncer | maps the client connection onto a small server-side pool for that database | `query_wait_timeout` → 503, not a hang |
| 5 | Postgres | executes against `schemaNNN.table` with `workspace_id` in the predicate | statement timeout 15 s |
| 6 | App | if the query would touch two workspaces, refuses it and uses the async path instead | never a scatter-gather on the request path |

```text
function route(workspace_id):
    shard  = sha256(workspace_id) mod 480          # 480 divides by 40, 48, 60, 80, 96
    db     = shard div 15                          # 15 logical shards per database
    schema = "schema" + zeroPad(shard mod 15 + 1, 3)
    return (db, schema)

function query(workspace_id, sql, params):
    (db, schema) = route(workspace_id)
    if not sqlHasShardKey(sql):                    # every sharded table carries it
        raise Unroutable("query needs workspace_id")
    return pgbouncer(db).execute("set search_path to " + schema, sql, params)
```

**Invariants.**

- **One workspace, one shard, forever** (for a given shard-map version). This is what
  makes single-shard transactions and joins correct.
- **`workspace_id` is on every sharded row.** Not just as a predicate — as a column,
  so the row can be moved and audited later.
- **A transaction never spans two databases.** Enforced by refusing cross-workspace
  queries, not by hoping.
- **The map is versioned.** Reads may use a cached map; writes must match the version
  the shard records.

| Edge case | What the algorithm does |
|---|---|
| A new workspace | UUID assigned at creation → hash decides the shard; nothing is rebalanced |
| A workspace that outgrows its shard | move it to a dedicated shard and add an override entry to the map |
| Cross-workspace search | separate analytics replica fed by CDC; never on the request path |
| A shard is down | the router fails that workspace's requests; every other workspace is unaffected — that is the point of sharding |
| Re-shard from 32 to 96 databases | change the divisor in `route()`, keep 480 logical shards, migrate in the background |
""",

"chapters/03-scaling-postgres-figma.md": """
## 6. The algorithm, end to end

The proxy turns a query into a routing decision. The interesting part is not the
lookup — it is what the proxy refuses to do, and how the same code runs in
"logical" mode before any data moves.

| # | Who | What happens | If this step fails |
|---|---|---|---|
| 1 | App | sends a query with its parameters, unchanged since before the proxy existed | — |
| 2 | DBProxy | parses just enough to find the table and its shard key | unparseable → pass through or reject by config |
| 3 | DBProxy | extracts the shard-key value from the parameters | missing → **error and metric**, never a fan-out |
| 4 | DBProxy | hashes the key → shard; looks up the pool for that shard | unknown shard → 503 |
| 5 | DBProxy | in *logical* mode: routes as if sharded but the pool points at the single old host, and shadow-compares results | mismatch → metric, no user impact |
| 6 | DBProxy | in *physical* mode: executes against the real shard with a 250 ms statement timeout | timeout → 504, caller retries |
| 7 | DBProxy | records latency per shard, per table | — |

```text
function execute(sql, params):
    table = parseTable(sql)
    key   = params[shardKeyFor(table)]
    if key is null:
        metric("unroutable", table)
        raise Unroutable(table)                 # loud, never a scatter-gather

    shard = ring.lookup(key)
    pool  = pools[shard]

    if mode == LOGICAL:                          # data still on one host
        result = pool.query(sql, params, timeout = 250ms)
        shadowCompare(shard, sql, params, result)
        return result

    return pool.query(sql, params, timeout = 250ms)
```

**Invariants.**

- **A query either routes or fails.** There is no third outcome, because a silent
  fan-out turns a 2 ms query into a 400 ms one and nobody notices until the p99
  incident.
- **Logical sharding is a configuration flag.** Rollback is a flag flip, which is why
  the migration can be de-risked in production.
- **Schema changes go through one orchestrator** and are backward compatible for one
  release, so a half-migrated fleet still serves.

| Edge case | What the algorithm does |
|---|---|
| Query with no shard key | `Unroutable` + `dbproxy_unroutable_total` — the alert is the fix |
| Query that genuinely needs two shards | rejected; the feature moves to the async/CDC path |
| A shard split is in flight | the map version gates writes; the split job is idempotent per chunk |
| Proxy pod dies mid-query | connection resets; the caller retries against another proxy |
| A shard's primary fails over | pool reconnects, ~10–30 s of errors for that shard only |
""",

"chapters/04-idempotent-payment-api.md": """
## 6. The algorithm, end to end

The idempotency layer is one state machine evaluated in a fixed order. Get the order
wrong and you replay the wrong answer; get the lease wrong and you strand a payment.

| # | Who | What happens | Durable afterwards |
|---|---|---|---|
| 1 | Client | mints a UUID per logical operation, persists it **before** the call | key on the client |
| 2 | API | computes `fingerprint = sha256(canonical(body))` | — |
| 3 | API | `INSERT … ON CONFLICT DO NOTHING` with `state=in_progress`, `lease=now+30s` | yes, one row |
| 4 | API | if the insert won: call the provider (no transaction open) | — |
| 5 | API | write the outcome + the response body, clear the lease | yes |
| 6 | Client | on any error, retries with the **same** key and the **same** body | — |
| 7 | API | arbitration ladder (below) decides: execute, replay, 409, or take over | — |
| 8 | Reaper | deletes rows older than the retention window, in batches | table stays flat |

```text
function handle(request, key):
    if key is null: return 400 "Idempotency-Key required"

    claim = tryInsert(key, fingerprint(request))       # atomic, ON CONFLICT
    if claim.inserted: return execute(claim.id, request)

    row = select for update (key)

    if row.fingerprint != fingerprint(request):        # checked FIRST
        return 409 "same key, different parameters"

    if row.state in ("succeeded", "terminal"):
        return replay(row.response)                    # Idempotent-Replayed: true

    if row.state == "in_progress" and row.lease > now():
        return 409 "already in progress"               # back off and retry

    # the previous worker died: take the lease over
    takeLease(row.id, lease = now() + 30s)
    return execute(row.id, request)
```

**Invariants.**

- **The ladder's order is the contract.** Fingerprint before replay, because
  replaying a stored response to a different request is a lie.
- **The lease outlives the RPC and not the client's patience.** 30 s against a 2 s
  provider timeout.
- **Idempotency reads go to the primary.** A replica with two seconds of lag answers
  "no such key" and you charge twice.
- **The stored response is immutable.** Changing its shape is a breaking change for
  every client that retries across it.

| Edge case | What the algorithm does |
|---|---|
| Response lost after the provider charged | retry replays the stored 201 |
| Two concurrent retries | one wins the insert; the other gets 409 with `Retry-After` |
| Worker killed between claim and provider call | lease expires → next retry takes over |
| Same key, different amount | 409 params-mismatch, never a replay |
| Key reused after 72 h (reaped) | treated as a new request — which is why retention is longer than the slowest legitimate retry |
""",

"chapters/05-double-payment-prevention.md": """
## 6. The algorithm, end to end

Three phases, two short transactions, one irreversible call, and a repair loop that
owns everything the request path could not finish. This is the algorithm; section 7
is the same thing in Python.

| # | Phase | What happens | State after |
|---|---|---|---|
| 1 | pre-RPC | validate, take the lease, `INSERT` intent | `pending`, lease set |
| 2 | pre-RPC | `COMMIT` — the intent is now durable | — |
| 3 | RPC | call the provider with our own key `pay-<id>`, timeout 2 s | unchanged |
| 4 | post-RPC | `UPDATE` state, write two ledger rows, insert the outbox event, `COMMIT` | `succeeded` / `failed_terminal` / `failed_retryable` |
| 5 | repair | picks up `pending`/`unknown` rows whose lease expired, `FOR UPDATE SKIP LOCKED` | — |
| 6 | repair | asks the provider "what happened to `pay-<id>`?" | authoritative answer |
| 7 | repair | writes the outcome exactly as step 4 would have | terminal |
| 8 | outbox | publishes `payments.settled`; consumers dedupe on payment id | downstream consistent |

```text
function createPayment(request):
    # ---- phase 1: intent, one short transaction ----
    tx.begin()
    p = insertIntent(request, lease = now() + 30s)
    tx.commit()
    if p.wasReplay: return p.storedResponse

    # ---- phase 2: the irreversible call, no transaction open ----
    try:
        ref = provider.charge(amount, currency, idempotencyKey = "pay-" + p.id, timeout = 2s)
        outcome = SUCCEEDED(ref)
    catch Declined as e:   outcome = TERMINAL(e)
    catch Timeout / 5xx:   outcome = UNKNOWN(e)        # money may have moved

    # ---- phase 3: outcome, one short transaction ----
    tx.begin()
    updateState(p.id, outcome)
    if outcome.ok: insertLedger(p.id, amount)
    insertOutbox(p.id, outcome)
    tx.commit()
    return p.storedResponse


function repairStuck():
    rows = select where state in (pending, unknown) and lease < now() - 10s
           order by updated_at limit 200 for update skip locked
    for r in rows:
        remote = provider.getByKey("pay-" + r.id)      # the authoritative question
        applyOutcome(r.id, remote)                      # same write as phase 3
```

**Invariants.**

- **No network call inside a transaction; no database call during the RPC.** Otherwise
  a slow provider drains your connection pool.
- **Every payment reaches a terminal state.** `unknown` is a state, not an excuse: the
  repair loop guarantees it drains.
- **Ledger rows are written in the same transaction as the state change**, so balances
  are always derivable.
- **Retries are safe because the provider knows our key.** Without that, the repair
  loop can only ask, not fix.

| Edge case | What the algorithm does |
|---|---|
| Provider charged, response lost | `unknown` → repair finds `captured` → `succeeded`, one charge |
| Provider never received it | repair sees `not_found` → `failed_retryable` → retried under the same key |
| Crash between phase 2 and 3 | lease expires, repair closes it out |
| Two workers on one payment | `FOR UPDATE SKIP LOCKED` plus the lease |
| Provider down for ten minutes | rows accumulate in `unknown`; the circuit opens; repair drains after recovery |
""",

"chapters/06-rate-limiting.md": """
## 6. The algorithm, end to end

Four decisions in a fixed order, each cheaper than the next, with a documented
answer for "the limiter itself is broken". The order matters as much as the
algorithms.

| # | Limiter | Cost | Decision | Failure mode |
|---|---|---|---|---|
| 1 | Request rate | 1 Redis `EVAL` (~0.3 ms) | take `cost` tokens from the bucket; empty → 429 | Redis error → **allow**, increment `degraded` |
| 2 | Concurrency | 1 `ZADD` + `ZREM` | more than N in flight → 429 | error → allow |
| 3 | Fleet usage | 1 cached counter read | non-critical over its share → 503 | stale counter → allow |
| 4 | Worker utilisation | local atomic, 0 network | shed class by class → 503 | cannot fail |

```text
function admit(request):
    if not limiterEnabled: return ALLOW                 # kill switch

    # 1. token bucket, atomic in Lua
    (allowed, left) = eval(tokenBucket, keys = ["{u}:tokens", "{u}:ts"],
                           args = [rate, burst, now, cost(request)])
    if redisError: metric("degraded"); return ALLOW     # fail open
    if not allowed: return REJECT_429(left)

    # 2. in-flight cap for CPU-heavy endpoints
    if inFlight(user) >= 20: return REJECT_429()

    # 3. fleet reservation for critical methods
    if not critical(request) and fleetInflight() > capacity * 0.80:
        return SHED_503()

    # 4. this box, right now
    util = localInflight / localCapacity
    if util > 0.98 and class(request) != CRITICAL: return SHED_503()
    if util > 0.95 and class(request) == GET:      return SHED_503()
    if util > 0.90 and class(request) == TEST:     return SHED_503()

    return ALLOW

function tokenBucket(rate, burst, now, cost):
    tokens = min(burst, stored + (now - lastRefill) * rate)
    allowed = tokens >= cost
    if allowed: tokens -= cost
    store(tokens, now, ttl = 2 * burst / rate)
    return (allowed, tokens)
```

**Invariants.**

- **The limiter is a filter, not a dependency.** Every error path allows the request;
  `ratelimit_degraded_total` is the alarm, not a 500.
- **One round trip per request, bounded at 20 ms.** Anything more expensive belongs in
  a different layer.
- **Shedding and restoring are slow.** Thresholds move a few percent per minute, or the
  system flaps.
- **Critical methods are exempt from steps 3 and 4.** Payments do not queue behind a
  test-mode script.

| Edge case | What the algorithm does |
|---|---|
| Redis down | allow everything, alert, keep serving |
| One user at 10k req/s | their bucket empties; other users' keys hash to other shards |
| Legitimate 5× burst | burst capacity absorbs it; the bucket refills at `rate` |
| Clock skew across pods | `now` comes from the server, and the bucket tolerates a small delta because it stores `lastRefill` |
| Bad limit shipped | kill switch flips the limiter off in seconds, no deploy |
""",

"chapters/07-realtime-messaging.md": """
## 6. The algorithm, end to end

Two paths matter: a client subscribing, and a message reaching every subscriber. Both
are short, and both depend on the ring being right.

| # | Path | Who | What happens |
|---|---|---|---|
| 1 | connect | client | opens a WebSocket to its nearest region's edge (Envoy) |
| 2 | connect | gateway | authenticates, loads the user's channel list, sends the first frame |
| 3 | connect | gateway | subscribes to each owning channel server **asynchronously**, 32 at a time |
| 4 | connect | gateway | replays the delta from `last_seen_message_id` if the client sent one |
| 5 | send | client | `POST` to the web app (persisted path) or a frame to the gateway (transient path) |
| 6 | send | admin server | hashes `channel_id` → owning channel server |
| 7 | send | channel server | verifies ring version **and** ownership, appends to its history window |
| 8 | send | channel server | fans out to every subscribed gateway in parallel, bounded per gateway |
| 9 | send | gateway | pushes to each subscribed socket, dropping slow consumers |
| 10 | rebalance | CHARM | on CS loss, re-assigns channels; gateways re-subscribe; ~20 s of elevated latency |

```text
function publish(channel, message, ringVersion):
    if ringVersion != myRingVersion: raise RingVersionMismatch   # stale routing
    if ring.owner(channel) != me:    raise NotOwner              # never write twice

    history[channel].append(message)                 # bounded window, in memory
    gateways = subscribers[channel]

    parallel for gw in gateways:                     # bounded, timed out
        gw.send(channel, message)                    # one slow gateway cannot stall

function onConnect(client, lastSeen):
    for channel in userChannels(client):             # 32 at a time, jittered retries
        cs = ring.owner(channel)
        cs.subscribe(channel, client.id)
        delta = cs.replay(channel, lastSeen)          # in-memory if the gap is small
        if delta is null: delta = storage.read(channel, lastSeen)   # fall back to ch 01
        client.send(delta)

function deliver(client, frame):
    try: client.outbox.put(frame)                     # bounded queue (256)
    catch Full: close(client, "slow consumer; resync required")
```

**Invariants.**

- **One owner per channel** — that single writer is what gives you ordering for free.
- **A channel server writes only what it owns**, and refuses messages routed with a
  stale ring version.
- **Fan-out is bounded.** A slow consumer is disconnected and told to resync; it never
  slows anyone else.
- **The channel server is a cache of history, not the source of truth.** Losing one is
  a latency event, not a data-loss event.

| Edge case | What the algorithm does |
|---|---|
| Client reconnects after a gap | `last_seen_message_id` → in-memory replay, or storage fallback |
| CS dies | ring re-assigns; gateways re-subscribe with jitter; ~20 s |
| 60k sockets reconnecting at once | jittered backoff, gateway scaled on connections |
| One client stops reading | dropped after its 256-frame queue fills |
| Typing indicator | gateway → CS directly, never persisted, never through the web app |
""",

"chapters/08-geospatial-matching.md": """
## 6. The algorithm, end to end

One rider, one request: find candidates by expanding rings, rank by real distance,
offer with an atomic lock, and give up cleanly. The whole thing is bounded work per
request — that is the design goal.

| # | Who | What happens | If this step fails |
|---|---|---|---|
| 1 | Driver app | pings position every ~4 s | next ping fixes it |
| 2 | Ingest | `GEOADD`/`SADD` into the city's Redis, batch-upsert to Postgres every 5 s | ingest lag alarm at 15 s |
| 3 | Rider | requests a match for `(lat, lng, city)` | — |
| 4 | Matcher | `cell = h3(lat, lng, res 9)` | pure function |
| 5 | Matcher | `k_ring(cell, 1)` → 7 cells → candidates; not enough → `k=2, 3, 5`, capped | cap reached → return what exists |
| 6 | Matcher | filters: available, vehicle type, fresh ping (< 2 min), not already offered | — |
| 7 | Matcher | ranks by haversine/ETA, takes the top N (≤ 40) | — |
| 8 | Matcher | `SET NX` on `offer:<driver>` with a 12 s TTL | lock lost → next candidate |
| 9 | Driver | accepts → trip created; declines or times out → lock expires, next candidate | — |

```text
function match(rider):
    cell = h3.cellAt(rider.lat, rider.lng, RES_INDEX)      # res 9, ~0.105 km2

    for k in [1, 2, 3, 5]:                                 # 7, 37, 91, 271 cells
        cells = h3.gridDisk(cell, k)
        drivers = redis.cellMembers(cells)                 # hot path, ~0.5 ms
        drivers = filter(drivers, available, vehicleMatch,
                         pingAge < 2min, notOffered)
        if length(drivers) >= 10:
            break

    ranked = sort(drivers, by = haversine(rider, driver))[:40]
    for d in ranked:
        if redis.set("offer:" + d.id, rider.id, nx = true, ex = 12s):
            notify(d, rider)
            return WAIT_FOR_ANSWER
    return NO_DRIVER                        # explicit, not a hang

function accept(rider, driver):
    if redis.get("offer:" + driver.id) != rider.id: return STALE_OFFER
    redis.del("offer:" + driver.id)                     # idempotent on the offer id
    createTrip(rider, driver)                           # chapters 04/05 apply here
```

**Invariants.**

- **Bounded work per request.** Ring expansion is capped; candidate set is capped;
  offer attempts are capped. No unbounded scan can be triggered by a client.
- **One live offer per driver.** `SET NX` is the only primitive that can promise that.
- **Position and cell never disagree.** They are written in one statement, because a
  stale cell makes a driver unmatchable.
- **Stale pings never win.** A two-minute freshness filter is the difference between a
  ghost driver and a real one.

| Edge case | What the algorithm does |
|---|---|
| Airport hotspot: 2,000 drivers in one cell | candidate cap + ranking; latency stays flat |
| Two riders, one driver | exactly one `SET NX` wins; the other falls through |
| Driver goes offline mid-offer | lock expires in 12 s; rider re-matches |
| Rider on a cell boundary | `k_ring` includes neighbours; no candidate is missed |
| No drivers at all | explicit `NO_DRIVER` after the cap, not a long scan |
""",

"chapters/09-notification-fanout.md": """
## 6. The algorithm, end to end

Fan-out is a pipeline with one hard external constraint: the provider's in-flight
limit. Every stage below exists to respect it while never blocking the producer.

| # | Stage | What happens | On failure |
|---|---|---|---|
| 1 | event | domain event lands on the queue (SQS) | redelivery after visibility timeout |
| 2 | fan-out | expands one event to N devices | retried, idempotent per (event, device) |
| 3 | dedupe | `SET NX` on a collapse key `(user, thread, 5-min window)` | duplicate → dropped |
| 4 | preference | muted / quiet hours / already active in app → drop | — |
| 5 | buffer | bounded enqueue (≈0.5 s of burst per pod) | full → shed + metric |
| 6 | pusher | demands work in batches ≤ 100 per connection | provider 429 → back off |
| 7 | provider | FCM / APNs / Web Push | 4xx → delete token; 5xx → retry |
| 8 | retry | exponential backoff with jitter, max 4 attempts | exhausted → DLQ |

```text
function onEvent(event):
    for (user, device) in expand(event):
        if not dedupe.allow(collapseKey(user, event.thread, 5min)): continue
        if not preferences.allows(user, event, now()):              continue
        if user.isActiveInApp:  continue                 # they are already looking
        if not collector.accept(Push(user, device, event)):
            metric("shed")                               # buffer full: documented loss
            continue

function pusher():
    sem = semaphore(connections * 100)                   # the provider's limit, as code
    loop:
        sem.acquire()
        request = collector.take()                       # demand, not push
        spawn:
            try:  provider.send(request)
            catch e:
                match classify(e):
                    Terminal:    deleteToken(request.device); dlq(request)
                    Retryable:   backoffWithJitter(attempt); requeue(request)
                    CircuitOpen: requeue(request)        # do not burn attempts
            finally: sem.release()
```

**Invariants.**

- **The provider's in-flight limit is encoded as a semaphore**, and the pool is sized
  from it: `16,700 ÷ (100 ÷ 0.05 s) ≈ 8.4` connections, so 13 for headroom.
- **The buffer is bounded and the drop policy is explicit.** Dropping a social push is
  acceptable; an outage is not.
- **Transactional pushes are never shed**, and never share a queue with social ones.
- **Retries always have jitter**, or the recovery becomes a second incident.
- **A dead token is deleted, not retried forever.**

| Edge case | What the algorithm does |
|---|---|
| 1M pushes in 60 s | buffer fills, shed starts, transactional latency stays flat |
| Provider returns 429 | in-flight limit set too high → back off, alert, tune |
| Provider outage for 3 min | circuit opens, messages requeue without burning attempts, drain after recovery |
| Same event delivered twice | collapse key dedupes |
| Malformed device token | 4xx → token deleted, message to DLQ |
""",
}


def renumber(text: str) -> str:
    """Bump `## N.` headings at or above 6 by one."""
    def sub(m):
        n = int(m.group(1))
        return f"## {n + 1}." if n >= 6 else m.group(0)
    return re.sub(r"^## (\d+)\.", sub, text, flags=re.MULTILINE)


def main() -> None:
    for rel, block in SECTIONS.items():
        path = pathlib.Path("docs") / rel
        text = path.read_text()
        if "## 6. The algorithm, end to end" in text:
            print("skip (already inserted):", rel)
            continue
        text = renumber(text)
        marker = "## 7. Build it"
        assert marker in text, f"no Build-it section in {rel}"
        text = text.replace(marker, block.strip() + "\n\n" + marker, 1)
        path.write_text(text)
        print("inserted:", rel)


if __name__ == "__main__":
    main()
