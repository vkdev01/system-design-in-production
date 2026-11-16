# Chapter 17 - multi-tenant isolation

```bash
cd code/tenant
python test_isolation.py
# requests            : 10,000
# tenants on >1 pod   : 0   (must be 0)
# pod 42 hosts        : 11 tenants
# blast radius        : 1.1%   (target <= 1/100 ~ 1%)
# OK: isolation holds

python move.py --tenant t7 --from-pod 42 --to-pod 77
```

- `router.py` - Sorting Hat: versioned tenant -> pod table, one lookup.
- `test_isolation.py` - the two assertions that define the design: one pod per
  unit of work, and a 1/N blast radius.
- `move.py` - the Pod Mover: freeze, copy, dual-write, flip, verify.
