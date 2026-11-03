#!/usr/bin/env python3
"""
osu!mania bulk beatmap downloader (Windows-friendly, rich TUI, built for osu!lazer).
Filter by key count(s), status(es), star rating, favourites.

Setup:
    pip install aiohttp rich
    python osu_mania_downloader.py

Everything you enter (API keys, folder, filters) is saved to
mania_dl_config.json next to this script and offered again next run:
just press Enter at "Use these settings?" to go straight to searching.
That file contains your API secret in plain text: keep it out of git.

Each download folder gets one status.json holding everything this tool
remembers about it: the sets already fetched and the ones that failed last
run. Keep it if you want sets to stay skipped after you import them into
lazer and delete their .osz.
"""

import asyncio
import getpass
import json
import os
import random
import re
import shutil
import sys
import time
import zipfile
from collections import deque
from pathlib import Path

import aiohttp
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm, FloatPrompt, IntPrompt, Prompt
from rich.table import Table

GUIDE = """[bold]How to get your osu! API keys[/]
1. Log in at [cyan]https://osu.ppy.sh[/].
2. Open your settings: [cyan]https://osu.ppy.sh/home/account/edit[/]
3. Scroll to the [bold]OAuth[/] section and click [bold]New OAuth Application[/].
4. Name it anything (e.g. "mania dl"). Callback URL: [cyan]http://localhost[/]
5. Click Register. You now see your [bold]Client ID[/] (a number) and
   [bold]Client Secret[/] (a long string). Copy both. If you lose the secret,
   you can reset it on the same page.
6. Keep the secret private. Never share it or post it publicly.
"""

# ---- Tunables -------------------------------------------------------------
API = "https://osu.ppy.sh/api/v2"
# Mirrors are ranked automatically by recent success. Edit if one dies.
# nerinyan was dropped: its API answers 404 for every set (and 530 on the root).
MIRRORS = [
    ("catboy", "https://catboy.best/d/{id}n"),
    ("beatconnect", "https://beatconnect.io/b/{id}/"),
    ("catboy-video", "https://catboy.best/d/{id}"),
    ("osu.direct", "https://osu.direct/api/d/{id}"),
]
RETRIES = 6  # attempts per set
# Mirrors sit behind Cloudflare, which 403s anything that smells like a script.
# A browser-like UA + Referer is the difference between 200 and 403.
# These are sent ONLY to mirrors: osu!'s own API 403s a browser UA that has no
# Origin/Referer (it looks like a fake browser), but accepts a plain one.
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
API_UA = "osu-mania-downloader/1.0"
# Don't set Accept-Encoding: aiohttp negotiates gzip/deflate itself, and forcing
# br would leave every response undecodable.
FILE_TIMEOUT = 600  # hard cap per file, seconds
SOCK_READ_TIMEOUT = 30  # no data for this long = stalled
CONNECT_TIMEOUT = 15
BATCH_PAUSE = 2.0  # seconds between batches
SEARCH_DELAY = 1.0  # seconds between API search pages
MIN_FREE_GB = 5.0  # stop if disk space drops below this

# When packed into an exe, __file__ points at a temp dir that is wiped on exit,
# so keep config + downloads next to the exe instead.
if getattr(sys, "frozen", False):
    HERE = Path(sys.executable).resolve().parent
else:
    HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "mania_dl_config.json"
DEFAULT_OUT = HERE / "downloads"
# Everything this tool remembers about a download folder lives in this one file,
# so a set is still skipped after you import it into lazer and delete its .osz
# (osu!lazer keeps maps in its own database, which the tool can't read).
STATUS_NAME = "status.json"
STATUS_VERSION = 1
# Old per-run text files; read once to seed status.json, never written again.
LEGACY_IDS_NAME = "downloaded_ids.txt"
LEGACY_FAILED_NAME = "failed.txt"

STATUS_SETS = {
    "graveyard": {"graveyard"},
    "ranked": {"ranked", "approved"},
    "loved": {"loved"},
    "qualified": {"qualified"},
    "pending": {"pending", "wip"},
}
SORTS = [
    "favourites_desc",
    "plays_desc",
    "ranked_desc",
    "updated_desc",
    "difficulty_desc",
]
SETTING_KEYS = [
    "out",
    "statuses",
    "keys",
    "min_sr",
    "max_sr",
    "min_favs",
    "sort",
    "limit",
    "slide_window",
    "workers",
    "batch",
]
# ---------------------------------------------------------------------------

console = Console()
log_lines: deque = deque(maxlen=10)
stats = {"ok": 0, "fail": 0, "active": 0, "bytes": 0}
mstats = {name: {"ok": 0, "streak": 0, "until": 0.0} for name, _ in MIRRORS}
# Set when every mirror has asked us to back off; the run stops instead of
# retrying, so a rate limit never turns into a ban.
mirrors_exhausted = False


class MirrorMiss(Exception):
    """Mirror refuses or lacks this set (HTTP 403/404); no point backing off."""


class RateLimited(Exception):
    """HTTP 429: the mirror wants us to come back later."""

    def __init__(self, seconds: int):
        super().__init__(f"rate limited, retry after {seconds}s")
        self.seconds = seconds


def mirror_headers(url: str) -> dict:
    """A Referer from the mirror's own site; Cloudflare likes it."""
    scheme, _, rest = url.partition("://")
    host = rest.split("/", 1)[0]
    return {"Referer": f"{scheme}://{host}/"}


def mirror_host(template: str) -> str:
    return template.split("://", 1)[-1].split("/", 1)[0]


def choose_mirror(attempt: int):
    """Pick the healthiest mirror that isn't cooling down after a 429.

    Returns (mirror, wait). A 429 means "come back later", not "fail this set",
    so the mirror is parked and other mirrors take over; a task never blocks the
    whole batch on one bad mirror. `wait` is only non-zero when every mirror is
    parked, in which case the soonest one is returned anyway.
    """
    now = time.time()
    ready = [m for m in MIRRORS if mstats[m[0]]["until"] <= now]
    if not ready:
        soonest = min(MIRRORS, key=lambda m: mstats[m[0]]["until"])
        return soonest, mstats[soonest[0]]["until"] - now
    ranked = sorted(ready, key=lambda m: (mstats[m[0]]["streak"], -mstats[m[0]]["ok"]))
    return ranked[attempt % len(ranked)], 0.0


def log(msg: str) -> None:
    log_lines.append(f"[dim]{time.strftime('%H:%M:%S')}[/] {msg}")


# ---- saved settings -------------------------------------------------------
def load_saved() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_saved(data: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(CONFIG_PATH, 0o600)  # limited effect on Windows
        except OSError:
            pass
    except OSError as e:
        console.print(f"[yellow]Couldn't save settings: {e}[/]")


def as_text(v) -> str:
    """Saved statuses/keys may be a list (older config) or a string."""
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    return str(v)


def as_bool(v) -> bool:
    """Saved toggles may be a real bool, or a string like "yes"/"false"."""
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


# ---- helpers --------------------------------------------------------------
def free_gb(path: Path) -> float:
    p = path
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free / 1e9


def scan_existing(folder: Path) -> set:
    """IDs already on disk: '123.osz' / '123 Artist - Title.osz' files."""
    ids = set()
    if not folder.exists():
        return ids
    for p in folder.iterdir():
        m = re.match(r"(\d+)(?:[ .]|$)", p.name)
        if m and p.suffix.lower() == ".osz":
            ids.add(int(m.group(1)))
    return ids


def _stamp(ts: float = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts or time.time()))


class Status:
    """A download folder's memory, kept in a single status.json.

    Holds the set IDs already fetched (with timestamps) and the IDs that failed
    last run. Writes are atomic (temp file + os.replace), so killing the process
    mid-save can never leave a truncated status.json behind.
    """

    def __init__(self, folder: Path):
        self.folder = folder
        self.path = folder / STATUS_NAME
        self.downloaded: dict = {}  # {"set id": timestamp}
        self.failed: list = []
        self.updated = ""

    def load(self) -> "Status":
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError:
            data = None
        except ValueError:
            console.print(f"[yellow]![/] {STATUS_NAME} isn't valid JSON; rebuilding it.")
            data = None
        if isinstance(data, dict):
            raw = data.get("downloaded") or {}
            if isinstance(raw, dict):
                self.downloaded = {str(k): str(v) for k, v in raw.items()}
            elif isinstance(raw, list):  # tolerate a bare list of IDs
                self.downloaded = {str(k): "" for k in raw}
            kept = []
            for x in data.get("failed") or []:
                try:
                    kept.append(int(x))
                except (TypeError, ValueError):
                    pass
            self.failed = kept
            self.updated = str(data.get("updated") or "")
        self._migrate_legacy()
        return self

    def _migrate_legacy(self) -> None:
        """Fold the old downloaded_ids.txt / failed.txt in once, if they exist."""
        if self.path.exists():
            return
        moved = []
        old_ids = self.folder / LEGACY_IDS_NAME
        try:
            stamp = _stamp(old_ids.stat().st_mtime)
        except OSError:
            stamp = ""
        try:
            for tok in old_ids.read_text(encoding="utf-8").split():
                if tok.isdigit() and tok not in self.downloaded:
                    self.downloaded[tok] = stamp
            moved.append(LEGACY_IDS_NAME)
        except OSError:
            pass
        old_failed = self.folder / LEGACY_FAILED_NAME
        try:
            for tok in old_failed.read_text(encoding="utf-8").split():
                if tok.isdigit() and int(tok) not in self.failed:
                    self.failed.append(int(tok))
            moved.append(LEGACY_FAILED_NAME)
        except OSError:
            pass
        if moved:
            self.save()
            console.print(
                f"[dim]Imported {' and '.join(moved)} into {STATUS_NAME}; "
                "you can delete the old text files.[/]"
            )

    @property
    def ids(self) -> set:
        return {int(k) for k in self.downloaded if str(k).isdigit()}

    def mark_done(self, sid: int) -> None:
        self.downloaded[str(sid)] = _stamp()
        self.save()

    def mark_failed(self, ids) -> None:
        self.failed = sorted({int(i) for i in ids})
        self.save()

    def save(self) -> None:
        self.updated = _stamp()
        ordered = sorted((k for k in self.downloaded if str(k).isdigit()), key=int)
        payload = {
            "version": STATUS_VERSION,
            "updated": self.updated,
            "downloaded": {k: self.downloaded[k] for k in ordered},
            "failed": self.failed,
        }
        tmp = self.folder / (STATUS_NAME + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            log(f"[yellow]![/] couldn't write {STATUS_NAME}: {e}")


def parse_statuses(text: str):
    """Return list of statuses to search; ['any'] means no status filter."""
    parts = [p.strip().lower() for p in text.split(",") if p.strip()]
    if not parts or "any" in parts:
        return ["any"]
    bad = [p for p in parts if p not in STATUS_SETS]
    if bad:
        raise ValueError(f"Unknown status: {', '.join(bad)}")
    return parts


def parse_keys(text: str):
    """Return sorted list of key counts, or None for all."""
    t = text.strip().lower()
    if t in ("", "all", "any"):
        return None
    keys = sorted({int(x) for x in re.split(r"[,\s]+", t) if x})
    if any(k < 1 or k > 18 for k in keys):
        raise ValueError("Key counts must be between 1 and 18")
    return keys


def cfg_from_raw(raw: dict) -> dict:
    """Build a run config from saved raw settings (raises on missing/bad values)."""
    sort = raw["sort"] if raw["sort"] in SORTS else SORTS[0]
    return {
        "out": Path(str(raw["out"])),
        "statuses": parse_statuses(as_text(raw["statuses"])),
        "keys": parse_keys(as_text(raw["keys"])),
        "min_sr": float(raw["min_sr"]),
        "max_sr": float(raw["max_sr"]),
        "min_favs": int(raw["min_favs"]),
        "sort": sort,
        "limit": int(raw["limit"]),
        "slide_window": as_bool(raw.get("slide_window", False)),
        "workers": max(1, int(raw["workers"])),
        "batch": max(1, int(raw["batch"])),
    }


def show_summary(cfg: dict) -> None:
    t = Table(title="Saved settings", show_header=False)
    t.add_row("Download folder", str(cfg["out"]))
    t.add_row("Status", ", ".join(cfg["statuses"]))
    t.add_row(
        "Keys",
        "all" if cfg["keys"] is None else ", ".join(f"{k}K" for k in cfg["keys"]),
    )
    t.add_row("Star rating", f"{cfg['min_sr']} - {cfg['max_sr']}")
    t.add_row("Min favourites", str(cfg["min_favs"]))
    t.add_row("Sort", cfg["sort"])
    t.add_row("Max sets", str(cfg["limit"]))
    t.add_row("Sliding window", "yes" if cfg["slide_window"] else "no")
    t.add_row("Parallel / batch", f"{cfg['workers']} / {cfg['batch']}")
    console.print(t)


def ask_config(saved: dict):
    """Prompt for settings (saved values are the defaults). Returns (cfg, raw)."""
    raw: dict = {}

    def d(key, fallback):
        v = as_text(saved.get(key, fallback)).strip()
        return v if v else fallback

    raw["out"] = Prompt.ask(
        "Download folder (.osz saved here, sets already in it are skipped)",
        default=d("out", str(DEFAULT_OUT)),
    )
    while True:
        raw["statuses"] = Prompt.ask(
            "Statuses (graveyard, ranked, loved, qualified, pending, or any; comma-separated)",
            default=d("statuses", "ranked") if saved.get("statuses") else "ranked",
        )
        try:
            parse_statuses(raw["statuses"])
            break
        except ValueError as e:
            console.print(f"[red]{e}[/]")
    while True:
        raw["keys"] = Prompt.ask(
            "Key counts (e.g. 4 or 4,7 or all)", default=d("keys", "all")
        )
        try:
            parse_keys(raw["keys"])
            break
        except ValueError as e:
            console.print(f"[red]{e}[/]")
    raw["min_sr"] = FloatPrompt.ask(
        "Min star rating (matching diff)", default=float(d("min_sr", "0"))
    )
    raw["max_sr"] = FloatPrompt.ask(
        "Max star rating (matching diff)", default=float(d("max_sr", "99"))
    )
    raw["min_favs"] = IntPrompt.ask(
        "Min favourites on set", default=int(d("min_favs", "0"))
    )
    sort_default = d("sort", SORTS[0])
    raw["sort"] = Prompt.ask(
        "Sort by",
        choices=SORTS,
        default=sort_default if sort_default in SORTS else SORTS[0],
    )
    raw["limit"] = IntPrompt.ask("Max sets to fetch", default=int(d("limit", "500")))
    raw["slide_window"] = Confirm.ask(
        "Slide past already-downloaded sets? "
        "(keep paging until it finds that many new ones; no = stop at the first N matches)",
        default=as_bool(saved.get("slide_window", False)),
    )
    raw["workers"] = IntPrompt.ask("Parallel downloads", default=int(d("workers", "4")))
    raw["batch"] = IntPrompt.ask("Batch size", default=int(d("batch", "20")))
    return cfg_from_raw(raw), raw


# ---- osu! API -------------------------------------------------------------
async def get_token(session: aiohttp.ClientSession, cid: str, secret: str) -> str:
    payload = {
        "client_id": int(cid),
        "client_secret": secret,
        "grant_type": "client_credentials",
        "scope": "public",
    }
    async with session.post("https://osu.ppy.sh/oauth/token", json=payload) as r:
        if r.status != 200:
            detail = (await r.text())[:200].strip()
            if r.status in (400, 401):
                # osu! says the credentials themselves are wrong: forget them.
                bad = load_saved()
                if "client_id" in bad or "client_secret" in bad:
                    bad.pop("client_id", None)
                    bad.pop("client_secret", None)
                    save_saved(bad)
                    console.print(
                        "[yellow]Saved credentials removed; you'll be asked again "
                        "next run.[/]"
                    )
                console.print(Panel(GUIDE, title="Auth failed - check your keys"))
            else:
                # 403/429/5xx are osu!'s edge, not your keys: keep them saved.
                console.print(
                    f"[yellow]osu! refused the token request (HTTP {r.status}). "
                    "That's their server, not your keys; saved credentials were "
                    "kept. Try again in a minute.[/]"
                )
            raise SystemExit(f"Auth failed (HTTP {r.status}). {detail}")
        return (await r.json())["access_token"]


def qualifies(s: dict, cfg: dict) -> bool:
    if "any" not in cfg["statuses"]:
        allowed = set().union(*(STATUS_SETS[x] for x in cfg["statuses"]))
        if s.get("status") not in allowed:
            return False
    if s.get("favourite_count", 0) < cfg["min_favs"]:
        return False
    for b in s.get("beatmaps", []):
        if b.get("mode_int") != 3:
            continue
        if cfg["keys"] is not None and int(b.get("cs", 0)) not in cfg["keys"]:
            continue
        if cfg["min_sr"] <= b.get("difficulty_rating", 0) <= cfg["max_sr"]:
            return True
    return False


def new_matches(found: dict, existing: set, slide: bool) -> int:
    """How many of `found` are sets we don't have yet.

    With the sliding window off, the limit counts every match (like before).
    With it on, already-downloaded sets don't count, so paging continues until
    `limit` genuinely new sets are collected (or osu! runs out of results).
    """
    if not slide:
        return len(found)
    return sum(1 for sid in found if sid not in existing)


async def search_one(session, headers, params, cfg, found, status, existing) -> None:
    cursor = None
    while new_matches(found, existing, cfg["slide_window"]) < cfg["limit"]:
        p = dict(params)
        if cursor:
            p["cursor_string"] = cursor
        async with session.get(
            f"{API}/beatmapsets/search", params=p, headers=headers
        ) as r:
            if r.status == 429:
                await asyncio.sleep(int(r.headers.get("Retry-After", 15)))
                continue
            if r.status != 200:
                raise SystemExit(f"Search failed (HTTP {r.status}).")
            data = await r.json()
        for s in data.get("beatmapsets", []):
            if qualifies(s, cfg):
                found[s["id"]] = s
        status.update(
            f"Searching... {new_matches(found, existing, cfg['slide_window'])} "
            "matching sets"
        )
        cursor = data.get("cursor_string")
        if not cursor or not data.get("beatmapsets"):
            break
        await asyncio.sleep(SEARCH_DELAY)


async def search_sets(session, token, cfg, status, existing) -> list:
    headers = {"Authorization": f"Bearer {token}"}
    found: dict = {}
    key_list = cfg["keys"] if cfg["keys"] is not None else [None]
    for st in cfg["statuses"]:
        for k in key_list:
            if new_matches(found, existing, cfg["slide_window"]) >= cfg["limit"]:
                break
            params = {"m": "3", "sort": cfg["sort"]}
            if st != "any":
                params["s"] = st
            if k is not None:
                params["q"] = f"keys={k}"
            await search_one(session, headers, params, cfg, found, status, existing)
    sets = list(found.values())
    if not cfg["slide_window"]:
        sets = sets[: cfg["limit"]]
    return sets


# ---- downloading ----------------------------------------------------------
async def fetch(session, url, part: Path, progress, tid) -> None:
    async with session.get(
        url,
        allow_redirects=True,
        headers={**BROWSER_HEADERS, **mirror_headers(url)},
    ) as r:
        if r.status == 429:
            try:
                wait = int(r.headers.get("Retry-After", 15))
            except ValueError:
                wait = 15
            raise RateLimited(wait)
        if r.status in (401, 403, 404, 451):
            raise MirrorMiss(f"HTTP {r.status}")
        if r.status != 200:
            raise aiohttp.ClientError(f"HTTP {r.status}")
        progress.update(tid, total=r.content_length)
        with open(part, "wb") as f:
            async for chunk in r.content.iter_chunked(65536):
                f.write(chunk)
                stats["bytes"] += len(chunk)
                progress.update(tid, advance=len(chunk))


async def download_set(
    session, sid, title, cfg, progress, overall, otid, sem, failed, status
) -> None:
    dest = cfg["out"] / f"{sid}.osz"
    part = dest.with_suffix(".part")
    async with sem:
        tid = progress.add_task(f"{sid} {title[:38]}", total=None)
        stats["active"] += 1
        try:
            for attempt in range(RETRIES):
                (name, tmpl), wait = choose_mirror(attempt)
                if wait > 0:
                    # Every mirror is cooling down. Touching them again is how
                    # an IP gets banned, so give up on this set for now; the
                    # batch loop stops the run once it sees the flag.
                    globals()["mirrors_exhausted"] = True
                    log("[yellow]…[/] all mirrors rate-limiting; stopping this set")
                    break
                try:
                    await asyncio.wait_for(
                        fetch(session, tmpl.format(id=sid), part, progress, tid),
                        FILE_TIMEOUT,
                    )
                    if not zipfile.is_zipfile(part):
                        raise ValueError("not a valid .osz")
                    os.replace(part, dest)
                    status.mark_done(sid)
                    mstats[name]["ok"] += 1
                    mstats[name]["streak"] = 0
                    mstats[name]["until"] = 0.0
                    stats["ok"] += 1
                    log(f"[green]+[/] {sid} via {name}")
                    return
                except (
                    asyncio.TimeoutError,
                    aiohttp.ClientError,
                    ValueError,
                    OSError,
                    MirrorMiss,
                    RateLimited,
                ) as e:
                    part.unlink(missing_ok=True)
                    progress.update(tid, completed=0, total=None)
                    log(
                        f"[yellow]![/] {sid} {name}: {type(e).__name__} {e} "
                        f"(try {attempt + 1}/{RETRIES})"
                    )
                    if isinstance(e, MirrorMiss):
                        # This mirror just lacks the set; don't hold it against
                        # it, and jump straight to the next one.
                        pass
                    elif isinstance(e, RateLimited):
                        # Park the whole host, not just this mirror entry, and
                        # move on. Sleeping here would stall every set in the
                        # batch for as long as the mirror asks.
                        until = time.time() + e.seconds
                        for other_name, other_tmpl in MIRRORS:
                            if mirror_host(other_tmpl) == mirror_host(tmpl):
                                mstats[other_name]["until"] = until
                        log(
                            f"[yellow]…[/] {mirror_host(tmpl)} cooling down "
                            f"for {e.seconds}s"
                        )
                    else:
                        mstats[name]["streak"] += 1
                        await asyncio.sleep(min(2**attempt + random.random(), 30))
            stats["fail"] += 1
            failed.append(sid)
            log(f"[red]x[/] {sid} gave up")
        finally:
            stats["active"] -= 1
            progress.remove_task(tid)
            overall.update(otid, advance=1)


# ---- main -----------------------------------------------------------------
async def main() -> None:
    console.print(Panel("osu!mania bulk downloader (lazer)", style="cyan"))
    saved = load_saved()
    # Configs written before this option existed default to off, so an existing
    # saved setup keeps loading without a full re-prompt.
    saved.setdefault("slide_window", False)

    cid = os.environ.get("OSU_CLIENT_ID") or saved.get("client_id")
    secret = os.environ.get("OSU_CLIENT_SECRET") or saved.get("client_secret")
    if not (cid and secret):
        console.print(Panel(GUIDE, title="First time? Get API keys"))
        cid = cid or Prompt.ask("osu! client ID")
        secret = secret or getpass.getpass("osu! client secret (hidden): ")
        saved["client_id"], saved["client_secret"] = str(cid), secret
        save_saved(saved)
        console.print(
            f"[green]Credentials saved to {CONFIG_PATH}[/] "
            "(plain text, keep it private / out of git)"
        )
    else:
        console.print("[dim]Using saved credentials.[/]")

    cfg = None
    if all(k in saved for k in SETTING_KEYS):
        try:
            cfg = cfg_from_raw(saved)
            show_summary(cfg)
            if not Confirm.ask("Use these settings?", default=True):
                cfg = None
        except (KeyError, ValueError, TypeError):
            cfg = None
    if cfg is None:
        cfg, raw = ask_config(saved)
        saved.update(raw)
        save_saved(saved)

    cfg["out"].mkdir(parents=True, exist_ok=True)
    for leftover in cfg["out"].glob("*.part"):  # clean interrupted downloads
        leftover.unlink(missing_ok=True)
    global mirrors_exhausted
    mirrors_exhausted = False
    status = Status(cfg["out"]).load()
    if status.failed:
        console.print(
            f"[dim]{len(status.failed)} set(s) failed last run; they'll be retried.[/]"
        )

    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=CONNECT_TIMEOUT,
        sock_connect=CONNECT_TIMEOUT,
        sock_read=SOCK_READ_TIMEOUT,
    )
    headers = {"User-Agent": API_UA}
    conn = aiohttp.TCPConnector(limit=cfg["workers"] * 2)
    async with aiohttp.ClientSession(
        timeout=timeout, headers=headers, connector=conn
    ) as session:
        token = await get_token(session, cid, secret)
        existing = scan_existing(cfg["out"]) | status.ids
        with console.status("Searching...") as st:
            sets = await search_sets(session, token, cfg, st, existing)

        todo = [s for s in sets if s["id"] not in existing]
        console.print(
            f"Found [bold]{len(sets)}[/] matching sets, "
            f"[bold]{len(sets) - len(todo)}[/] already downloaded, "
            f"[bold]{len(todo)}[/] to download."
        )
        if not todo or not Confirm.ask("Start downloading?", default=True):
            return

        progress = Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            transient=True,
        )
        overall = Progress(
            TextColumn("[bold]Overall"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeRemainingColumn(),
        )
        otid = overall.add_task("all", total=len(todo))
        t0 = time.time()

        def render():
            mb = stats["bytes"] / 1e6
            rate = mb / max(time.time() - t0, 1)
            head = (
                f"[green]ok {stats['ok']}[/]  [red]failed {stats['fail']}[/]  "
                f"active {stats['active']}  {mb:,.0f} MB  {rate:.1f} MB/s  "
                f"free disk {free_gb(cfg['out']):.1f} GB"
            )
            return Group(
                Panel(head, title="Stats"),
                overall,
                progress,
                Panel("\n".join(log_lines) or "...", title="Log"),
            )

        sem = asyncio.Semaphore(cfg["workers"])
        failed: list = []
        try:
            with Live(get_renderable=render, refresh_per_second=8, console=console):
                for i in range(0, len(todo), cfg["batch"]):
                    if free_gb(cfg["out"]) < MIN_FREE_GB:
                        log("[red]Low disk space, stopping.[/]")
                        break
                    batch = todo[i : i + cfg["batch"]]
                    log(f"Batch {i // cfg['batch'] + 1}: {len(batch)} sets")
                    await asyncio.gather(
                        *(
                            download_set(
                                session,
                                s["id"],
                                s.get("title", ""),
                                cfg,
                                progress,
                                overall,
                                otid,
                                sem,
                                failed,
                                status,
                            )
                            for s in batch
                        )
                    )
                    await asyncio.sleep(BATCH_PAUSE)
                    if mirrors_exhausted:
                        log(
                            "[red]Every mirror is rate-limiting us; stopping "
                            "instead of hammering them. Re-run later.[/]"
                        )
                        break
        finally:
            for leftover in cfg["out"].glob("*.part"):
                leftover.unlink(missing_ok=True)
            if failed:
                status.mark_failed(failed)

    if mirrors_exhausted:
        console.print(
            "[yellow]Stopped early: the mirrors rate-limited this IP. Nothing was "
            "hammered. Re-run later; finished sets are already recorded.[/]"
        )
    console.print(
        f"\n[bold]Done.[/] {stats['ok']} downloaded, {stats['fail']} failed. "
        f"Files in {cfg['out']}"
    )
    if stats["fail"]:
        console.print(
            f"Failed IDs recorded in {status.path} (they'll be retried next run)"
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Interrupted. Partial files cleaned up; re-run to resume.[/]"
        )
