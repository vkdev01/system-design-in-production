"""Chapter 14: the fan-out tier decision.

Push when the write cost is bounded by the follower count; pull when it is not.
The threshold is a property of your write budget, not a magic number.
"""

from __future__ import annotations

from dataclasses import dataclass

PUSH_THRESHOLD = 100_000        # followers
CELEB_MERGE_CAP = 8             # sources merged per read


@dataclass
class Post:
    id: str
    author: str
    ts: float


def tier(followers: int) -> str:
    return "push" if followers < PUSH_THRESHOLD else "pull"


class Fanout:
    def __init__(self, store):
        self.store = store
        self.writes = 0
        self.pushed_posts = 0
        self.pulled_posts = 0

    def deliver(self, post: Post, followers: list[str]) -> str:
        mode = tier(len(followers))
        if mode == "push":
            for f in followers:
                self.store.add(f, post.id, post.ts)
                self.writes += 1
            self.pushed_posts += 1
        else:
            # one write into the author's recent list, not fifty million
            self.store.add("celeb:" + post.author, post.id, post.ts)
            self.writes += 1
            self.pulled_posts += 1
        return mode

    def read(self, user: str, celeb_authors: list[str], limit: int = 20) -> list[str]:
        sources = [self.store.head(user, limit)]
        for author in celeb_authors[:CELEB_MERGE_CAP]:      # bounded on purpose
            sources.append(self.store.head("celeb:" + author, limit))
        from timeline import kway_merge
        return kway_merge(sources, limit)
