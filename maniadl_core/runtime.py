"""Mutable per-run state and the shared log feed.

Keeping this in one module avoids circular imports between the UI, API and
download layers. The GUI subscribes to :func:`log` through a listener so it can
show events without polling a console.
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque

from . import util
from .constants import HOST_CONCURRENCY, HOST_INTERVAL, MIRRORS

# Last events, kept for diagnostics and simple callers.
log_lines: deque[str] = deque(maxlen=500)

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

_listener = None
_listener_lock = threading.Lock()
_stop = threading.Event()

# Rich-style tags still appear in a few log messages; strip them for the GUI.
_MARKUP = re.compile(
    r"\[/\]|\[(?:bold|dim|italic|underline|blink|reverse|conceal|strike|"
    r"black|red|green|yellow|blue|magenta|cyan|white|bright_[a-z]+|"
    r"on [a-z]+|link=[^\]]+)(?:\s+[a-z_]+)*\]",
    re.I,
)


def plain(text: str) -> str:
    """Remove rich-style markup so log lines are safe for plain widgets."""
    return _MARKUP.sub("", str(text))


def set_log_listener(listener) -> None:
    """Register a callable that receives every plain log line.

    The listener is invoked from the worker thread, so it must be thread-safe
    (the GUI pushes lines onto a queue).
    """
    global _listener
    with _listener_lock:
        _listener = listener


def log(message: str) -> None:
    line = f"{time.strftime('%H:%M:%S')}  {plain(message)}"
    log_lines.append(line)
    with _listener_lock:
        listener = _listener
    if listener is not None:
        try:
            listener(line)
        except Exception:
            # A broken UI listener must never stop a download.
            pass


def reset_run() -> None:
    """Reset counters and pacing state between runs."""
    global mirrors_exhausted

    stats.update(ok=0, fail=0, active=0, bytes=0)
    for entry in mstats.values():
        entry.update(ok=0, fail=0, streak=0, until=0.0, last=0.0)
    host_state.clear()
    log_lines.clear()
    mirrors_exhausted = False
    _stop.clear()
    util.reset_disk_cache()


def request_stop() -> None:
    """Ask the running job to stop after the current files/batch."""
    _stop.set()


def should_stop() -> bool:
    return _stop.is_set()
