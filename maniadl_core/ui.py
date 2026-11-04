"""Interactive prompts and the rich live dashboard."""

from __future__ import annotations

import time

from rich import box
from rich.console import Group
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
from rich.text import Text

from . import config, runtime, util
from .constants import (
    ADVANCED_KEYS,
    MAX_BPM,
    MAX_LENGTH,
    MAX_NOTES,
    MIRRORS,
    NEW_DEFAULTS,
    SORTS,
)


def _default(saved: dict, key: str, fallback: str) -> str:
    value = util.as_text(saved.get(key, fallback)).strip()
    return value if value else fallback


def _float_default(saved: dict, key: str, fallback: float) -> float:
    try:
        return float(saved.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def _int_default(saved: dict, key: str, fallback: int) -> int:
    try:
        return int(saved.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def _ask_range(prompt: str, default: str, cast, name: str) -> str:
    while True:
        text = Prompt.ask(prompt, default=default, console=runtime.console)
        try:
            util.parse_range(text, cast, name)
            return text
        except ValueError as exc:
            runtime.console.print(f"[red]{exc}[/]")


def _ask_date_range(prompt: str, default: str, name: str) -> str:
    while True:
        text = Prompt.ask(prompt, default=default, console=runtime.console)
        try:
            util.parse_date_range(text, name)
            return text
        except ValueError as exc:
            runtime.console.print(f"[red]{exc}[/]")


def print_banner() -> None:
    title = Text("ManiaDL", style="bold cyan")
    subtitle = Text(
        "bulk osu!mania beatmap downloader for osu!lazer", style="dim"
    )
    runtime.console.print(
        Panel(
            Group(title, subtitle),
            border_style="cyan",
            padding=(0, 2),
        )
    )
    runtime.console.print(
        Panel(
            "[bold]Anti-ban notice[/]\n"
            "Only the public osu! API and community mirrors are used. Strict "
            "mode spaces requests per host, caps concurrency and stops when "
            "mirrors ask you to slow down.\n"
            "Bulk downloading can still violate a mirror's terms. Keep workers "
            "modest, leave strict mode on, and stop if you see repeated 429s.",
            border_style="yellow",
            title="Please read",
        )
    )


def ask_config(saved: dict) -> tuple[dict, dict]:
    raw: dict = {}

    runtime.console.print("[bold cyan]Download settings[/]")
    raw["out"] = Prompt.ask(
        "Download folder (.osz saved here, sets already in it are skipped)",
        default=_default(saved, "out", str(config.DEFAULT_OUT)),
        console=runtime.console,
    )

    while True:
        raw["statuses"] = Prompt.ask(
            "Statuses (graveyard, ranked, loved, qualified, pending, or any; "
            "comma-separated)",
            default=_default(saved, "statuses", "ranked"),
            console=runtime.console,
        )
        try:
            util.parse_statuses(raw["statuses"])
            break
        except ValueError as exc:
            runtime.console.print(f"[red]{exc}[/]")

    while True:
        raw["keys"] = Prompt.ask(
            "Key counts (e.g. 4 or 4,7 or all)",
            default=_default(saved, "keys", "all"),
            console=runtime.console,
        )
        try:
            util.parse_keys(raw["keys"])
            break
        except ValueError as exc:
            runtime.console.print(f"[red]{exc}[/]")

    raw["min_sr"] = FloatPrompt.ask(
        "Min star rating (matching diff)",
        default=_float_default(saved, "min_sr", 0.0),
        console=runtime.console,
    )
    raw["max_sr"] = FloatPrompt.ask(
        "Max star rating (matching diff)",
        default=_float_default(saved, "max_sr", 99.0),
        console=runtime.console,
    )
    raw["min_favs"] = IntPrompt.ask(
        "Min favourites on set",
        default=_int_default(saved, "min_favs", 0),
        console=runtime.console,
    )
    sort_default = _default(saved, "sort", SORTS[0])
    raw["sort"] = Prompt.ask(
        "Sort by",
        choices=SORTS,
        default=sort_default if sort_default in SORTS else SORTS[0],
        console=runtime.console,
    )
    raw["limit"] = IntPrompt.ask(
        "Max sets to fetch",
        default=_int_default(saved, "limit", 500),
        console=runtime.console,
    )
    raw["slide_window"] = Confirm.ask(
        "Slide past already-downloaded sets? "
        "(keep paging until it finds that many new ones; no = stop at the first "
        "N matches)",
        default=util.as_bool(saved.get("slide_window", False)),
        console=runtime.console,
    )
    raw["workers"] = IntPrompt.ask(
        "Parallel downloads",
        default=_int_default(saved, "workers", 4),
        console=runtime.console,
    )
    raw["batch"] = IntPrompt.ask(
        "Batch size",
        default=_int_default(saved, "batch", 20),
        console=runtime.console,
    )
    raw["safe_mode"] = Confirm.ask(
        "Strict anti-ban mode? (per-host spacing, capped concurrency, "
        "jittered retries)",
        default=util.as_bool(saved.get("safe_mode", True)),
        console=runtime.console,
    )

    advanced_default = util.as_bool(saved.get("advanced", False)) or any(
        str(saved.get(key) or "").strip()
        for key in ADVANCED_KEYS
        if key not in ("include_nsfw", "min_plays")
    ) or _int_default(saved, "min_plays", 0) > 0 or util.as_bool(
        saved.get("include_nsfw", False)
    )

    raw["advanced"] = Confirm.ask(
        "Configure advanced filters? (title/artist/mapper, BPM, length, notes, "
        "genre, language, ranked dates)",
        default=advanced_default,
        console=runtime.console,
    )

    if raw["advanced"]:
        raw["query"] = Prompt.ask(
            "osu! search query / free text "
            "(supports stars>=5, keys=4, title=..., ranked>=2020)",
            default=_default(saved, "query", ""),
            console=runtime.console,
        )
        raw["title"] = Prompt.ask(
            "Title contains", default=_default(saved, "title", ""),
            console=runtime.console,
        )
        raw["artist"] = Prompt.ask(
            "Artist contains", default=_default(saved, "artist", ""),
            console=runtime.console,
        )
        raw["creator"] = Prompt.ask(
            "Mapper/creator contains", default=_default(saved, "creator", ""),
            console=runtime.console,
        )
        raw["source"] = Prompt.ask(
            "Source contains", default=_default(saved, "source", ""),
            console=runtime.console,
        )
        raw["exclude"] = Prompt.ask(
            "Exclude terms (comma-separated, matched anywhere in metadata)",
            default=_default(saved, "exclude", ""),
            console=runtime.console,
        )
        raw["genre"] = Prompt.ask(
            "Genres (comma-separated, partial ok, blank=any)",
            default=_default(saved, "genre", ""),
            console=runtime.console,
        )
        raw["language"] = Prompt.ask(
            "Languages (comma-separated, partial ok, blank=any)",
            default=_default(saved, "language", ""),
            console=runtime.console,
        )
        raw["bpm_range"] = _ask_range(
            "BPM range (e.g. 150-220, blank=any)",
            _default(saved, "bpm_range", ""),
            float,
            "BPM",
        )
        raw["length_range"] = _ask_range(
            "Length range in seconds (e.g. 60-300, blank=any)",
            _default(saved, "length_range", ""),
            int,
            "length",
        )
        raw["notes_range"] = _ask_range(
            "Note count range (e.g. 1000-5000, blank=any)",
            _default(saved, "notes_range", ""),
            int,
            "note count",
        )
        raw["min_plays"] = IntPrompt.ask(
            "Min play count",
            default=_int_default(saved, "min_plays", 0),
            console=runtime.console,
        )
        raw["ranked_range"] = _ask_date_range(
            "Ranked date range (e.g. 2020-01-01..2024-12-31, blank=any)",
            _default(saved, "ranked_range", ""),
            "ranked date",
        )
        raw["include_nsfw"] = Confirm.ask(
            "Include NSFW sets?",
            default=util.as_bool(saved.get("include_nsfw", False)),
            console=runtime.console,
        )
    else:
        # Preserve old advanced values so toggling it back on is non-destructive.
        for key in ADVANCED_KEYS:
            raw[key] = saved.get(key, NEW_DEFAULTS[key])

    return config.cfg_from_raw(raw), raw


def _range_label(low, high, low_default, high_default, unit: str = "") -> str:
    if low <= low_default and high >= high_default:
        return "any"
    if low > low_default and high < high_default:
        return f"{low:g}-{high:g}{unit}"
    if low > low_default:
        return f">={low:g}{unit}"
    return f"<={high:g}{unit}"


def _date_label(after: str, before: str) -> str:
    if after and before:
        return f"{after}..{before}"
    if after:
        return f">={after}"
    if before:
        return f"<={before}"
    return "any"


def show_summary(cfg: dict) -> None:
    basic = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    basic.add_column(style="bold cyan", no_wrap=True)
    basic.add_column()
    basic.add_row("Download folder", str(cfg["out"]))
    basic.add_row("Status", ", ".join(cfg["statuses"]))
    basic.add_row(
        "Keys",
        "all"
        if cfg["keys"] is None
        else ", ".join(f"{key}K" for key in cfg["keys"]),
    )
    basic.add_row("Star rating", f"{cfg['min_sr']:g} - {cfg['max_sr']:g}")
    basic.add_row("Min favourites", str(cfg["min_favs"]))
    basic.add_row("Sort", cfg["sort"])
    basic.add_row("Max sets", str(cfg["limit"]))
    basic.add_row("Sliding window", "yes" if cfg["slide_window"] else "no")
    basic.add_row("Parallel / batch", f"{cfg['workers']} / {cfg['batch']}")
    basic.add_row(
        "Anti-ban mode", "strict" if cfg["safe_mode"] else "balanced"
    )

    group = [basic]
    if cfg["advanced"]:
        advanced = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        advanced.add_column(style="bold cyan", no_wrap=True)
        advanced.add_column()
        advanced.add_row("Query", cfg["query"] or "-")
        advanced.add_row("Title contains", cfg["title"] or "-")
        advanced.add_row("Artist contains", cfg["artist"] or "-")
        advanced.add_row("Creator contains", cfg["creator"] or "-")
        advanced.add_row("Source contains", cfg["source"] or "-")
        advanced.add_row(
            "Exclude", ", ".join(cfg["exclude"]) if cfg["exclude"] else "-"
        )
        advanced.add_row(
            "Genre", ", ".join(cfg["genre"]) if cfg["genre"] else "any"
        )
        advanced.add_row(
            "Language", ", ".join(cfg["language"]) if cfg["language"] else "any"
        )
        advanced.add_row(
            "BPM",
            _range_label(cfg["min_bpm"], cfg["max_bpm"], 0.0, MAX_BPM),
        )
        advanced.add_row(
            "Length",
            _range_label(
                cfg["min_length"], cfg["max_length"], 0, MAX_LENGTH, "s"
            ),
        )
        advanced.add_row(
            "Notes",
            _range_label(cfg["min_notes"], cfg["max_notes"], 0, MAX_NOTES),
        )
        advanced.add_row("Min plays", str(cfg["min_plays"]))
        advanced.add_row(
            "Ranked", _date_label(cfg["ranked_after"], cfg["ranked_before"])
        )
        advanced.add_row(
            "NSFW", "include" if cfg["include_nsfw"] else "exclude"
        )
        group.append(advanced)

    runtime.console.print(
        Panel(Group(*group), title="[bold]Settings[/]", border_style="blue")
    )


def show_risk_report(cfg: dict) -> bool:
    items = config.risk_items(cfg)
    if not items:
        runtime.console.print(
            Panel(
                "[green]No risky settings detected.[/]",
                title="Safety check",
                border_style="green",
            )
        )
        return False

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Level", no_wrap=True)
    table.add_column("Warning")
    colors = {"high": "red", "medium": "yellow", "low": "cyan"}
    for level, message in items:
        table.add_row(f"[{colors[level]}]{level.upper()}[/]", message)

    high = any(level == "high" for level, _ in items)
    runtime.console.print(
        Panel(
            table,
            title="Safety check",
            border_style="red" if high else "yellow",
        )
    )
    runtime.console.print(
        "[bold]Mirrors are community-run. Keep strict mode on and stop if you "
        "see repeated 429s.[/]"
    )
    return high


def show_search_summary(sets: list, todo: list, existing: set, cfg: dict) -> None:
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()
    table.add_row("Matching sets", str(len(sets)))
    table.add_row("Already downloaded", str(len(sets) - len(todo)))
    table.add_row("To download", f"[bold green]{len(todo)}[/]")
    table.add_row("Status", ", ".join(cfg["statuses"]))
    table.add_row(
        "Keys",
        "all"
        if cfg["keys"] is None
        else ", ".join(f"{key}K" for key in cfg["keys"]),
    )
    if cfg["advanced"] and cfg["query"]:
        table.add_row("Query", cfg["query"])
    runtime.console.print(
        Panel(table, title="Search results", border_style="cyan")
    )


def stats_panel(cfg: dict, started: float) -> Panel:
    elapsed = max(time.time() - started, 1.0)
    megabytes = runtime.stats["bytes"] / 1e6
    rate = megabytes / elapsed
    grid = Table.grid(expand=True, padding=(0, 2))
    for _ in range(6):
        grid.add_column()
    grid.add_row(
        f"[bold green]OK[/] {runtime.stats['ok']}",
        f"[bold red]FAIL[/] {runtime.stats['fail']}",
        f"[bold cyan]ACTIVE[/] {runtime.stats['active']}",
        f"[bold]{megabytes:,.1f} MB[/]",
        f"[bold]{rate:.2f} MB/s[/]",
        f"[bold]FREE[/] {util.free_gb(cfg['out']):.1f} GB",
    )
    return Panel(grid, title="Stats", border_style="green")


def mirror_table() -> Table:
    table = Table(
        title="Mirror health",
        box=box.SIMPLE,
        header_style="bold",
        expand=True,
    )
    table.add_column("Mirror", style="cyan", no_wrap=True)
    table.add_column("State")
    table.add_column("OK", justify="right")
    table.add_column("Fail", justify="right")
    table.add_column("Streak", justify="right")
    now = time.time()
    for name, _ in MIRRORS:
        entry = runtime.mstats[name]
        if entry["until"] > now:
            state = f"[yellow]cool {entry['until'] - now:.0f}s[/]"
        elif entry["streak"] >= 2:
            state = "[yellow]shaky[/]"
        else:
            state = "[green]ready[/]"
        table.add_row(
            name,
            state,
            str(entry["ok"]),
            str(entry["fail"]),
            str(entry["streak"]),
        )
    return table


def log_panel() -> Panel:
    body = "\n".join(runtime.log_lines) or "[dim]Waiting for events...[/]"
    return Panel(body, title="Log", border_style="dim")


def render_dashboard(cfg: dict, started: float, overall, progress) -> Group:
    return Group(
        stats_panel(cfg, started),
        overall,
        progress,
        mirror_table(),
        log_panel(),
    )


def make_progress() -> tuple[Progress, Progress]:
    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        transient=True,
        console=runtime.console,
    )
    overall = Progress(
        TextColumn("[bold]Overall"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=runtime.console,
    )
    return progress, overall
