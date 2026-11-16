# 19 · Multi-region active-active

!!! abstract "The question"
    **"Design a system with a 99.99% SLO across two regions."** Users in Mumbai
    and Singapore both need single-digit-millisecond reads from their own region,
    and losing a whole region must cost seconds, not an incident.

!!! info "Source"
    This chapter is assembled from practice: the latency figures are
    round-trip measurements between AWS regions, and the SLO arithmetic is
    standard availability budgeting. The ownership model, the failover procedure
    and the code are this chapter's additions.

---

## 1. The problem, and the naive design

The naive multi-region design is a synchronous replica:

```python
def write(key, value):
    primary.write(key, value)          # in Mumbai
    secondary.write(key, value)        # in Singapore, wait for the ack
    return ok
```

It looks safe and it is unshippable:

| Problem | What happens | Consequence |
|---|---|---|
| Every write pays a cross-region round trip | ~70 ms Mumbai↔Singapore, ~200 ms to the US | your 50 ms write budget is gone before you do any work |
| Distance is a hard floor | physics, not tuning | no amount of hardware fixes it |
| Failover is untested | the secondary is never the primary | the first real failover is also the first rehearsal |
| Both regions write | two writers, one key | last-write-wins silently discards data |

The correct shape is **active-active with home-region ownership**: every key has
one region that accepts writes for it, reads are served locally everywhere, and
replication is asynchronous with a known, bounded lag.

---

## 2. The numbers that decide the design

| Figure | Value | Consequence |
|---|---|---|
| Mumbai ↔ Singapore RTT | **55–75 ms** | one synchronous round trip eats a third of a 200 ms budget |
| Mumbai ↔ US-East RTT | 200–230 ms | synchronous cross-ocean writes are simply impossible |
| Write budget (p99) | 200 ms | at most 2 cross-region round trips, and then nothing else |
| 99.99% availability | **52.6 minutes of downtime per year** | one unplanned failover per quarter is already most of the budget |
| Replication lag (async) | 100–500 ms typical | **your RPO is that lag**: a failover can lose the last half-second |
| Health check | 3 failures × 10 s = 30 s to detect | plus DNS TTL 60 s → ~90 s to shift traffic |
| Failover budget | ≤ 5 minutes | well inside 52 minutes a year, even twice |
| Read locality | 100% of reads served locally | the entire point of a second region |

The two numbers that decide everything: **the 70 ms round trip** forbids
synchronous replication, and **52.6 minutes a year** means you can afford a
couple of real failovers but not a flapping one.

---

## 3. The mental model

> **Every key has a home region. Reads go local; writes go home. Replication is
> asynchronous, so the system is consistent within a region and eventually
> consistent across them — and the RPO is a number you choose, document, and
> test.**

That framing makes the trade explicit instead of accidental: you are not
"avoiding distributed consistency", you are choosing a 500 ms data-loss window
in exchange for 70 ms writes and a working second region.

---

## 4. The flow chart

```mermaid
flowchart TD
    U1["User in Mumbai"] --> R1["Route 53 / Global Accelerator<br/>latency-based routing"]
    U2["User in Singapore"] --> R1
    R1 -->|"nearest healthy"| M["ap-south-1 (Mumbai)<br/>home for keys hash < 50%"]
    R1 --> S["ap-southeast-1 (Singapore)<br/>home for keys hash >= 50%"]
    M <-->|"async replication<br/>100-500 ms lag"| S
    M --> MDB[("Mumbai primary<br/>for its half")]
    S --> SDB[("Singapore primary<br/>for its half")]
    M -.->|"read of a Singapore-home key"| SDB
    M --> HC["Health check<br/>3 x 10 s"]
    HC -->|"region down"| FO["Failover runbook<br/>promote, flip DNS, drain"]
    FO --> R1
    style HC fill:#fff7ed,stroke:#f97316
    style M <-->|"async replication<br/>100-500 ms lag"| S
```

Note the dotted arrow: a read for a key whose home is the *other* region either
waits one round trip or returns the locally replicated (possibly stale) copy.
Which one you pick is a per-endpoint decision — that is the read-your-writes
conversation.

---

## 5. Sizing the components

| Component | Unit of work | Cost per unit | Peak demand | Provisioned | Headroom |
|---|---|---|---|---|---|
| Regional write path | 1 write | local commit + async ship | 50k writes/s per region | 2 regions, each sized for 60% of global | 1.2× |
| Cross-region replication | 1 row change | 500 B | 50k × 500 B = **25 MB/s** | 2 × 10 Gbps links | 300× |
| Local read path | 1 read | < 5 ms | 500k reads/s per region | 100% local | — |
| Cross-region read (stale-ok) | 1 read | 1 RTT if strong | ~2% of reads | local replica serves | — |
| Global LB | 1 DNS/anycast decision | 30 s detection | — | Route 53 + Global Accelerator | — |

**Bytes on the wire.**

- replication: 25 MB/s per direction — tiny compared with the write rate it represents, because rows are small
- cross-region reads: 2% × 500k × 2 KB = **20 MB/s**, and each costs 70 ms — so they must be rare and explicitly opted into
- user traffic: served locally, so it never crosses a region

| Benchmark | How to measure | Target | What it tells you |
|---|---|---|---|
| Local read p99 | per region | ≤ 10 ms | locality is real |
| Local write p99 | per region | ≤ 50 ms | no synchronous cross-region hop crept in |
| Replication lag | per key range | ≤ 500 ms p99 | the RPO you are promising |
| Failover time | game day, measured | ≤ 5 min | the number in your runbook |
| Split-brain events | conflict detector | 0 in steady state | two writers on one key |

---

## 6. The algorithm, end to end

| # | Path | Who | What happens | If this step fails |
|---|---|---|---|---|
| 1 | read | client | routed to the nearest healthy region | region unhealthy → next nearest |
| 2 | read | regional service | reads local; if the key is home elsewhere, reads the local replica | replica stale → serve with `X-Stale: true` or force a home read |
| 3 | write | client | routed to the key's **home** region (by key hash or tenant) | home down → failover, then writes resume there |
| 4 | write | home region | commits locally, appends to a replication stream | replication down → lag grows; writes keep working |
| 5 | replicate | async worker | ships the change to the peer region | peer behind → RPO grows; alert |
| 6 | failover | operator or automation | promote the peer, flip DNS, drain the old region | flapping → require a cooldown before flipping back |

```text
function homeRegion(key):
    return regions[hash(key) % len(regions)]        # deterministic, no lookup


function write(key, value):
    home = homeRegion(key)
    if localRegion != home and !failoverActive(home):
        return redirect(home)                        # 307 to the home region
    row = local.commit(key, value)                   # local, fast
    replicationStream.append(row)                    # async, never awaited
    return ok


function read(key, consistency = LOCAL):
    if consistency == LOCAL or homeRegion(key) == localRegion:
        return localStore.get(key)                   # may be stale by the lag
    return homeStore.get(key)                        # 1 RTT, opt-in only


function failover(down, up):
    assert replicationLag(up) < RPO_MS               # refuse if the peer is too far behind
    promote(up)                                      # peer becomes home for all keys
    flipDNS(up, ttl = 60)                            # ~90 s to drain
    freezeWrites(down)                               # never two writers
    # cooldown: refuse to fail back for 30 minutes
```

**Invariants.**

- **One home per key.** Two writers on one key is the only unrecoverable
  failure, so failover freezes the old region's writes before promoting.
- **Reads are local by default.** A cross-region read is an explicit choice with
  a 70 ms cost, not an accident.
- **The RPO is a number, and failover refuses to run if the peer is further
  behind than that.** Otherwise you silently lose more than you promised.
- **Failback is a separate, slower operation** with a cooldown — flapping burns
  the 52-minute budget faster than an outage does.
- **Data residency is a routing decision.** If a jurisdiction requires data to
  stay in-country, that is a third input to `homeRegion`, not a compliance
  afterthought.

| Edge case | What the algorithm does |
|---|---|
| Region down | promote peer, flip DNS in ~90 s, freeze the old region's writes |
| Peer 10 s behind during failover | refuse the promotion; that is more loss than the RPO allows |
| Both regions alive, link broken | both keep serving their own homes; conflicts only for keys whose home moved — so do not move homes without a failover |
| User travels to the other region | reads local (fast), writes redirect home (70 ms) — acceptable |
| Read-your-writes required | force that endpoint's read to the home region |
| Failback after a failover | drain, re-replicate, flip back with a 30-minute cooldown |

---

## 7. Build it

### Step 1 — home-region ownership, and a conflict detector

```python
# code/region/router.py (excerpt)
REGIONS = ("ap-south-1", "ap-southeast-1")

def home_region(key: str) -> str:
    return REGIONS[zlib.crc32(key.encode()) % len(REGIONS)]


class RegionRouter:
    def __init__(self, local: str):
        self.local = local
        self.failover: dict[str, str] = {}          # down region -> promoted region

    def home(self, key: str) -> str:
        h = home_region(key)
        return self.failover.get(h, h)

    def accepts_writes(self, key: str) -> bool:
        return self.home(key) == self.local

    def read(self, key: str, consistency: str = "local"):
        if consistency == "local" or self.home(key) == self.local:
            return self.local_store.get(key)
        return self.peer_store.get(key)             # one RTT, opt-in
```

### Step 2 — prove the write path never crosses a region

```python
# code/region/latency.py
python latency.py --rtt-ms 70 --budget-ms 200
# local write (1 local commit)         : 5 ms   OK
# + sync replication to peer           : 75 ms  OK
# + sync to a third region             : 145 ms OK
# + one more hop (e.g. a read-back)    : 215 ms BREACHES BUDGET
```

That table is the whole argument for asynchronous replication in four lines: the
third hop breaks the budget, and most real write paths have more than three hops.

### Step 3 — a failover you can rehearse

```python
# code/region/failover.py
python failover.py --down ap-south-1 --lag-ms 300 --rpo-ms 500
# lag 300 ms <= RPO 500 ms: promote ap-southeast-1
# promote ............ 2 s
# DNS flip ........... 60 s TTL, ~90 s to drain
# freeze old writes .. 1 s
# total .............. 93 s   (budget 300 s)
```

Run it with `--lag-ms 900` and it refuses, which is the point: a runbook that
cannot say no will lose more data than it saves.

---

## 8. The production layer

```hcl
# deploy/region/main.tf (abridged)
resource "aws_route53_health_check" "region" {
  for_each          = toset(["ap-south-1", "ap-southeast-1"])
  fqdn              = "api.${each.key}.example.com"
  port              = 443
  type              = "HTTPS"
  resource_path     = "/healthz"
  failure_threshold = 3
  request_interval  = 10
}

resource "aws_route53_record" "api" {
  zone_id        = var.zone_id
  name           = "api.example.com"
  type           = "A"
  set_identifier = "latency"
  latency_routing_policy {
    region = "ap-south-1"
  }
  health_check_id = aws_route53_health_check.region["ap-south-1"].id
  alias {
    name                   = var.alb_dns["ap-south-1"]
    zone_id                = var.alb_zone_id
    evaluate_target_health = true
  }
}

resource "aws_globalaccelerator_accelerator" "api" {
  name            = "api-global"
  ip_address_type = "IPV4"
  enabled         = true
  attributes { flow_logs_enabled = true }
}
```

| Knob | Value | Why |
|---|---|---|
| Routing | latency-based DNS + Global Accelerator | DNS alone cannot fail over in under a minute |
| Health check | 3 × 10 s, path `/healthz` that touches only local state | a check that calls the peer fails both regions at once |
| TTL | 60 s | the floor for a DNS-based flip |
| Replication | async, per-region stream, lag alerting | the 70 ms round trip forbids synchronous |
| Failover guard | refuse if lag > RPO | a runbook that cannot say no loses data |
| Failback cooldown | 30 minutes | flapping is more expensive than a slow return |

| Alert | Threshold | Why |
|---|---|---|
| Replication lag | > 500 ms for 2 min | your RPO is already breached |
| Cross-region read rate | > 5% | locality is broken; someone added a synchronous hop |
| Health check flaps | > 2 in an hour | failover is about to burn the budget |
| Write latency | > 50 ms p99 | a cross-region call crept into the write path |

### Failure drills

1. **Kill a region.** Game day: take Mumbai down entirely; measure the time to
   full service from Singapore and confirm the RPO held.
2. **Lag beyond RPO.** Throttle replication past the RPO, then attempt a
   failover; assert it refuses.
3. **Split brain.** Partition the link while both regions are up; assert keys
   keep their homes and the conflict detector stays at zero.
4. **Failback.** After the game day, fail back and confirm the cooldown prevents
   an immediate second flip.

---

## 9. The two-minute answer

> "Multi-region is a latency problem before it is an availability problem. The
> Mumbai–Singapore round trip is 55 to 75 milliseconds and Mumbai to the US is
> over 200, so with a 200 millisecond write budget you get at most two or three
> cross-region hops before you have spent it — which rules out synchronous
> replication immediately.
>
> So: active-active with home-region ownership. Every key has one home region
> that accepts its writes, decided by a hash, so there is no lookup and no
> ambiguity. Reads are served locally everywhere and may be stale by the
> replication lag; a cross-region read is an explicit, opt-in 70 millisecond
> cost, not something that happens by accident. Writes redirect to the home
> region if the client landed elsewhere, and replication is asynchronous at 100
> to 500 milliseconds of lag.
>
> That makes the RPO a number you choose and document, not an accident: the
> half-second of lag is your data-loss window, and the failover script refuses
> to run if the peer is further behind than that. A runbook that cannot say no
> loses more data than it saves.
>
> Availability arithmetic: 99.99% is 52.6 minutes a year, so you can afford two
> real failovers but not a flapping one. Detection is 30 seconds of health
> checks plus a 60 second DNS TTL, so about 90 seconds to shift traffic, and the
> whole thing fits inside five minutes. Failback is a separate, slower operation
> with a 30-minute cooldown.
>
> The one invariant that matters: one home per key. Failover freezes the old
> region's writes before promoting the peer, because two writers on one key is
> the only failure here you cannot recover from. And if a jurisdiction requires
> data to stay in-country, that is a third input to the home decision, not a
> compliance afterthought."

### Follow-ups you should expect

| Question | The answer they want |
|---|---|
| "Why not synchronous?" | 70 ms per round trip against a 200 ms budget; the third hop breaches it |
| "What is your RPO?" | the replication lag, ~500 ms, and the failover refuses to run beyond it |
| "How do you avoid split brain?" | one home per key; freeze writes before promoting |
| "Read-your-writes?" | force that endpoint's read to the home region, or pin the session |
| "How fast is failover?" | ~90 s to shift traffic, ≤ 5 min end to end, measured in a game day |
| "Data residency?" | residency is a routing input, not a separate cluster |

**Code:** `code/region/` · **Manifests:** `deploy/region/`
