# Chapter 19 - multi-region active-active

```bash
cd code/region
python latency.py --rtt-ms 70 --budget-ms 200
python failover.py --down ap-south-1 --lag-ms 300 --rpo-ms 500
python failover.py --down ap-south-1 --lag-ms 900 --rpo-ms 500   # refuses
```

- `router.py` - home-region ownership, local reads, redirect writes, promotion.
- `latency.py` - the arithmetic that forbids synchronous replication.
- `failover.py` - the runbook as code, including the refusal when the peer is
  further behind than the RPO allows.
