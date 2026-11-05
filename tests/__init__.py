"""ManiaDL unit tests (offline; no API or mirror calls)."""

from maniadl_core import runtime

# Keep tests independent from whatever listener a previous GUI test installed.
runtime.set_log_listener(None)
