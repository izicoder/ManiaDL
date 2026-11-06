"""Tunables, mirrors, API constants and persisted-setting keys."""

from __future__ import annotations

import sys
from pathlib import Path

# ---- osu! API --------------------------------------------------------------
API = "https://osu.ppy.sh/api/v2"
TOKEN_URL = "https://osu.ppy.sh/oauth/token"
API_UA = "osu-mania-downloader/2.0"

# Community mirrors. Keep the most reliable ones first; the scheduler also
# tracks health and rotates away from mirrors that fail or rate-limit.
MIRRORS = [
    ("nerinyan", "https://api.nerinyan.moe/d/{id}"),
    ("nekoha", "https://mirror.nekoha.moe/api/download/{id}"),
    ("catboy", "https://catboy.best/d/{id}n"),
    ("beatconnect", "https://beatconnect.io/b/{id}/"),
    ("osu.direct", "https://osu.direct/api/d/{id}"),
    ("sayobot", "https://dl.sayobot.cn/beatmaps/download/full/{id}"),
    ("catboy-video", "https://catboy.best/d/{id}"),
]

# Mirror requests need a browser-ish UA + Referer or Cloudflare returns 403.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# ---- Download behaviour ----------------------------------------------------
RETRIES = 6
SEARCH_RETRIES = 5
SEARCH_MAX_PAGES = 1000
FILE_TIMEOUT = 900
SOCK_READ_TIMEOUT = 120
CONNECT_TIMEOUT = 15
MIN_FREE_GB = 5.0
CHUNK_SIZE = 128 * 1024
MAX_WORKERS = 32
MAX_RETRY_AFTER = 300

# Community mirrors are rate-limited automatically: requests are spaced per
# host, concurrency is capped and 429s park the host. No user toggle.
HOST_INTERVAL = 0.9
HOST_CONCURRENCY = 2
SEARCH_DELAY = 1.8
BATCH_PAUSE = 3.0

# Status persistence is batched to avoid rewriting JSON on every set.
SAVE_EVERY = 8
SAVE_INTERVAL = 5.0
DISK_CACHE_TTL = 3.0

# ---- Persistence -----------------------------------------------------------
if getattr(sys, "frozen", False):
    HERE = Path(sys.executable).resolve().parent
else:
    # This module lives in maniadl_core/, but state belongs next to maniadl.py.
    HERE = Path(__file__).resolve().parent.parent

CONFIG_PATH = HERE / "mania_dl_config.json"
DEFAULT_OUT = HERE / "downloads"
STATUS_NAME = "status.json"
STATUS_VERSION = 2
LEGACY_IDS_NAME = "downloaded_ids.txt"
LEGACY_FAILED_NAME = "failed.txt"
FAILED_LINKS_NAME = "failed_links.txt"

# ---- Domain data -----------------------------------------------------------
STATUS_SETS = {
    "graveyard": {"graveyard"},
    "ranked": {"ranked", "approved"},
    "loved": {"loved"},
    "qualified": {"qualified"},
    "pending": {"pending", "wip"},
}

# What to send to the osu! API for each user-facing status. The API treats
# "ranked" as ranked+approved and has no combined "pending" bucket.
API_STATUSES = {
    "graveyard": ("graveyard",),
    "ranked": ("ranked",),
    "loved": ("loved",),
    "qualified": ("qualified",),
    "pending": ("pending", "wip"),
}

SORTS = [
    "favourites_desc",
    "plays_desc",
    "ranked_desc",
    "updated_desc",
    "difficulty_desc",
    "relevance_desc",
]

# Friendly combobox labels; the stored config keeps the raw API sort key.
SORT_LABELS = {
    "favourites_desc": "Most favourites",
    "plays_desc": "Most played",
    "ranked_desc": "Recently ranked",
    "updated_desc": "Recently updated",
    "difficulty_desc": "Difficulty",
    "relevance_desc": "Relevance",
}

# Legacy keys are required for reusing an existing config without prompting.
SETTING_KEYS = [
    "out",
    "statuses",
    "keys",
    "min_sr",
    "max_sr",
    "min_favs",
    "sort",
    "limit",
    "workers",
    "batch",
]

# New optional keys are filled with defaults on first run of this version.
NEW_SETTING_KEYS = [
    "advanced",
    "query",
    "title",
    "artist",
    "creator",
    "source",
    "exclude",
    "genre",
    "language",
    "bpm_range",
    "length_range",
    "notes_range",
    "min_plays",
    "ranked_range",
    "include_nsfw",
]
ADVANCED_KEYS = [
    "query",
    "title",
    "artist",
    "creator",
    "source",
    "exclude",
    "genre",
    "language",
    "bpm_range",
    "length_range",
    "notes_range",
    "min_plays",
    "ranked_range",
    "include_nsfw",
]

NEW_DEFAULTS = {
    "advanced": False,
    "query": "",
    "title": "",
    "artist": "",
    "creator": "",
    "source": "",
    "exclude": "",
    "genre": "",
    "language": "",
    "bpm_range": "",
    "length_range": "",
    "notes_range": "",
    "min_plays": 0,
    "ranked_range": "",
    "include_nsfw": False,
}

# Big upper bounds mean "no filter" in cfg_from_raw().
MAX_BPM = 9999.0
MAX_LENGTH = 10**9
MAX_NOTES = 10**9
