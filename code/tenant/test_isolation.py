"""Chapter 17: the design goal, as two assertions.

    python test_isolation.py

1. every request touches exactly one pod
2. killing one pod affects only its tenants -- 1/N of them
"""

from __future__ import annotations

import zlib

from router import PodRouter

TENANTS = 1_000
PODS = 100


def build() -> PodRouter:
    table = {f"t{i}": zlib.crc32(f"t{i}".encode()) % PODS for i in range(TENANTS)}
    return PodRouter(table)


def main() -> None:
    router = build()
    touched: dict[str, set[int]] = {}

    # 1. one unit of work, one pod
    for t in router.table:
        for _ in range(10):                     # ten requests per tenant
            touched.setdefault(t, set()).add(router.pod_for(t))

    multi = [t for t, pods in touched.items() if len(pods) > 1]
    print(f"requests            : {TENANTS * 10:,}")
    print(f"tenants on >1 pod   : {len(multi)}   (must be 0)")

    # 2. blast radius
    dead = 42
    affected = [t for t, p in router.table.items() if p == dead]
    print(f"pod {dead} hosts        : {len(affected)} tenants")
    print(f"blast radius        : {len(affected) / TENANTS:.1%}   (target <= 1/{PODS} ~ 1%)")

    assert not multi
    assert len(affected) <= TENANTS / PODS * 2
    print("OK: isolation holds")


if __name__ == "__main__":
    main()
