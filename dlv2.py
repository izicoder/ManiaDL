#!/usr/bin/env python3
"""
osu!mania bulk beatmap downloader - Textual TUI (Windows-friendly).

Left side: credentials, download folder, filters, buttons.
Right side: status panel, overall progress, active downloads, log.

Setup:
    pip install textual aiohttp
    python osu_mania_downloader.py

Everything you enter (API keys, folder, filters) is saved to
mania_dl_config.json next to this script and restored on the next run.
That file contains your API secret in plain text: keep it out of git.
"""

import asyncio
import json
import os
import random
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

import aiohttp
from rich.markup import escape
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
    SelectionList,
    Static,
)

GUIDE = """[b]How to get your osu! API keys[/b]
1. Log in at https://osu.ppy.sh
2. Open https://osu.ppy.sh/home/account/edit
3. Scroll to the OAuth section, click New OAuth Application
4. Name it anything. Callback URL: http://localhost
5. Click Register. Copy the Client ID (a number) and the Client Secret.
   If you lose the secret you can reset it on the same page.
6. Paste both into the boxes on the left. They are saved automatically.
Keep the secret private."""

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
# ---------------------------------------------------------------------------

mstats = {name: {"ok": 0, "streak": 0} for name, _ in MIRRORS}


class MirrorMiss(Exception):
    """Mirror refuses or lacks this set (HTTP 403/404); no point backing off."""


class JobError(Exception):
    """Fatal problem for the current run (auth, search)."""


# ---- helpers --------------------------------------------------------------
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
    except OSError:
        pass


def as_list(value, cast=str) -> list:
    """Accept lists or old comma-separated strings ('all'/'any' = empty)."""
    if isinstance(value, list):
        out = []
        for x in value:
            try:
                out.append(cast(x))
            except (ValueError, TypeError):
                pass
        return out
    if isinstance(value, str):
        out = []
        for x in re.split(r"[,\s]+", value.lower()):
            if x in ("", "all", "any"):
                continue
            try:
                out.append(cast(x))
            except ValueError:
                pass
        return out
    return []


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
    hist = folder / HISTORY_NAME
    try:
        for tok in hist.read_text(encoding="utf-8").split():
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


async def get_token(session, cid: str, secret: str) -> str:
    payload = {
        "client_id": int(cid),
        "client_secret": secret,
        "grant_type": "client_credentials",
        "scope": "public",
    }
    async with session.post("https://osu.ppy.sh/oauth/token", json=payload) as r:
        if r.status != 200:
            raise JobError(f"Auth failed (HTTP {r.status}). Check client ID / secret.")
        return (await r.json())["access_token"]


async def search_one(session, headers, params, cfg, found, on_found) -> None:
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
                raise JobError(f"Search failed (HTTP {r.status}).")
            data = await r.json()
        for s in data.get("beatmapsets", []):
            if qualifies(s, cfg):
                found[s["id"]] = s
        on_found(len(found))
        cursor = data.get("cursor_string")
        if not cursor or not data.get("beatmapsets"):
            break
        await asyncio.sleep(SEARCH_DELAY)


async def search_sets(session, token, cfg, on_found) -> list:
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
            await search_one(session, headers, params, cfg, found, on_found)
    return list(found.values())[: cfg["limit"]]


async def fetch(session, url, part: Path, entry: dict, stats: dict) -> None:
    async with session.get(url, allow_redirects=True) as r:
        if r.status == 429:
            await asyncio.sleep(int(r.headers.get("Retry-After", 10)))
            raise aiohttp.ClientError("rate limited")
        if r.status in (403, 404):
            raise MirrorMiss(f"HTTP {r.status}")
        if r.status != 200:
            raise aiohttp.ClientError(f"HTTP {r.status}")
        entry["total"] = r.content_length
        with open(part, "wb") as f:
            async for chunk in r.content.iter_chunked(65536):
                f.write(chunk)
                entry["done"] += len(chunk)
                stats["bytes"] += len(chunk)


# ---- the app --------------------------------------------------------------
class ManiaDL(App):
    TITLE = "osu!mania downloader"
    BINDINGS = [("ctrl+q", "quit", "Quit")]
    CSS = """
    #main { height: 1fr; }
    #left { width: 50; }
    #filters { height: 1fr; border: round $accent; padding: 0 1; }
    #filters Label { margin-top: 1; text-style: bold; }
    #statuses { height: 7; }
    #keys { height: 12; }
    #buttons { height: auto; }
    #buttons Button { width: 1fr; min-width: 8; }
    #right { width: 1fr; }
    #stats { height: 5; border: round $success; padding: 0 1; }
    #overall { height: auto; padding: 0 1; }
    #active { height: 9; border: round $warning; padding: 0 1; }
    #log { height: 1fr; border: round $primary; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.saved = load_saved()
        self._ready = False
        self.running = False
        self.job = None
        self.active: dict = {}
        self.out_dir = Path(self.saved.get("out", str(DEFAULT_OUT)))
        self.stats = self._fresh_stats()

    @staticmethod
    def _fresh_stats() -> dict:
        return {
            "ok": 0,
            "fail": 0,
            "bytes": 0,
            "done": 0,
            "total": 0,
            "phase": "Idle",
            "t0": None,
        }

    # -- layout --
    def compose(self) -> ComposeResult:
        s = self.saved
        sel_status = as_list(s.get("statuses", ["ranked"]))
        sel_keys = as_list(s.get("keys", []), int)
        sort_val = s.get("sort", SORTS[0])
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="left"):
                with VerticalScroll(id="filters"):
                    yield Label("osu! API client ID")
                    yield Input(
                        value=str(
                            s.get("client_id", os.environ.get("OSU_CLIENT_ID", ""))
                        ),
                        placeholder="number",
                        id="client_id",
                    )
                    yield Label("osu! API client secret")
                    yield Input(
                        value=str(
                            s.get(
                                "client_secret", os.environ.get("OSU_CLIENT_SECRET", "")
                            )
                        ),
                        placeholder="secret",
                        password=True,
                        id="client_secret",
                    )
                    yield Button("How do I get API keys?", id="guide")
                    yield Label(
                        "Download folder (saves .osz here, skips sets already in it)"
                    )
                    yield Input(value=str(s.get("out", DEFAULT_OUT)), id="out")
                    yield Label("Status (none selected = any)")
                    yield SelectionList(
                        *[(name, name, name in sel_status) for name in STATUS_SETS],
                        id="statuses",
                    )
                    yield Label("Key counts (none selected = all)")
                    yield SelectionList(
                        *[(f"{k}K", k, k in sel_keys) for k in range(1, 11)], id="keys"
                    )
                    yield Label("Sort by")
                    yield Select(
                        [(x, x) for x in SORTS],
                        value=sort_val if sort_val in SORTS else SORTS[0],
                        allow_blank=False,
                        id="sort",
                    )
                    yield Label("Min star rating (matching diff)")
                    yield Input(
                        value=str(s.get("min_sr", "0")), type="number", id="min_sr"
                    )
                    yield Label("Max star rating (matching diff)")
                    yield Input(
                        value=str(s.get("max_sr", "99")), type="number", id="max_sr"
                    )
                    yield Label("Min favourites on set")
                    yield Input(
                        value=str(s.get("min_favs", "0")), type="integer", id="min_favs"
                    )
                    yield Label("Max sets to fetch")
                    yield Input(
                        value=str(s.get("limit", "500")), type="integer", id="limit"
                    )
                    yield Label("Parallel downloads")
                    yield Input(
                        value=str(s.get("workers", "4")), type="integer", id="workers"
                    )
                    yield Label("Batch size")
                    yield Input(
                        value=str(s.get("batch", "20")), type="integer", id="batch"
                    )
                with Horizontal(id="buttons"):
                    yield Button("Start", id="start", variant="success")
                    yield Button("Search", id="search", variant="primary")
                    yield Button("Stop", id="stop", variant="error", disabled=True)
                    yield Button("Quit", id="quit")
            with Vertical(id="right"):
                yield Static("", id="stats")
                yield ProgressBar(total=None, show_eta=False, id="overall")
                yield Static("", id="active")
                yield RichLog(id="log", markup=True, wrap=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#filters").border_title = "Filters"
        self.query_one("#stats").border_title = "Status"
        self.query_one("#active").border_title = "Active downloads"
        self.query_one("#log").border_title = "Log"
        self.set_interval(0.25, self.refresh_panels)
        self._ready = True
        self.log_line(
            "Ready. [b]Start[/b] = search + download, [b]Search[/b] = just count matches."
        )
        if not (self.saved.get("client_id") and self.saved.get("client_secret")):
            self.log_line("[yellow]No API keys yet.[/] Press 'How do I get API keys?'")

    # -- logging / panels --
    def log_line(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(
            f"[dim]{time.strftime('%H:%M:%S')}[/] {msg}"
        )

    def refresh_panels(self) -> None:
        st = self.stats
        elapsed = (time.time() - st["t0"]) if st["t0"] else 0
        mb = st["bytes"] / 1e6
        rate = mb / elapsed if elapsed > 1 else 0.0
        free = free_gb(self.out_dir)
        self.query_one("#stats", Static).update(
            f"[b]{st['phase']}[/b]\n"
            f"[green]ok {st['ok']}[/]  [red]failed {st['fail']}[/]  "
            f"active {len(self.active)}  done {st['done']}/{st['total']}\n"
            f"{mb:,.0f} MB  {rate:.1f} MB/s  free disk {free:.1f} GB"
        )
        text = Text()
        for sid, e in list(self.active.items()):
            if e["total"]:
                frac = min(e["done"] / e["total"], 1.0)
                fill = int(frac * 16)
                bar = "#" * fill + "-" * (16 - fill)
                info = f"{frac * 100:3.0f}%  {e['done'] / 1e6:.1f}/{e['total'] / 1e6:.1f} MB"
            else:
                bar = "." * 16
                info = f"{e['done'] / 1e6:.1f} MB"
            text.append(f"{sid:>8} {e['title'][:22]:<22} [{bar}] {info}\n")
        self.query_one("#active", Static).update(text)

    # -- settings --
    def _val(self, wid: str) -> str:
        return self.query_one(f"#{wid}", Input).value.strip()

    def save_settings(self) -> None:
        if not self._ready:
            return
        sort_v = self.query_one("#sort", Select).value
        data = {
            "client_id": self._val("client_id"),
            "client_secret": self.query_one("#client_secret", Input).value.strip(),
            "out": self._val("out"),
            "statuses": list(self.query_one("#statuses", SelectionList).selected),
            "keys": list(self.query_one("#keys", SelectionList).selected),
            "sort": sort_v if isinstance(sort_v, str) else SORTS[0],
        }
        for wid in ("min_sr", "max_sr", "min_favs", "limit", "workers", "batch"):
            data[wid] = self._val(wid)
        self.saved.update(data)
        save_saved(self.saved)

    def read_cfg(self) -> dict:
        out = self._val("out")
        if not out:
            raise ValueError("Download folder is required.")
        sort_v = self.query_one("#sort", Select).value
        keys = sorted(self.query_one("#keys", SelectionList).selected)
        cfg = {
            "out": Path(out),
            "statuses": list(self.query_one("#statuses", SelectionList).selected)
            or ["any"],
            "keys": keys or None,
            "sort": sort_v if isinstance(sort_v, str) else SORTS[0],
            "min_sr": float(self._val("min_sr") or 0),
            "max_sr": float(self._val("max_sr") or 99),
            "min_favs": int(self._val("min_favs") or 0),
            "limit": max(1, int(self._val("limit") or 500)),
            "workers": max(1, int(self._val("workers") or 4)),
            "batch": max(1, int(self._val("batch") or 20)),
        }
        return cfg

    @on(Input.Changed)
    def _input_changed(self, event: Input.Changed) -> None:
        self.save_settings()

    @on(SelectionList.SelectedChanged)
    def _list_changed(self, event: SelectionList.SelectedChanged) -> None:
        self.save_settings()

    @on(Select.Changed)
    def _select_changed(self, event: Select.Changed) -> None:
        self.save_settings()

    # -- buttons --
    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "guide":
            for line in GUIDE.splitlines():
                self.log_line(line)
        elif bid in ("start", "search"):
            if self.running:
                self.notify("A job is already running.", severity="warning")
                return
            self.job = self.run_worker(
                self.run_job(download=(bid == "start")), exclusive=True, group="job"
            )
        elif bid == "stop":
            if self.job is not None:
                self.job.cancel()
        elif bid == "quit":
            self.save_settings()
            self.exit()

    def set_busy(self, busy: bool) -> None:
        self.query_one("#start", Button).disabled = busy
        self.query_one("#search", Button).disabled = busy
        self.query_one("#stop", Button).disabled = not busy

    # -- the job --
    async def run_job(self, download: bool) -> None:
        try:
            cfg = self.read_cfg()
        except ValueError as e:
            self.notify(f"Bad input: {e}", severity="error")
            return
        cid = self._val("client_id")
        secret = self.query_one("#client_secret", Input).value.strip()
        if not cid or not secret:
            self.notify("Enter your API client ID and secret first.", severity="error")
            for line in GUIDE.splitlines():
                self.log_line(line)
            return
        if not cid.isdigit():
            self.notify("Client ID must be a number.", severity="error")
            return

        self.save_settings()
        self.running = True
        self.set_busy(True)
        self.out_dir = cfg["out"]
        self.stats = self._fresh_stats()
        self.stats["t0"] = time.time()
        self.active.clear()
        bar = self.query_one("#overall", ProgressBar)
        bar.update(total=None, progress=0)
        try:
            cfg["out"].mkdir(parents=True, exist_ok=True)
            for leftover in cfg["out"].glob("*.part"):
                leftover.unlink(missing_ok=True)

            timeout = aiohttp.ClientTimeout(
                total=None,
                connect=CONNECT_TIMEOUT,
                sock_connect=CONNECT_TIMEOUT,
                sock_read=SOCK_READ_TIMEOUT,
            )
            conn = aiohttp.TCPConnector(limit=cfg["workers"] * 2)
            async with aiohttp.ClientSession(
                timeout=timeout,
                connector=conn,
                headers={"User-Agent": "osu-mania-downloader/2.0"},
            ) as session:
                self.stats["phase"] = "Authenticating..."
                token = await get_token(session, cid, secret)

                self.stats["phase"] = "Searching..."

                def on_found(n: int) -> None:
                    self.stats["phase"] = f"Searching... {n} matching sets"

                sets = await search_sets(session, token, cfg, on_found)
                existing = await asyncio.to_thread(scan_existing, cfg["out"])
                todo = [s for s in sets if s["id"] not in existing]
                self.log_line(
                    f"Found [b]{len(sets)}[/] matching sets, "
                    f"[b]{len(sets) - len(todo)}[/] already downloaded, "
                    f"[b]{len(todo)}[/] to download."
                )
                if not download or not todo:
                    self.stats["phase"] = (
                        "Idle (search only)" if not download else "Idle"
                    )
                    return
                await self.download_all(session, cfg, todo, bar)
        except asyncio.CancelledError:
            self.log_line(
                "[yellow]Stopped. Partial files cleaned up; start again to resume.[/]"
            )
            raise
        except (JobError, aiohttp.ClientError, OSError) as e:
            self.log_line(f"[red]Error:[/] {escape(str(e))}")
            self.notify(str(e), severity="error")
        finally:
            for leftover in cfg["out"].glob("*.part"):
                leftover.unlink(missing_ok=True)
            self.active.clear()
            self.running = False
            self.set_busy(False)
            if self.stats["phase"] not in ("Idle", "Idle (search only)"):
                self.stats["phase"] = "Idle"

    async def download_all(
        self, session, cfg: dict, todo: list, bar: ProgressBar
    ) -> None:
        self.stats["total"] = len(todo)
        bar.update(total=len(todo), progress=0)
        sem = asyncio.Semaphore(cfg["workers"])
        failed: list = []
        n_batches = (len(todo) + cfg["batch"] - 1) // cfg["batch"]
        try:
            for i in range(0, len(todo), cfg["batch"]):
                if free_gb(cfg["out"]) < MIN_FREE_GB:
                    self.log_line("[red]Low disk space, stopping.[/]")
                    break
                batch = todo[i : i + cfg["batch"]]
                self.stats["phase"] = (
                    f"Downloading batch {i // cfg['batch'] + 1}/{n_batches}"
                )
                await asyncio.gather(
                    *(
                        self.download_set(
                            session, s["id"], s.get("title", ""), cfg, sem, failed, bar
                        )
                        for s in batch
                    )
                )
                await asyncio.sleep(BATCH_PAUSE)
            self.stats["phase"] = "Done"
            self.log_line(
                f"[b]Done.[/] {self.stats['ok']} downloaded, "
                f"{self.stats['fail']} failed. Files in {cfg['out']}"
            )
        finally:
            if failed:
                (cfg["out"] / "failed.txt").write_text("\n".join(map(str, failed)))
                self.log_line(f"Failed IDs saved to {cfg['out'] / 'failed.txt'}")

    async def download_set(self, session, sid, title, cfg, sem, failed, bar) -> None:
        dest = cfg["out"] / f"{sid}.osz"
        part = dest.with_suffix(".part")
        async with sem:
            entry = {"title": title, "done": 0, "total": None}
            self.active[sid] = entry
            try:
                for attempt in range(RETRIES):
                    # best mirror first: fewest consecutive failures, then most successes
                    ranked = sorted(
                        MIRRORS,
                        key=lambda m: (mstats[m[0]]["streak"], -mstats[m[0]]["ok"]),
                    )
                    name, tmpl = ranked[attempt % len(ranked)]
                    entry["done"], entry["total"] = 0, None
                    try:
                        await asyncio.wait_for(
                            fetch(
                                session, tmpl.format(id=sid), part, entry, self.stats
                            ),
                            FILE_TIMEOUT,
                        )
                        if not zipfile.is_zipfile(part):
                            raise ValueError("not a valid .osz")
                        os.replace(part, dest)
                        record_downloaded(cfg["out"], sid)
                        mstats[name]["ok"] += 1
                        mstats[name]["streak"] = 0
                        self.stats["ok"] += 1
                        self.log_line(f"[green]+[/] {sid} via {name}")
                        return
                    except (
                        asyncio.TimeoutError,
                        aiohttp.ClientError,
                        ValueError,
                        OSError,
                        MirrorMiss,
                    ) as e:
                        part.unlink(missing_ok=True)
                        mstats[name]["streak"] += 1
                        self.log_line(
                            f"[yellow]![/] {sid} {name}: {type(e).__name__} "
                            f"{escape(str(e))} (try {attempt + 1}/{RETRIES})"
                        )
                        if not isinstance(
                            e, MirrorMiss
                        ):  # back off only on transient errors
                            await asyncio.sleep(min(2**attempt + random.random(), 30))
                self.stats["fail"] += 1
                failed.append(sid)
                self.log_line(f"[red]x[/] {sid} gave up")
            finally:
                self.active.pop(sid, None)
                self.stats["done"] += 1
                bar.advance(1)


if __name__ == "__main__":
    ManiaDL().run()
