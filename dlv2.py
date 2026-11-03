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
MIRRORS = [
    ("nerinyan", "https://api.nerinyan.moe/d/{id}?noVideo=true"),
    ("catboy", "https://catboy.best/d/{id}n"),
    ("osu.direct", "https://osu.direct/api/d/{id}"),
]
RETRIES = 4  # attempts per set
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
# IDs of everything this tool downloaded, kept in the download folder so a set is
# still skipped after you delete its .osz (osu!lazer keeps maps in its own database).
HISTORY_NAME = "downloaded_ids.txt"

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
    "workers",
    "batch",
]
# ---------------------------------------------------------------------------

console = Console()
log_lines: deque = deque(maxlen=10)
stats = {"ok": 0, "fail": 0, "active": 0, "bytes": 0}
mstats = {name: {"ok": 0, "streak": 0} for name, _ in MIRRORS}


class MirrorMiss(Exception):
    """Mirror refuses or lacks this set (HTTP 403/404); no point backing off."""


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


# ---- helpers --------------------------------------------------------------
def free_gb(path: Path) -> float:
    p = path
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free / 1e9


def scan_existing(folder: Path) -> set:
    """IDs already downloaded: '123.osz' / '123 Artist - Title.osz' files + history file."""
    ids = set()
    if not folder.exists():
        return ids
    for p in folder.iterdir():
        m = re.match(r"(\d+)(?:[ .]|$)", p.name)
        if m and p.suffix.lower() == ".osz":
            ids.add(int(m.group(1)))
    try:
        for tok in (folder / HISTORY_NAME).read_text(encoding="utf-8").split():
            if tok.isdigit():
                ids.add(int(tok))
    except OSError:
        pass
    return ids


def record_downloaded(folder: Path, sid: int) -> None:
    try:
        with open(folder / HISTORY_NAME, "a", encoding="utf-8") as f:
            f.write(f"{sid}\n")
    except OSError:
        pass


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
            bad = load_saved()
            if bad.pop("client_id", None) or bad.pop("client_secret", None):
                save_saved(bad)
                console.print(
                    "[yellow]Saved credentials removed; you'll be asked again next run.[/]"
                )
            console.print(Panel(GUIDE, title="Auth failed - check your keys"))
            raise SystemExit(f"Auth failed (HTTP {r.status}).")
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


async def search_one(session, headers, params, cfg, found, status) -> None:
    cursor = None
    while len(found) < cfg["limit"]:
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
        status.update(f"Searching... {len(found)} matching sets")
        cursor = data.get("cursor_string")
        if not cursor or not data.get("beatmapsets"):
            break
        await asyncio.sleep(SEARCH_DELAY)


async def search_sets(session, token, cfg, status) -> list:
    headers = {"Authorization": f"Bearer {token}"}
    found: dict = {}
    key_list = cfg["keys"] if cfg["keys"] is not None else [None]
    for st in cfg["statuses"]:
        for k in key_list:
            if len(found) >= cfg["limit"]:
                break
            params = {"m": "3", "sort": cfg["sort"]}
            if st != "any":
                params["s"] = st
            if k is not None:
                params["q"] = f"keys={k}"
            await search_one(session, headers, params, cfg, found, status)
    return list(found.values())[: cfg["limit"]]


# ---- downloading ----------------------------------------------------------
async def fetch(session, url, part: Path, progress, tid) -> None:
    async with session.get(url, allow_redirects=True) as r:
        if r.status == 429:
            await asyncio.sleep(int(r.headers.get("Retry-After", 10)))
            raise aiohttp.ClientError("rate limited")
        if r.status in (403, 404):
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
    session, sid, title, cfg, progress, overall, otid, sem, failed
) -> None:
    dest = cfg["out"] / f"{sid}.osz"
    part = dest.with_suffix(".part")
    async with sem:
        tid = progress.add_task(f"{sid} {title[:38]}", total=None)
        stats["active"] += 1
        try:
            for attempt in range(RETRIES):
                # best mirror first: fewest consecutive failures, then most successes
                ranked = sorted(
                    MIRRORS, key=lambda m: (mstats[m[0]]["streak"], -mstats[m[0]]["ok"])
                )
                name, tmpl = ranked[attempt % len(ranked)]
                try:
                    await asyncio.wait_for(
                        fetch(session, tmpl.format(id=sid), part, progress, tid),
                        FILE_TIMEOUT,
                    )
                    if not zipfile.is_zipfile(part):
                        raise ValueError("not a valid .osz")
                    os.replace(part, dest)
                    record_downloaded(cfg["out"], sid)
                    mstats[name]["ok"] += 1
                    mstats[name]["streak"] = 0
                    stats["ok"] += 1
                    log(f"[green]+[/] {sid} via {name}")
                    return
                except (
                    asyncio.TimeoutError,
                    aiohttp.ClientError,
                    ValueError,
                    OSError,
                    MirrorMiss,
                ) as e:
                    part.unlink(missing_ok=True)
                    progress.update(tid, completed=0, total=None)
                    mstats[name]["streak"] += 1
                    log(
                        f"[yellow]![/] {sid} {name}: {type(e).__name__} {e} "
                        f"(try {attempt + 1}/{RETRIES})"
                    )
                    if not isinstance(
                        e, MirrorMiss
                    ):  # back off only on transient errors
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

    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=CONNECT_TIMEOUT,
        sock_connect=CONNECT_TIMEOUT,
        sock_read=SOCK_READ_TIMEOUT,
    )
    headers = {"User-Agent": "osu-mania-downloader/1.0"}
    conn = aiohttp.TCPConnector(limit=cfg["workers"] * 2)
    async with aiohttp.ClientSession(
        timeout=timeout, headers=headers, connector=conn
    ) as session:
        token = await get_token(session, cid, secret)
        with console.status("Searching...") as st:
            sets = await search_sets(session, token, cfg, st)

        existing = scan_existing(cfg["out"])
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
                            )
                            for s in batch
                        )
                    )
                    await asyncio.sleep(BATCH_PAUSE)
        finally:
            for leftover in cfg["out"].glob("*.part"):
                leftover.unlink(missing_ok=True)
            if failed:
                (cfg["out"] / "failed.txt").write_text("\n".join(map(str, failed)))

    console.print(
        f"\n[bold]Done.[/] {stats['ok']} downloaded, {stats['fail']} failed. "
        f"Files in {cfg['out']}"
    )
    if stats["fail"]:
        console.print(f"Failed IDs saved to {cfg['out'] / 'failed.txt'}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Interrupted. Partial files cleaned up; re-run to resume.[/]"
        )
