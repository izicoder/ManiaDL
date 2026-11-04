"""ManiaDL unit tests (offline; no API or mirror calls)."""

from rich.console import Console

from maniadl_core import runtime

# Keep the suite quiet; individual tests can patch in a recording console.
runtime.console = Console(quiet=True)
