# Chapter 18 - collaborative editing

```bash
cd code/collab
python simulate.py --ops 400 --seed 7
python reconnect.py --doc-size-mb 1 --offline-ops 400
```

- `tree.py` - fractional indexing (with rebalance on precision exhaustion) and
  the cycle check only the server can perform.
- `simulate.py` - fuzz: the same ops applied in two orders to two replicas must
  converge.
- `reconnect.py` - replay versus redownload, and where the crossover sits.
