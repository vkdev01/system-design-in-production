"""Chapter 18: why the server's order is the tiebreak.

    python simulate.py --ops 300 --seed 7

Three replicas, one op set:

  A  applies ops in server order                     -> the reference state
  B  receives them out of order but honours `seq`    -> converges with A
  C  receives them out of order and ignores `seq`    -> diverges

That difference between B and C is the whole reason a central sequencer is worth
having: last-writer-wins is only well defined once somebody defines "last".
"""

from __future__ import annotations

import argparse
import random

from tree import CycleRejected, Doc


def make_ops(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    ops: list[dict] = []
    ids = ["root"]
    for seq in range(n):
        kind = rng.choice(["add", "add", "reparent", "prop"])
        if kind == "add" or len(ids) < 3:
            new_id = f"n{len(ids)}"
            ops.append({
                "seq": seq, "kind": "add", "id": new_id,
                "parent": rng.choice(ids), "pos": rng.random(),
            })
            ids.append(new_id)
        elif kind == "reparent":
            ops.append({
                "seq": seq, "kind": "reparent", "id": rng.choice(ids[1:]),
                "parent": rng.choice(ids), "pos": rng.random(),
            })
        else:
            ops.append({
                "seq": seq, "kind": "prop", "id": rng.choice(ids[1:]),
                "key": rng.choice(["color", "width", "locked"]),
                "value": rng.choice(["red", "blue", 12, 24, True]),
            })
    return ops


def apply(doc: Doc, op: dict) -> None:
    try:
        if op["kind"] == "add":
            if op["id"] not in doc.nodes:
                doc.nodes[op["id"]] = __import__("tree").Node(
                    op["id"], op["parent"], op["pos"]
                )
                doc.version += 1
        elif op["kind"] == "reparent":
            if op["id"] in doc.nodes and op["parent"] in doc.nodes:
                doc.reparent(op["id"], op["parent"], op["pos"])
        else:
            if op["id"] in doc.nodes:
                doc.nodes[op["id"]].props[op["key"]] = op["value"]
                doc.version += 1
    except CycleRejected:
        pass                      # the server refuses it; every replica agrees


def replay(ops: list[dict], honour_seq: bool) -> Doc:
    doc = Doc()
    ordered = sorted(ops, key=lambda o: o["seq"]) if honour_seq else ops
    for op in ordered:
        apply(doc, op)
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ops", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    ops = make_ops(args.ops, args.seed)
    shuffled = ops[:]
    random.Random(args.seed + 1).shuffle(shuffled)

    a = replay(ops, honour_seq=True)               # server order
    b = replay(shuffled, honour_seq=True)          # out of order, seq honoured
    c = replay(shuffled, honour_seq=False)         # out of order, seq ignored

    print(f"ops {len(ops)}  nodes {len(a.nodes)}")
    print(f"  A server order, honouring seq : {a.state_hash()}")
    print(f"  B shuffled,     honouring seq : {b.state_hash()}  "
          f"{'converged' if b.state_hash() == a.state_hash() else 'DIVERGED'}")
    print(f"  C shuffled,     ignoring seq  : {c.state_hash()}  "
          f"{'converged' if c.state_hash() == a.state_hash() else 'DIVERGED'}")
    print()
    print("B == A because the sequence number defines 'last'.")
    print("C != A because without it, arrival order silently picks a different winner.")


if __name__ == "__main__":
    main()
