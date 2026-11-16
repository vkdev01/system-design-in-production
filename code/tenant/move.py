"""Chapter 17: the Pod Mover -- freeze, copy, dual-write, flip, verify.

    python move.py --tenant t7 --from-pod 42 --to-pod 77
"""

from __future__ import annotations

import argparse
import time


class Store:
    """In-memory stand-in for a pod's MySQL."""

    def __init__(self):
        self.rows: dict[int, dict[str, dict]] = {}

    def write(self, pod: int, tenant: str, key: str, value) -> None:
        self.rows.setdefault(pod, {}).setdefault(tenant, {})[key] = value

    def dump(self, pod: int, tenant: str) -> dict:
        return dict(self.rows.get(pod, {}).get(tenant, {}))

    def restore(self, pod: int, tenant: str, rows: dict) -> None:
        self.rows.setdefault(pod, {})[tenant] = dict(rows)


def move(tenant: str, from_pod: int, to_pod: int, store: Store, router) -> dict:
    log = []

    snapshot = store.dump(from_pod, tenant)
    log.append(("freeze writes", len(snapshot)))

    store.restore(to_pod, tenant, snapshot)
    log.append(("copy", len(snapshot)))

    # dual-write the gap: anything written during the copy lands in both
    for k, v in store.dump(from_pod, tenant).items():
        if store.dump(to_pod, tenant).get(k) != v:
            store.write(to_pod, tenant, k, v)
    log.append(("dual write catch-up", len(store.dump(to_pod, tenant))))

    accepted = router.apply({**router.table, tenant: to_pod}, router.version + 1)
    log.append(("flip routing", int(accepted)))
    time.sleep(0.05)                                   # LB refresh, ~1 s in prod
    log.append(("wait for refresh", 0))

    ok = store.dump(to_pod, tenant) == store.dump(from_pod, tenant)
    log.append(("verify", int(ok)))
    return {"tenant": tenant, "from": from_pod, "to": to_pod, "ok": ok, "log": log}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="t7")
    ap.add_argument("--from-pod", type=int, default=42)
    ap.add_argument("--to-pod", type=int, default=77)
    args = ap.parse_args()

    from router import PodRouter
    store = Store()
    for i in range(500):
        store.write(args.from_pod, args.tenant, f"row{i}", {"v": i})
    router = PodRouter({args.tenant: args.from_pod})

    result = move(args.tenant, args.from_pod, args.to_pod, store, router)
    for step, n in result["log"]:
        print(f"  {step:22} {n}")
    print(f"routed to pod {router.pod_for(args.tenant)}  verified={result['ok']}")
