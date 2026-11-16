# Chapter 06 - rate limiting and load shedding

```bash
docker compose -f deploy/compose/ratelimit.yml up --build
k6 run code/ratelimit/loadtest/burst.js     # 1000 requests from one user
```

| File | Limiter |
|---|---|
| `token_bucket.lua` | request rate limiter, atomic, with a per-request cost |
| `middleware.go` | the Go wiring, including the fail-open rule and the 429 body |
| `concurrency.py` | in-flight limiter for CPU-bound endpoints |
| `fleet_shed.py` | reserve a fraction of the fleet for critical methods |
| `worker_shed.go` | the per-box last line of defence |

Drills: kill Redis (everything must still succeed), burst, hot key, shed and
un-shed, kill switch.
