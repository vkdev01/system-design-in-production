"""Chapter 17: Sorting Hat. Tenant -> pod, versioned, cached, one lookup."""

from __future__ import annotations


class UnknownTenant(KeyError):
    pass


class PodRouter:
    def __init__(self, table: dict[str, int], version: int = 1):
        self.table = dict(table)
        self.version = version

    def pod_for(self, tenant: str) -> int:
        try:
            return self.table[tenant]
        except KeyError:
            raise UnknownTenant(tenant)

    def apply(self, new_table: dict[str, int], version: int) -> bool:
        """Hot reload. Only a newer version is accepted, so a stale push cannot
        roll the fleet backwards in the middle of a move."""
        if version <= self.version:
            return False
        self.table, self.version = dict(new_table), version
        return True


def middleware(router: PodRouter, pools: dict, dispatch):
    """Every request resolves to exactly one pod, and may only use that pool."""
    def handle(host: str, path: str):
        tenant = host.split(".")[0]
        pod = router.pod_for(tenant)
        conn = pools[pod]                     # the only datastore this request sees
        return dispatch(tenant, pod, conn, path)
    return handle
