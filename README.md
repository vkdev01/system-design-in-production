# System Design in Production

**A build-it-yourself manual for the nine systems that show up in every senior
system-design loop, reconstructed from the engineering write-ups that the people
who actually ran them published.**

Read it as a site: **https://vkdev01.github.io/system-design-in-production/**

Nine production write-ups are the spine of this repo:

| # | The interview question | The write-up it comes from |
|---|---|---|
| 01 | Design a chat app | How Discord Stores Trillions of Messages |
| 02 | Your Postgres database is full. Now what? | Herding elephants: sharding Postgres at Notion |
| 03 | Scale a database without rewriting the app | How Figma's databases team lived to tell the scale |
| 04 | Design a payment API | Designing robust and predictable APIs with idempotency (Stripe) |
| 05 | How do you stop a user getting charged twice? | Avoiding Double Payments in a Distributed Payments System (Airbnb) |
| 06 | Design a rate limiter | Scaling your API with rate limiters (Stripe) |
| 07 | Design Slack | Real-time Messaging (Slack Engineering) |
| 08 | Design driver matching for Uber | H3: Uber's hexagonal spatial index |
| 09 | Design a notification system | How Discord handles push request bursts of over a million per minute |

Each chapter follows the same seven-step path: the problem, the numbers that
decide the design, the mental model, the flow chart, the build (from scratch to
a working prototype), the production layer (Kubernetes manifests, AWS managed
services, limits, failure drills), and finally the two-minute interview answer.

## Why this exists

Diagrams teach you the boxes. Write-ups teach you why the boxes broke. This repo
takes the write-ups and adds the part they leave out: the code, the configs, the
capacity math, and the operational drills, so you can run the thing and watch it
fail in a controlled way.

## Run the site locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
mkdocs serve          # http://127.0.0.1:8000
mkdocs build --strict # what CI runs
```

## Repo layout

```
docs/           the manual (MkDocs Material, published to GitHub Pages)
  foundations/  mental models, capacity numbers, the 7-step method
  chapters/     the nine chapters
  appendices/   k8s + AWS pattern library, drills, sources
code/           runnable prototypes, one directory per chapter
deploy/         Kubernetes manifests, Helm values, Terraform, docker-compose
```

## Code map

| Chapter | Code | Run it with |
|---|---|---|
| 01 | `code/chat-storage/` | `docker compose -f deploy/compose/chat-storage.yml up` |
| 02 | `code/sharding/` | `psql -f code/sharding/schema.sql` |
| 03 | `code/dbproxy/` | `go run ./code/dbproxy` |
| 04 | `code/idempotency/` | `docker compose -f deploy/compose/idempotency.yml up` |
| 05 | `code/payments-outbox/` | `docker compose -f deploy/compose/payments.yml up` |
| 06 | `code/ratelimit/` | `docker compose -f deploy/compose/ratelimit.yml up` |
| 07 | `code/realtime/` | `go run ./code/realtime/cmd/gateway` |
| 08 | `code/geo/` | `python code/geo/match.py` |
| 09 | `code/notify/` | `go run ./code/notify` |

## Licence

MIT. The prose in this repo is original; the numbers and the stories belong to
the engineering teams that published them, and every chapter links back to the
source.
