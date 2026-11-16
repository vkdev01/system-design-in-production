"""Chapter 18: a document tree with fractional ordering and cycle rejection."""

from __future__ import annotations

from dataclasses import dataclass, field


class CycleRejected(Exception):
    pass


@dataclass
class Node:
    id: str
    parent: str | None = None
    pos: float = 0.5
    props: dict = field(default_factory=dict)


class Doc:
    def __init__(self):
        self.nodes: dict[str, Node] = {"root": Node("root", None, 0.5)}
        self.version = 0

    # ---- structure ----
    def children(self, parent_id: str) -> list[Node]:
        kids = [n for n in self.nodes.values() if n.parent == parent_id]
        return sorted(kids, key=lambda n: n.pos)

    def insert_between(self, parent_id: str, left: Node | None, right: Node | None,
                       node_id: str) -> float:
        lo = left.pos if left else 0.0
        hi = right.pos if right else 1.0
        if hi - lo < 1e-12:                       # precision exhausted in this gap
            self.rebalance(parent_id)
            kids = self.children(parent_id)
            left = next((k for k in kids if k.pos <= lo), None)
            right = next((k for k in kids if k.pos > lo), None)
            return self.insert_between(parent_id, left, right, node_id)
        pos = (lo + hi) / 2
        self.nodes[node_id] = Node(node_id, parent_id, pos)
        self.version += 1
        return pos

    def rebalance(self, parent_id: str) -> None:
        kids = self.children(parent_id)
        for i, k in enumerate(kids):
            k.pos = (i + 1) / (len(kids) + 1)
        self.version += 1

    # ---- the check only the server can do ----
    def would_cycle(self, node_id: str, new_parent: str) -> bool:
        seen: set[str] = set()
        cur: str | None = new_parent
        while cur is not None and cur not in seen:
            if cur == node_id:
                return True
            seen.add(cur)
            cur = self.nodes[cur].parent if cur in self.nodes else None
        return False

    def reparent(self, node_id: str, new_parent: str, pos: float | None = None) -> None:
        if self.would_cycle(node_id, new_parent):
            raise CycleRejected(f"{node_id} -> {new_parent} would form a cycle")
        node = self.nodes[node_id]
        node.parent = new_parent
        node.pos = pos if pos is not None else 0.5
        self.version += 1

    # ---- convergence ----
    def state_hash(self) -> str:
        import hashlib
        payload = "|".join(
            f"{n.id}:{n.parent}:{round(n.pos, 12)}:{sorted(n.props.items())}"
            for n in sorted(self.nodes.values(), key=lambda x: x.id)
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:12]
