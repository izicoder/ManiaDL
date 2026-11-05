#!/usr/bin/env python3
"""
ManiaDL - bulk osu!mania beatmap downloader for osu!lazer.

Setup (uv):
    uv sync
    uv run maniadl.py

The window keeps every filter in the left panel and all run status (progress,
stats, mirror health, log, failed sets) in the right panel.

Everything you enter (API keys, folder, filters) is saved to
mania_dl_config.json next to this script and loaded again next launch.
That file contains your API secret in plain text: keep it out of git.

Each download folder gets one status.json holding downloaded and failed sets;
nothing else is written there besides the .osz files.
"""

from maniadl_core.gui import main


if __name__ == "__main__":
    main()
