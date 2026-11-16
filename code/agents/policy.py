"""Chapter 12: tool policy.

A model asking to run something is a request, not a decision. Anything that can
touch the network or the filesystem outside the workspace is denied by default,
and privileged tools are denied outright after an untrusted read.
"""

from __future__ import annotations

ALLOW = {
    "read_file", "write_file", "run_tests", "slow_tool", "list_dir",
}
NEEDS_APPROVAL = {"git_push", "deploy", "delete_branch"}
DENY = {"shell_unrestricted", "network_fetch_any", "rm_rf"}

_tainted = False


def mark_untrusted_read() -> None:
    """Called after reading content the model did not author (web, user upload)."""
    global _tainted
    _tainted = True


def reset() -> None:
    global _tainted
    _tainted = False


def allows(tool: str) -> tuple[bool, str]:
    if tool in DENY:
        return False, "denied by policy"
    if tool in NEEDS_APPROVAL:
        return False, "needs human approval"
    if _tainted and tool in {"write_file", "run_tests"}:
        # after untrusted input, only read-only tools are safe
        return False, "untrusted content read; privileged tools disabled"
    return True, "allowed"
