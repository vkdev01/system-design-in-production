"""Chapter 12: the run store.

SQLite here so the demo runs anywhere; the schema in migrations/001.sql is the
Postgres version and the API is identical. The two operations that matter are
`claim` (lease a run without two workers taking it) and `append` (write the step
before the side effect).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, task TEXT, state TEXT DEFAULT 'pending',
    steps INTEGER DEFAULT 0, tokens INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0,
    max_steps INTEGER DEFAULT 200, max_cost_usd REAL DEFAULT 5,
    lease_expires REAL, summary TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT, seq INTEGER, kind TEXT, tool_name TEXT, payload TEXT,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS tool_cache (key TEXT PRIMARY KEY, result TEXT);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.executescript(SCHEMA)

    # ---- runs ----
    def create(self, task: str, max_steps: int = 200, max_cost: float = 5.0) -> str:
        rid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO runs (id, task, max_steps, max_cost_usd) VALUES (?,?,?,?)",
            (rid, task, max_steps, max_cost),
        )
        return rid

    def claim(self, rid: str, lease_seconds: float = 60) -> bool:
        """Take a lease. Fails if another worker holds a live one."""
        now = time.time()
        cur = self.db.execute(
            "UPDATE runs SET state='running', lease_expires=? "
            "WHERE id=? AND (lease_expires IS NULL OR lease_expires < ?) "
            "AND state IN ('pending','running')",
            (now + lease_seconds, rid, now),
        )
        return cur.rowcount == 1

    def get(self, rid: str) -> dict:
        row = self.db.execute(
            "SELECT id, task, state, steps, tokens, cost_usd, max_steps, max_cost_usd, summary "
            "FROM runs WHERE id=?", (rid,)
        ).fetchone()
        keys = ("id", "task", "state", "steps", "tokens", "cost_usd",
                "max_steps", "max_cost_usd", "summary")
        return dict(zip(keys, row))

    def release(self, rid: str) -> None:
        """Hand the lease back after a completed step.

        A worker that crashes mid-step never reaches this, which is exactly how
        the repair loop discovers the run.
        """
        self.db.execute("UPDATE runs SET lease_expires=NULL WHERE id=?", (rid,))

    def finish(self, rid: str, state: str) -> None:
        self.db.execute(
            "UPDATE runs SET state=?, lease_expires=NULL WHERE id=?", (state, rid)
        )

    def stuck(self) -> list[str]:
        now = time.time()
        return [r[0] for r in self.db.execute(
            "SELECT id FROM runs WHERE state='running' AND lease_expires < ?", (now,)
        )]

    # ---- steps ----
    def next_seq(self, rid: str) -> int:
        row = self.db.execute("SELECT COALESCE(MAX(seq),0) FROM steps WHERE run_id=?", (rid,)).fetchone()
        return int(row[0]) + 1

    def append(self, rid: str, kind: str, payload: dict, tool_name: str | None = None) -> int:
        seq = self.next_seq(rid)
        self.db.execute(
            "INSERT INTO steps (run_id, seq, kind, tool_name, payload) VALUES (?,?,?,?,?)",
            (rid, seq, kind, tool_name, json.dumps(payload)),
        )
        self.db.execute(
            "UPDATE runs SET steps = steps + 1, tokens = tokens + ? WHERE id=?",
            (payload.get("tokens", 0), rid),
        )
        return seq

    def steps(self, rid: str) -> list[dict]:
        return [
            {"seq": s, "kind": k, "tool": t, "payload": json.loads(p)}
            for s, k, t, p in self.db.execute(
                "SELECT seq, kind, tool_name, payload FROM steps WHERE run_id=? ORDER BY seq", (rid,)
            )
        ]

    # ---- tool cache ----
    def cache_get(self, key: str):
        row = self.db.execute("SELECT result FROM tool_cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache_put(self, key: str, result: dict) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO tool_cache (key, result) VALUES (?,?)",
            (key, json.dumps(result)),
        )
