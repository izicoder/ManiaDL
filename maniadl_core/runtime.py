"""Mutable per-run state and the shared console.

Keeping this in one module avoids circular imports between the UI, API and
download layers.
"""

from __future__ import annotations

import time
from collections import deque

from rich.console import Console

from . import util
from .constants import HOST_CONCURRENCY, HOST_INTERVAL, MIRRORS

console = Console()

# Last events shown in the live "Log" panel.
log_lines: deque[str] = deque(maxlen=14)

stats = {"ok": 0, "fail": 0, "active": 0, "bytes": 0}

# Per-mirror health. "until" is a Unix timestamp: while in the future the host
# is cooling down after a 429.
mstats = {
    name: {"ok": 0, "fail": 0, "streak": 0, "until": 0.0, "last": 0.0}
    for name, _ in MIRRORS
}

# Per-host rate limiting. Created lazily because asyncio primitives must be
# constructed inside the running loop.
host_state: dict[str, dict] = {}

mirrors_exhausted = False
HOST_MIN_INTERVAL = HOST_INTERVAL
HOST_MAX_CONCURRENCY = HOST_CONCURRENCY


def log(message: str) -> None:
    log_lines.append(f"[dim]{time.strftime('%H:%M:%S')}[/] {message}")


def reset_run() -> None:
    """Reset counters and pacing state between runs."""
    global mirrors_exhausted

    stats.update(ok=0, fail=0, active=0, bytes=0)
    for entry in mstats.values():
        entry.update(ok=0, fail=0, streak=0, until=0.0, last=0.0)
    host_state.clear()
    log_lines.clear()
    mirrors_exhausted = False
    util.reset_disk_cache()
