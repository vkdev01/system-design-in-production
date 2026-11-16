"""Chapter 10: the paged KV block allocator.

A sequence holds a *block table* mapping logical token positions to physical
pages, exactly like virtual memory. Allocating a page at a time instead of
reserving max_seq_len is what turns 60-80% waste into under 4%.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class OutOfBlocks(RuntimeError):
    pass


@dataclass
class BlockAllocator:
    num_blocks: int
    block_size: int = 16
    free: list[int] = field(default_factory=list)
    ref_count: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.free = list(range(self.num_blocks))

    # ---- sizing ----
    def blocks_for(self, tokens: int) -> int:
        """Pages needed for `tokens`, rounding up to a page."""
        return (tokens + self.block_size - 1) // self.block_size

    def free_blocks(self) -> int:
        return len(self.free)

    def utilisation(self) -> float:
        total = len(self.free) + len(self.ref_count)
        return 0.0 if total == 0 else 1 - len(self.free) / total

    # ---- lifecycle ----
    def allocate(self, n: int) -> list[int]:
        if n > len(self.free):
            raise OutOfBlocks(f"need {n} blocks, {len(self.free)} free")
        out = [self.free.pop() for _ in range(n)]
        for b in out:
            self.ref_count[b] = 1
        return out

    def free_all(self, blocks: list[int]) -> None:
        for b in blocks:
            self.ref_count[b] -= 1
            if self.ref_count[b] <= 0:
                del self.ref_count[b]
                self.free.append(b)

    def share(self, blocks: list[int]) -> None:
        """Prefix caching: two sequences point at the same physical pages."""
        for b in blocks:
            self.ref_count[b] += 1

    def check(self) -> None:
        """Invariant: every block is either free or owned by someone, never both."""
        assert len(self.free) == len(set(self.free)), "duplicate free block"
        assert not (set(self.free) & set(self.ref_count)), "block both free and owned"
        assert all(c > 0 for c in self.ref_count.values()), "zero refcount held"
