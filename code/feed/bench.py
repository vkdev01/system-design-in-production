"""Chapter 14: why the hybrid is the only survivable design.

    python bench.py

Prints the write and read cost of the three strategies on the follower
distribution the chapter uses, so the argument is checkable rather than asserted.
"""

from __future__ import annotations

NORMAL_POSTS_PER_S = 980        # 98% of posts
CELEB_POSTS_PER_S = 20          # 2%, from accounts with millions of followers
NORMAL_FOLLOWERS = 150          # median
CELEB_FOLLOWERS = 10_000_000    # the tail
READS_PER_S = 60_000            # peak feed reads
AVG_FOLLOWEES = 800             # a heavy reader's graph


def main() -> None:
    print("write side")
    push_all = NORMAL_POSTS_PER_S * NORMAL_FOLLOWERS + CELEB_POSTS_PER_S * CELEB_FOLLOWERS
    hybrid = NORMAL_POSTS_PER_S * NORMAL_FOLLOWERS + CELEB_POSTS_PER_S * 1
    print(f"  push-everything : {push_all:>15,.0f} timeline writes/s")
    print(f"  hybrid          : {hybrid:>15,.0f} timeline writes/s"
          f"   ({push_all / hybrid:,.0f}x less)")
    print()
    print("read side")
    pull_all = READS_PER_S * AVG_FOLLOWEES
    print(f"  pull-everything : {pull_all:>15,.0f} list reads/s")
    print(f"  hybrid          : {READS_PER_S:>15,.0f} head reads/s"
          f"   + <= 8 celebrity lists per read")
    print()
    print("memory")
    full = 50_000_000 * 800 * 120 / 1e9
    head = 50_000_000 * 40 * 120 / 1e9
    print(f"  full timelines  : {full:>15,.0f} GB of Redis")
    print(f"  head only (40)  : {head:>15,.0f} GB of Redis   ({full / head:,.0f}x less)")


if __name__ == "__main__":
    main()
