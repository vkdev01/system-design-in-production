# deploy/

Everything needed to run the chapters somewhere real. Two levels:

**Laptop (docker compose)** - `deploy/compose/`
```bash
docker compose -f deploy/compose/idempotency.yml up --build
docker compose -f deploy/compose/ratelimit.yml  up --build
docker compose -f deploy/compose/chat-storage.yml up --build
docker compose -f deploy/compose/payments.yml   up --build
```

**Cluster (Kubernetes)** - one directory per chapter
```bash
kubectl apply -f deploy/scylla/            # 01: ScyllaDB via scylla-operator
kubectl apply -f deploy/chat-storage/      # 01: coalescing data service
kubectl apply -f deploy/pgbouncer/         # 02: transaction pooling
kubectl apply -f deploy/dbproxy/           # 03: routing proxy + shard map
kubectl apply -f deploy/idempotency/       # 04: payments API + reaper
kubectl apply -f deploy/payments/          # 05: repair loop + outbox
kubectl apply -f deploy/ratelimit/         # 06: four limiters
kubectl apply -f deploy/realtime/          # 07: channel servers + gateways
kubectl apply -f deploy/geo/               # 08: matcher
kubectl apply -f deploy/notify/            # 09: fan-out + KEDA
kubectl apply -f deploy/mesh/              # timeout and retry budget
```

**AWS (Terraform)** - `deploy/terraform/`
```bash
cd deploy/terraform/sharded-postgres && terraform init && terraform plan
```

Every manifest is annotated with the chapter it belongs to and the reason for the
knob values that matter. The defaults are deliberately conservative; the comments
say which single value you would change first under load.
