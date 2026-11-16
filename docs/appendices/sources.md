# Appendix C · Sources

Every number in this manual comes from one of these nine write-ups, or is
arithmetic shown in the text so you can check it. Read the originals — they are
better than any summary, including this one.

## The nine primary sources

| # | Write-up | Author / date | What to take from it |
|---|---|---|---|
| 01 | [How Discord Stores Trillions of Messages](https://discord.com/blog/how-discord-stores-trillions-of-messages) | Bo Ingram, Discord, March 2023 | Partition key design, hot partitions at quorum, data services with request coalescing, the dual-write + token-range migration, 177 → 72 nodes, 15 ms p99 |
| 02 | [Herding elephants: Lessons learned from sharding Postgres at Notion](https://www.notion.com/blog/sharding-postgres-at-notion) | Garrett Fidalgo, Notion, October 2021 | The 480-shard divisibility argument, 500 GB / 10 TB / 60k IOPS ceilings, application-level sharding vs Citus, backfilling the shard key |
| 03 | [How Figma's databases team lived to tell the scale](https://www.figma.com/blog/how-figmas-databases-team-lived-to-tell-the-scale/) | Figma, March 2024 | Logical vs physical sharding, DBProxy, colos, partial commit failures, nine months for the first table |
| 03b | [The growing pains of database architecture](https://www.figma.com/blog/how-figma-scaled-to-multiple-databases/) | Figma, April 2023 | Vertical partitioning mechanics, AAS measurement, ~30 s partial availability per move, 65% CPU baseline |
| 04 | [Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency) | Brandur Leach, Stripe, February 2017 | `Idempotency-Key`, why retries need a stored answer, the failure taxonomy |
| 04b | [Stripe API reference: idempotent requests](https://docs.stripe.com/api/idempotent_requests) | Stripe | Header name, 24-hour retention, `Idempotent-Replayed`, the parameter-mismatch error message |
| 05 | [Avoiding Double Payments in a Distributed Payments System](https://medium.com/airbnb-engineering/avoiding-double-payments-in-a-distributed-payments-system-2981f6b070bb) | Airbnb, April 2019 | Orpheus, pre-RPC/RPC/post-RPC, the two ground rules, leases, retryable vs non-retryable, replica-lag double charges |
| 06 | [Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters) | Paul Tarjan, Stripe, March 2017 | The four limiters, fail-open, kill switches, dark launching, load shedding vs rate limiting |
| 06b | [Token bucket Lua script](https://gist.github.com/ptarjan/e38f45f2dfe601419ca3af937fff574d) | Paul Tarjan | The reference implementation this repo's `token_bucket.lua` follows |
| 07 | [Real-time Messaging](https://slack.engineering/real-time-messaging/) | Sameera Thangudu, Slack, April 2023 | Channel/Gateway/Admin/Presence split, ~16 M channels per host, CHARM, 20 s replacement, 500 ms global delivery |
| 08 | [H3: Uber's Hexagonal Hierarchical Spatial Index](https://www.uber.com/blog/h3/) | Isaac Brodsky, Uber, 2018 | Why hexagons, the hierarchy, indexing strategy for movement |
| 08b | [H3: tables of cell statistics](https://h3geo.org/docs/core-library/restable) | H3 documentation | Exact cell counts and average areas per resolution (used in chapter 08's table) |
| 09 | [How Discord handles push request bursts of over a million per minute with Elixir's GenStage](https://discord.com/blog/how-discord-handles-push-request-bursts-of-over-a-million-per-minute-with-elixirs-genstage) | Jesse Howarth, Discord, December 2016 | Producer/consumer with demand, the 100-in-flight provider limit, buffer-based load shedding, the incident timeline |

## Secondary sources worth reading

| Topic | Source | Why |
|---|---|---|
| Postgres at scale, in general | [Scaling Postgres](https://www.scalingpostgres.com/) | Weekly, practical, and honest about limits |
| Query routing proxies | [pganalyze: How Figma built DBProxy](https://pganalyze.com/blog/5mins-postgres-figma-dbproxy-sharding-postgres) | A second read on the proxy design |
| Idempotency in practice | [brandur.org/idempotency-keys](https://brandur.org/idempotency-keys) | The recovery-point implementation in depth |
| Wide-column modelling | [ScyllaDB docs: data modelling](https://docs.scylladb.com/) | Partition size, compaction strategy, `LOCAL_QUORUM` |
| Kubernetes patterns | [Kubernetes docs: disruption budgets, probes, topology spread](https://kubernetes.io/docs/concepts/) | The primitives in Appendix A |
| SLO alerting | [Google SRE Workbook, chapter 5](https://sre.google/workbook/alerting-on-slos/) | Burn-rate alerts instead of thresholds |

## A note on figures

- All company figures (node counts, latencies, shard counts, cell areas) are quoted
  from the sources above.
- All arithmetic (storage sizing, connection counts, cost estimates, timeout
  budgets) is shown step by step in the text. Redo it; if you get a different
  answer, one of us is wrong and it is worth knowing which.
- Cloud prices and instance limits change. The structure of the calculation does
  not.
- Discord's push post describes Firebase's XMPP interface, which is now legacy;
  FCM HTTP v1 is the current API. The *pattern* — a hard provider concurrency
  limit, demand-driven consumers, bounded buffers, load shedding — is unchanged and
  is the part worth learning.
