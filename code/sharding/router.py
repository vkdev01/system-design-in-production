"""Chapter 02: the shard router.

Routing is deterministic and stateless: the same workspace always lands on the
same logical shard, and the logical shard always maps to the same physical
database for a given shard-map version.

480 logical shards over 32 physical databases (15 each). 480 and not 512
because 480 divides by 40, 48, 60, 80, 96: the fleet can grow in ~25% steps
instead of doubling every time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

LOGICAL_SHARDS = 480
PHYSICAL_DATABASES = 32
SHARDS_PER_DATABASE = LOGICAL_SHARDS // PHYSICAL_DATABASES  # 15


@dataclass(frozen=True)
class Location:
    database: str
    schema: str
    shard_index: int

    @property
    def dsn_key(self) -> str:
        return self.database


def shard_index(workspace_id: str, logical_shards: int = LOGICAL_SHARDS) -> int:
    """Uniform mapping from a workspace UUID to a logical shard."""
    digest = hashlib.sha256(workspace_id.encode()).digest()
    return int.from_bytes(digest[:8], "big") % logical_shards


def location_for(
    workspace_id: str,
    physical_databases: int = PHYSICAL_DATABASES,
    shards_per_database: int = SHARDS_PER_DATABASE,
) -> Location:
    """workspace_id -> (physical database, logical schema).

    During a re-shard only `physical_databases` and `shards_per_database`
    change. The application's call site does not.
    """
    idx = shard_index(workspace_id)
    db = idx // shards_per_database
    schema = f"schema{idx % shards_per_database + 1:03d}"
    return Location(
        database=f"notion_db_{db:02d}",
        schema=schema,
        shard_index=idx,
    )


def distribution_check(n: int = 100_000) -> dict[str, int]:
    """Sanity check: no shard should be wildly over- or under-loaded."""
    counts: dict[str, int] = {}
    for i in range(n):
        loc = location_for(f"00000000-0000-0000-0000-{i:012d}")
        counts[loc.database] = counts.get(loc.database, 0) + 1
    return counts


if __name__ == "__main__":
    print(location_for("3f2b8c1e-1a2b-4c3d-9e8f-0123456789ab"))
    dist = distribution_check()
    lo, hi = min(dist.values()), max(dist.values())
    print(f"databases={len(dist)} min={lo} max={hi} skew={hi / lo:.2f}x")
