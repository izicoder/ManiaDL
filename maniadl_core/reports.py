"""Failed-download data for the GUI.

Earlier builds wrote ``failed_links.txt`` into the download folder. The spec
for the GUI build is one ``status.json`` per folder, so failed sets are shown
in the right-hand panel instead of on disk.
"""

from __future__ import annotations

from . import util


def _title_map(titles: dict) -> dict[int, str]:
    mapped: dict[int, str] = {}
    for key, value in (titles or {}).items():
        try:
            mapped[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    return mapped


def failed_entries(failed_ids, titles: dict) -> list[dict]:
    """Rows for the failed tab: id, title and every direct download link."""
    ids = sorted({int(item) for item in failed_ids})
    title_map = _title_map(titles)
    return [
        {
            "id": sid,
            "title": title_map.get(sid) or "unknown title",
            "links": util.direct_links(sid),
        }
        for sid in ids
    ]


def links_text(entries: list[dict]) -> str:
    """Plain-text block for the clipboard."""
    lines = ["ManiaDL failed downloads", ""]
    for entry in entries:
        lines.append(f"[{entry['id']}] {entry['title']}")
        for name, url in entry["links"]:
            lines.append(f"  {name:<12} {url}")
        lines.append("")
    return "\n".join(lines)
