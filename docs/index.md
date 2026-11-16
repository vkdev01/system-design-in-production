## How to use this

**In a week.** One system a day, and do the arithmetic by hand before you read the numbers section.

| Day | Read | Build |
|---|---|---|
| 1 | [Mental models](foundations/mental-models.md), [Numbers](foundations/numbers.md) | Nothing. Do the arithmetic on paper. |
| 2 | [04](chapters/04-idempotent-payment-api.md), [05](chapters/05-double-payment-prevention.md) | `code/idempotency`, then kill it mid-request |
| 3 | [06](chapters/06-rate-limiting.md) | `code/ratelimit`, then run the load test until it sheds |
| 4 | [01](chapters/01-chat-message-storage.md), [09](chapters/09-notification-fanout.md) | `code/chat-storage`, `code/notify` |
| 5 | [02](chapters/02-sharding-postgres.md), [03](chapters/03-scaling-postgres-figma.md) | `code/sharding`, `code/dbproxy` |
| 6 | [07](chapters/07-realtime-messaging.md), [08](chapters/08-geospatial-matching.md) | `code/realtime`, `code/geo` |
| 7 | [Drills](appendices/drills.md) | Answer all nine out loud, two minutes each |

**Before an interview.** Read the mental models page, then the "two-minute answer" and
"follow-ups" sections of each chapter. That is about forty minutes and it covers the nine
most common senior prompts. Do not memorise diagrams; memorise the numbers and the failure
modes, because those are what the interviewer is testing.

**As a reference at work.** Each chapter's production layer is a pattern library, not a
tutorial. [Appendix A](appendices/k8s-aws-patterns.md) is the cross-chapter catalogue:
HPA versus KEDA, PodDisruptionBudgets, PgBouncer, CloudNativePG, ElastiCache, ScyllaDB on
EKS, MSK versus SQS, and the timeout budgets that tie them together.

## Who this is for

- Engineers preparing for senior or staff system design loops who can already draw a load
  balancer and a cache, and want the second half of the answer.
- Backend engineers who have to actually ship one of these systems on Kubernetes and want
  the manifests, not the metaphor.
- Anyone who learns by running things: every chapter has runnable code under `code/` and
  deployable manifests under `deploy/`.

You should be comfortable with SQL, HTTP, one server-side language, and `kubectl apply`.
Nothing here assumes you have run a 200-node cluster.

## What "production" means in this repo

Every deployment section sticks to primitives you will find in a real cluster, and prefers
managed AWS services where a team of ten would sensibly use them.

| Concern | Default choice here | Why |
|---|---|---|
| Stateless services | EKS + Deployment + HPA on RPS or CPU | Cheap, boring, well understood |
| Queue-driven workers | KEDA scaling on queue depth | HPA on CPU cannot see a backlog |
| Postgres | RDS or CloudNativePG, PgBouncer in front | Connection count, not CPU, is the usual wall |
| Cache and rate-limit state | ElastiCache Redis, cluster mode | Atomic Lua, sub-millisecond |
| Message log | MSK (Kafka) or SQS + SNS | Replay versus simplicity; chapter 09 picks apart when |
| Wide-column messages | ScyllaDB on local NVMe + RAID | Chapter 01's whole point |
| Secrets | External Secrets + IRSA | No long-lived keys in the cluster |

## Repo layout

```
docs/            the manual: foundations, nineteen chapters, three appendices
code/            runnable prototypes, one directory per chapter
deploy/          Kubernetes manifests, Terraform modules, compose files
site_builder/    this site: build.py, templates, stylesheet, scripts
```

Every figure in the manual is either quoted from the linked engineering write-up or is
arithmetic shown step by step so you can check it. Cloud prices and instance limits change;
the arithmetic does not.
