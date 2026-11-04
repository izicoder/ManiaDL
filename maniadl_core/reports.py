"""Failed-download reports with direct mirror links."""

from __future__ import annotations

import time
from pathlib import Path

from rich import box
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from . import runtime, util
from .constants import FAILED_LINKS_NAME


def _title_map(titles: dict) -> dict[int, str]:
    mapped: dict[int, str] = {}
    for key, value in (titles or {}).items():
        try:
            mapped[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    return mapped


def write_failed_links(folder: Path, failed_ids, titles: dict) -> Path | None:
    ids = sorted({int(item) for item in failed_ids})
    path = folder / FAILED_LINKS_NAME
    if not ids:
        path.unlink(missing_ok=True)
        return None

    title_map = _title_map(titles)
    lines = [
        "ManiaDL failed downloads",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Count: {len(ids)}",
        "",
        "Official pages and community mirrors. Try them in this order.",
        "",
    ]
    for sid in ids:
        title = title_map.get(sid) or "unknown title"
        lines.append(f"[{sid}] {title}")
        for name, url in util.direct_links(sid):
            lines.append(f"  {name:<12} {url}")
        lines.append("")

    try:
        util.atomic_write_text(path, "\n".join(lines))
    except OSError as exc:
        runtime.console.print(f"[yellow]Couldn't write {path.name}: {exc}[/]")
        return None
    return path


def print_failed_links(folder: Path, failed_ids, titles: dict) -> None:
    ids = sorted({int(item) for item in failed_ids})
    path = write_failed_links(folder, ids, titles)
    if not ids:
        runtime.console.print("[green]No failed downloads.[/]")
        return

    title_map = _title_map(titles)
    table = Table(
        title=f"Failed downloads ({len(ids)})",
        box=box.SIMPLE,
        header_style="bold",
        expand=True,
    )
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", overflow="fold")
    table.add_column("Official", no_wrap=True)
    table.add_column("Mirrors", overflow="fold")

    for sid in ids:
        title = title_map.get(sid) or "unknown"
        if len(title) > 60:
            title = title[:57] + "..."
        title = escape(title)
        official = f"[link=https://osu.ppy.sh/beatmapsets/{sid}]osu![/link]"
        mirror_links = " · ".join(
            f"[link={url}]{name}[/link]"
            for name, url in util.direct_links(sid)
            if name != "osu!"
        )
        table.add_row(str(sid), title, official, mirror_links)

    runtime.console.print(
        Panel(table, border_style="red", title="Manual download links")
    )
    if path is not None:
        runtime.console.print(f"[dim]Full list saved to {path}[/]")
