# Appendix A · Kubernetes and AWS patterns

The same handful of primitives appear in all thirteen chapters. This is the cross-chapter
catalogue: what to use, the exact knob, and the failure it prevents. Everything here
is copy-paste shaped; the per-chapter manifests under `deploy/` are the worked
examples.

---

## 1. Which workload object

| Your component | Object | Why |
|---|---|---|
| Stateless API (data service, proxy, matcher) | `Deployment` | interchangeable pods, fast rollout |
| Owner of a hash ring or shard (channel server, ScyllaDB node) | `StatefulSet` | stable identity, ordered/parallel rollout, PVC per pod |
| One-shot job (backfill, reaper, split) | `Job` / `CronJob` | retries and completion semantics |
| Per-node agent (log shipper, local NVMe formatter) | `DaemonSet` | exactly one per node |

```yaml
# The three-line rule for StatefulSets of stateful ring members
spec:
  podManagementPolicy: Parallel        # don't wait for ordinal 0 to be Ready
  serviceName: cs-headless             # headless Service for stable DNS per pod
  updateStrategy: { type: RollingUpdate }
```

!!! warning "`podManagementPolicy: OrderedReady` is the default"
    It makes a 12-node ring take 12 × readiness-time to roll out, and if pod 0
    never becomes ready, the whole rollout stalls. Use `Parallel` for ring members
    unless ordering is genuinely required (it is not for a consistent hash ring).

---

## 2. Autoscaling: HPA vs KEDA vs VPA

| Signal | Use | Never |
|---|---|---|
| CPU | batch-ish workloads, CPU-bound handlers | WebSocket gateways, coalescing services |
| RPS / in-flight requests | latency-sensitive services | when the metric lags the burst |
| Queue depth / age | **any worker reading from a queue** | — (HPA cannot see a backlog) |
| Memory | almost never for horizontal scaling | as a primary metric — it does not fall when load drops |

```yaml
# HPA on in-flight work, not CPU (the pattern from chapters 01 and 07)
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  metrics:
    - type: Pods
      pods:
        metric: { name: http_inflight_requests }
        target: { type: AverageValue, averageValue: "30" }
  behavior:
    scaleUp:   { stabilizationWindowSeconds: 0 }
    scaleDown: { stabilizationWindowSeconds: 600 }
```

```yaml
# KEDA on queue depth (chapter 09)
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
spec:
  triggers:
    - type: aws-sqs-queue
      metadata:
        queueURL: https://sqs.ap-south-1.amazonaws.com/123/notify-fanout
        queueLength: "500"
        scaleOnInFlight: "true"
```

| Asymmetry rule | Value | Reason |
|---|---|---|
| Scale up fast | 0 s window, +100%/15 s | bursts arrive in seconds |
| Scale down slowly | 300–900 s window | scaling down drops in-flight work and sockets |
| Min replicas | ≥ 3 across 3 AZs | survive a zone loss and a rollout at once |

---

## 3. Probes: the three that mean different things

| Probe | Question | Must depend on |
|---|---|---|
| `startupProbe` | has the process finished booting? | warm caches, loaded ring/shard map |
| `readinessProbe` | should this pod receive traffic? | **local** state only — never Redis, never a downstream |
| `livenessProbe` | should this pod be killed? | nothing external; a deadlock detector |

```yaml
startupProbe:
  httpGet: { path: /healthz, port: 9090 }
  failureThreshold: 30
  periodSeconds: 2          # up to 60s to boot
readinessProbe:
  httpGet: { path: /ready, port: 9090 }
  periodSeconds: 5
  failureThreshold: 2
livenessProbe:
  httpGet: { path: /healthz, port: 9090 }
  periodSeconds: 10
  failureThreshold: 6       # 60s before a restart: never flap
```

!!! danger "The most common self-inflicted outage"
    A readiness probe that checks Redis or Postgres. The dependency blips, every
    pod is removed from the Service, and your fail-open rate limiter (chapter 06)
    never gets a chance to run because there is no traffic left to limit.

---

## 4. Graceful shutdown and drain

```yaml
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: app
      lifecycle:
        preStop:
          exec: { command: ["/bin/sh", "-c", "sleep 5 && /app/drain --timeout=30s"] }
```

| Component | `terminationGracePeriodSeconds` | `preStop` | Why |
|---|---|---|---|
| Stateless API | 30 | sleep 5, stop accepting | let the Service endpoint update propagate |
| Payments API (ch. 04/05) | 60 | sleep 10, finish in-flight charges | never cut a charge in half |
| WebSocket gateway (ch. 07) | 45 | send `reconnect: true`, then close | move 60k sockets without a storm |
| Hash-ring owner (ch. 07) | 45 | `/app/drain --timeout=30s` | hand off channels before dying |
| Worker (ch. 09) | 30 | finish the current batch, stop polling | no half-sent pushes |

The pattern: `sleep` long enough for kube-proxy/ingress to stop sending new
traffic, *then* drain in-flight work, *then* exit.

---

## 5. Disruption budgets and spread

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: { name: cs }
spec:
  maxUnavailable: 1          # ring members: one at a time
  selector: { matchLabels: { app: cs } }
```

| Workload | PDB | Topology spread |
|---|---|---|
| Stateless API | `minAvailable: 75%` | `ScheduleAnyway` across AZs |
| Ring/shard owner | `maxUnavailable: 1` | `DoNotSchedule` across AZs |
| Payments | `minAvailable: 3` | `DoNotSchedule` across AZs |
| Queue worker | `minAvailable: 50%` | `ScheduleAnyway` |

```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector: { matchLabels: { app: cs } }
```

---

## 6. Resources: requests, limits, and QoS

```yaml
resources:
  requests: { cpu: 500m, memory: 512Mi }
  limits:   { memory: 512Mi }        # note: no CPU limit
```

| Rule | Why |
|---|---|
| **Set memory limits, usually not CPU limits** | a CPU limit throttles a latency-sensitive service at exactly the wrong moment; requests guarantee scheduling, and CPU contention is handled by the scheduler |
| `requests.cpu` ≈ steady-state usage | drives scheduling and HPA percentages |
| `limits.memory` ≈ 1.5–2× steady state | too tight means OOMKills under a burst; too loose means a noisy neighbour |
| Guaranteed QoS only where it matters | payments, ring owners — `requests == limits` for both CPU and memory |

---

## 7. Postgres in the cluster

| Option | Use when | Knobs that matter |
|---|---|---|
| **RDS / Aurora** | you want to stop thinking about the database | `multi_az`, `io2` + provisioned IOPS, `performance_insights`, parameter group: `autovacuum_vacuum_scale_factor=0.02`, `idle_in_transaction_session_timeout` |
| **CloudNativePG** | you want Postgres in-cluster with operators | `instances: 3`, `backup.barmanObjectStore`, `postgresql.parameters`, PDB generated |
| **PgBouncer** | always, above ~50 app pods | `pool_mode=transaction`, `default_pool_size=25`, `query_wait_timeout=10` |

```yaml
# CloudNativePG cluster, for the sharded-fleet pattern of chapter 02/03
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata: { name: shard-07, namespace: data }
spec:
  instances: 3
  storage:
    size: 2Ti
    storageClass: io2-high-iops
  postgresql:
    parameters:
      max_connections: "800"
      autovacuum_vacuum_scale_factor: "0.02"
      idle_in_transaction_session_timeout: "30000"
      shared_buffers: "16GB"
      effective_cache_size: "48GB"
  resources:
    requests: { cpu: "8", memory: "64Gi" }
    limits:   { memory: "64Gi" }
  monitoring:
    enablePodMonitor: true
```

---

## 8. Identity, secrets and the AWS control plane

```yaml
# IRSA: pods get AWS permissions without long-lived keys
apiVersion: v1
kind: ServiceAccount
metadata:
  name: notify-fanout
  namespace: notify
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/notify-fanout
---
# External Secrets: the secret lives in AWS, the pod sees a k8s Secret
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata: { name: fcm, namespace: notify }
spec:
  refreshInterval: 1h
  secretStoreRef: { name: aws-secretsmanager, kind: ClusterSecretStore }
  target: { name: fcm }
  data:
    - secretKey: json
      remoteRef: { key: prod/fcm/service-account, property: json }
```

| Need | Use | Not this |
|---|---|---|
| Pod → AWS API | IRSA (OIDC) | static access keys in a Secret |
| Secrets from AWS | External Secrets Operator | `kubectl create secret` by hand |
| Cluster → ECR | node IAM role + image pull policy | docker login in an init container |
| Cross-namespace config | ConfigMap + explicit mount | guessing at another namespace |

---

## 9. The service-mesh layer (Envoy)

Envoy is what Slack uses at the edge, and it is what most clusters already run.
Three settings do most of the work:

```yaml
# deploy/mesh/timeouts-and-retries.yaml (conceptual, Istio/Envoy shape)
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata: { name: payments }
spec:
  hosts: ["payments.payments.svc.cluster.local"]
  http:
    - timeout: 800ms
      retries:
        attempts: 2
        perTryTimeout: 300ms
        retryOn: "5xx,reset,connect-failure"
      # NEVER retry a non-idempotent POST unless it carries an idempotency key
      match:
        - method: { exact: POST }
          headers: { "idempotency-key": { prefix: "" } }
```

| Setting | Value | Why |
|---|---|---|
| `timeout` | strictly less than the caller's | chapter 06's timeout budget |
| `perTryTimeout` | ~1/3 of the total | one slow attempt must not eat the budget |
| `retries.attempts` | 1–2 | more than that is a load amplifier |
| `retryOn` | `5xx,reset,connect-failure` | never retry 4xx |
| `outlierDetection` | 5 consecutive 5xx → eject 30 s | removes a sick pod without a deploy |
| Global rate limit | Envoy `ratelimit` service + Redis | per-route ceilings before the app (ch. 06) |

---

## 10. Observability: what to measure per pattern

| Pattern | Metrics | Alert on |
|---|---|---|
| Coalescing service (ch. 01) | `coalescer_inflight_queries`, `coalescer_shared_ratio` | shared ratio dropping (coalescing stopped working) |
| Shard router (ch. 02/03) | `dbproxy_unroutable_total`, per-shard AAS | any unroutable query |
| Idempotency (ch. 04/05) | `idempotency_replays_total`, stuck leases, `unknown` payments | stuck leases > 0 |
| Rate limiter (ch. 06) | `ratelimit_degraded_total`, 429 rate, Redis p99 | degraded > 0.1% |
| Realtime (ch. 07) | delivery p99, ring version mismatches, slow-consumer drops | mismatch > 0 |
| Geo (ch. 08) | match p99, zero-candidate rate, ingest lag | ingest lag > 15 s |
| Fan-out (ch. 09) | shed rate, queue age, provider 429 rate, DLQ depth | queue age > 60 s |

Use **RED** (rate, errors, duration) for request-driven services and **USE**
(utilisation, saturation, errors) for resources, then add one business metric per
chapter (`payments_unknown`, `notifications_shed`, `matches_with_zero_candidates`)
because that is the metric that tells you the product is broken, not just the box.

SLO burn-rate alerts beat threshold alerts:

```promql
# page when 2% of a 30-day error budget is consumed in 1 hour
(
  sum(rate(http_requests_total{code=~"5.."}[1h])) / sum(rate(http_requests_total[1h]))
) > (14.4 * 0.001)     # 0.1% SLO → 14.4× burn over 1h
```

---

## 11. Cost sheet (order of magnitude, ap-south-1)

Illustrative monthly figures at list price, to make the point that design decisions
have a rupee number. Check current pricing before quoting them.

| Component | Spec | Approx monthly |
|---|---|---|
| `i4i.4xlarge` × 72 (chapter 01's cluster) | 16 vCPU, 128 GB, 3.75 TB NVMe | instance cost + no EBS for data |
| 648 TB gp3 for the same data on EBS | $0.08/GB-month | **≈ $51,800 ≈ ₹45 lakh** |
| `db.r6g.4xlarge` × 96 (chapter 02 re-shard) | 16 vCPU, 128 GB, Multi-AZ | the re-shard multiplies instance count by 3 |
| `cache.r7g.large` × 3 shards (rate limiting) | cluster mode | single-digit thousands of rupees |
| SQS + Lambda-free workers (chapter 09) | 1M msgs/min bursts | per-request pricing; cheap for bursts |

The lesson to carry into a review: **storage topology and node count dominate the
bill, and both are chosen by the design, not by the vendor.**

---

## 12. The golden manifest

Start every new service from this, then delete what you do not need.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: SERVICE
  namespace: NS
  labels: { app: SERVICE }
spec:
  replicas: 3
  revisionHistoryLimit: 3
  strategy:
    rollingUpdate: { maxUnavailable: 0, maxSurge: 1 }
  selector:
    matchLabels: { app: SERVICE }
  template:
    metadata:
      labels: { app: SERVICE }
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
    spec:
      serviceAccountName: SERVICE
      terminationGracePeriodSeconds: 45
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels: { app: SERVICE }
      containers:
        - name: app
          image: ghcr.io/ORG/SERVICE:TAG
          ports: [{ containerPort: 8080 }, { containerPort: 9090 }]
          resources:
            requests: { cpu: 500m, memory: 512Mi }
            limits:   { memory: 512Mi }
          startupProbe:
            httpGet: { path: /healthz, port: 9090 }
            failureThreshold: 30
            periodSeconds: 2
          readinessProbe:
            httpGet: { path: /ready, port: 9090 }
            periodSeconds: 5
          livenessProbe:
            httpGet: { path: /healthz, port: 9090 }
            periodSeconds: 10
            failureThreshold: 6
          lifecycle:
            preStop:
              exec: { command: ["/bin/sh", "-c", "sleep 5"] }
          securityContext:
            runAsNonRoot: true
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: { name: SERVICE, namespace: NS }
spec:
  minAvailable: 75%
  selector: { matchLabels: { app: SERVICE } }
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: { name: SERVICE, namespace: NS }
spec:
  scaleTargetRef: { apiVersion: apps/v1, kind: Deployment, name: SERVICE }
  minReplicas: 3
  maxReplicas: 30
  metrics:
    - type: Pods
      pods:
        metric: { name: http_inflight_requests }
        target: { type: AverageValue, averageValue: "30" }
  behavior:
    scaleDown: { stabilizationWindowSeconds: 300 }
```
