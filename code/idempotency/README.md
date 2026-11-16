# Chapter 04 - idempotent payment API

```bash
docker compose -f deploy/compose/idempotency.yml up --build
curl -sX POST localhost:8080/v1/charges \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: 9f1c1b7e-4b3a-4a1e-9a1e-1b2c3d4e5f60' \
  -d '{"account_id":"acme","amount":49900,"customer":"cus_123"}'
```

Run it twice. The second response is identical and carries
`Idempotent-Replayed: true`; the provider is called exactly once.

Then run the drill that matters: kill the container between the claim and the
provider call, restart, and retry with the same key. You should see a 409 while
the lease is live and a take-over after 30 seconds.
