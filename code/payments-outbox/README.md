# Chapter 05 - exactly-once money movement

```bash
docker compose -f deploy/compose/payments.yml up --build
python faults.py --mode timeout-after-charge   # money moved, answer lost
python repair.py                                # asks the provider what happened
psql "$DATABASE_URL" -f stuck.sql               # should be empty afterwards
```

`service.py` is the three-phase request. `repair.py` is the part that turns
at-least-once retries into at-most-once money movement. `faults.py` is how you
prove it, and it is the file to point at when someone asks how you test this.
