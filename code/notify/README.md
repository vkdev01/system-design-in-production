# Chapter 09 - notification fan-out

```bash
go run ./code/notify/cmd/burst --rate 17000 --seconds 60
python code/notify/sizing.py     # how many connections does the burst need?
```

- `pipeline.go` - bounded buffer, demand-driven pusher, shed on overflow
- `retry.go` - 4xx terminal, 429/5xx retryable with jitter, DLQ
- `dedupe.go` - collapse keys; fails open (a duplicate push beats a missing one)
- `sizing.py` - burst rate -> in-flight limit -> connections -> buffer

Drill: raise `--provider-inflight` above the provider's real limit and watch the
429s appear immediately.
