"""Chapter 18: what a reconnect actually costs.

    python reconnect.py --doc-size-mb 1 --offline-ops 400

Compares replaying the offline op log against downloading a snapshot and
re-applying locally. The crossover is why real systems redownload.
"""

from __future__ import annotations

import argparse

OP_BYTES = 200
OP_APPLY_MS = 0.02          # 20 microseconds per op, locally
MBPS = 100


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-size-mb", type=float, default=1.0)
    ap.add_argument("--offline-ops", type=int, default=400)
    args = ap.parse_args()

    replay_ms = args.offline_ops * OP_APPLY_MS
    download_ms = args.doc_size_mb * 8 / MBPS * 1000
    reapply_ms = args.offline_ops * OP_APPLY_MS
    print(f"offline ops        : {args.offline_ops:,}")
    print(f"replay the log     : {replay_ms:>8.1f} ms")
    print(f"download snapshot  : {download_ms:>8.1f} ms  ({args.doc_size_mb} MB at {MBPS} Mbps)")
    print(f"re-apply locally   : {reapply_ms:>8.1f} ms")
    print(f"download + reapply : {download_ms + reapply_ms:>8.1f} ms")
    print()
    # crossover: download wins once replay exceeds the snapshot transfer
    crossover = int(download_ms / OP_APPLY_MS)
    print(f"replay beats download below ~{crossover:,} offline ops")


if __name__ == "__main__":
    main()
