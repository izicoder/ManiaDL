#!/usr/bin/env python3
"""
ManiaDL - bulk osu!mania beatmap downloader for osu!lazer.

Setup (uv):
    uv venv
    uv pip install aiohttp rich
    uv run maniadl.py

Everything you enter (API keys, folder, filters) is saved to
mania_dl_config.json next to this script and offered again next run.
That file contains your API secret in plain text: keep it out of git.

Each download folder gets one status.json holding downloaded and failed sets.
Older single-file status/config files are imported and upgraded automatically
on first run.
"""

import asyncio

from maniadl_core.app import main
from maniadl_core.runtime import console


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Interrupted. Partial files cleaned up; re-run to resume.[/]"
        )
