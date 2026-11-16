"""Chapter 09: the capacity plan, in one function.

burst rate -> provider in-flight limit -> per-connection throughput ->
connections needed -> buffer size. Every number is either given or estimable,
and this is the answer to "how many pushers do you need?".
"""

from __future__ import annotations


def pusher_pool(burst_per_second: float, per_conn_limit: int, p50_latency_s: float,
                headroom: float = 1.5) -> dict:
    per_conn_throughput = per_conn_limit / p50_latency_s
    conns_needed = burst_per_second / per_conn_throughput
    return {
        "per_conn_limit": per_conn_limit,
        "per_conn_throughput": round(per_conn_throughput, 1),
        "conns_needed": round(conns_needed, 1),
        "conns_to_run": int(conns_needed * headroom) + 1,
        "buffer_per_collector": max(1000, int(burst_per_second * 0.5)),
    }


if __name__ == "__main__":
    # Discord's shape: >1M pushes/minute, 100 pending per connection, ~50ms sends.
    plan = pusher_pool(burst_per_second=1_000_000 / 60, per_conn_limit=100,
                       p50_latency_s=0.05)
    for k, v in plan.items():
        print(f"{k:>22}: {v}")
