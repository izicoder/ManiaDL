"""Human-readable labels for the GUI (no prompts, no rich markup)."""

from __future__ import annotations

from .constants import MAX_BPM, MAX_LENGTH, MAX_NOTES, SORT_LABELS


def range_label(low, high, low_default, high_default, unit: str = "") -> str:
    if low <= low_default and high >= high_default:
        return "any"
    if low > low_default and high < high_default:
        return f"{low:g}-{high:g}{unit}"
    if low > low_default:
        return f">={low:g}{unit}"
    return f"<={high:g}{unit}"


def date_label(after: str, before: str) -> str:
    if after and before:
        return f"{after}..{before}"
    if after:
        return f">={after}"
    if before:
        return f"<={before}"
    return "any"


def keys_label(cfg: dict) -> str:
    if cfg["keys"] is None:
        return "all"
    return ", ".join(f"{key}K" for key in cfg["keys"])


def summary_rows(cfg: dict) -> list[tuple[str, str]]:
    rows = [
        ("Download folder", str(cfg["out"])),
        ("Status", ", ".join(cfg["statuses"])),
        ("Keys", keys_label(cfg)),
        ("Star rating", f"{cfg['min_sr']:g} - {cfg['max_sr']:g}"),
        ("Min favourites", str(cfg["min_favs"])),
        ("Sort", SORT_LABELS.get(cfg["sort"], cfg["sort"])),
        ("Max sets", str(cfg["limit"])),
        ("Parallel / batch", f"{cfg['workers']} / {cfg['batch']}"),
    ]
    if not cfg["advanced"]:
        return rows

    rows.extend(
        [
            ("Query", cfg["query"] or "-"),
            ("Title contains", cfg["title"] or "-"),
            ("Artist contains", cfg["artist"] or "-"),
            ("Creator contains", cfg["creator"] or "-"),
            ("Source contains", cfg["source"] or "-"),
            ("Exclude", ", ".join(cfg["exclude"]) if cfg["exclude"] else "-"),
            ("Genre", ", ".join(cfg["genre"]) if cfg["genre"] else "any"),
            (
                "Language",
                ", ".join(cfg["language"]) if cfg["language"] else "any",
            ),
            ("BPM", range_label(cfg["min_bpm"], cfg["max_bpm"], 0.0, MAX_BPM)),
            (
                "Length",
                range_label(
                    cfg["min_length"], cfg["max_length"], 0, MAX_LENGTH, "s"
                ),
            ),
            (
                "Notes",
                range_label(cfg["min_notes"], cfg["max_notes"], 0, MAX_NOTES),
            ),
            ("Min plays", str(cfg["min_plays"])),
            (
                "Ranked",
                date_label(cfg["ranked_after"], cfg["ranked_before"]),
            ),
            ("NSFW", "include" if cfg["include_nsfw"] else "exclude"),
        ]
    )
    return rows


def search_rows(matched: int, todo: int, cfg: dict) -> list[tuple[str, str]]:
    rows = [
        ("Matching sets", str(matched)),
        ("Already downloaded", str(max(0, matched - todo))),
        ("To download", str(todo)),
        ("Status", ", ".join(cfg["statuses"])),
        ("Keys", keys_label(cfg)),
    ]
    if cfg["advanced"] and cfg["query"]:
        rows.append(("Query", cfg["query"]))
    return rows
