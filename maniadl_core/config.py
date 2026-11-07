"""Configuration loading, migration and validation."""

from __future__ import annotations

import json
from pathlib import Path

from . import util
from .constants import (
    CONFIG_PATH,
    DEFAULT_OUT,
    GENRE_IDS,
    LANGUAGE_IDS,
    MAX_BPM,
    MAX_LENGTH,
    MAX_NOTES,
    MAX_WORKERS,
    NEW_DEFAULTS,
    NEW_SETTING_KEYS,
    SORTS,
    STATUS_SETS,
)


def load_saved() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_saved(data: dict) -> None:
    try:
        util.atomic_write_text(
            CONFIG_PATH, json.dumps(data, indent=2, ensure_ascii=False)
        )
        try:
            CONFIG_PATH.chmod(0o600)
        except OSError:
            pass
    except OSError as exc:
        from . import runtime

        runtime.log(f"Couldn't save settings: {exc}")


def migrate_saved(saved: dict) -> tuple[dict, bool]:
    """Fill new optional keys without touching existing values."""
    changed = False
    # safe_mode was an internal pacing toggle that briefly leaked into config.
    if "safe_mode" in saved:
        saved.pop("safe_mode", None)
        changed = True
    if "slide_window" in saved:
        saved.pop("slide_window", None)
        changed = True
    for key in NEW_SETTING_KEYS:
        if key not in saved:
            saved[key] = NEW_DEFAULTS[key]
            changed = True
    return saved, changed


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_ids(terms: list[str], mapping: dict[str, int], kind: str) -> list[int]:
    """Turn partial genre/language names into the numeric ids the API expects.

    The UI accepts partial names (``elec`` matches ``Electronic``), so a term
    may resolve to more than one id. Unknown terms are a configuration error
    rather than a silently empty result.
    """
    ids: set[int] = set()
    unknown: list[str] = []
    for term in terms:
        matches = [value for name, value in mapping.items() if term in name]
        if not matches:
            unknown.append(term)
            continue
        ids.update(matches)
    if unknown:
        known = ", ".join(sorted(mapping))
        raise ValueError(
            f"Unknown {kind}: {', '.join(unknown)}. Try one of: {known}"
        )
    return sorted(ids)


def cfg_from_raw(raw: dict) -> dict:
    out = Path(str(raw.get("out") or DEFAULT_OUT)).expanduser()
    statuses = util.parse_statuses(util.as_text(raw.get("statuses", "ranked")))
    keys = util.parse_keys(util.as_text(raw.get("keys", "all")))

    min_sr = _to_float(raw.get("min_sr"), 0.0)
    max_sr = _to_float(raw.get("max_sr"), 99.0)
    if min_sr < 0:
        raise ValueError("Min star rating cannot be negative")
    if max_sr < min_sr:
        raise ValueError("Max star rating must be >= min star rating")

    min_favs = max(0, _to_int(raw.get("min_favs"), 0))
    sort = raw.get("sort") if raw.get("sort") in SORTS else SORTS[0]
    limit = max(1, _to_int(raw.get("limit"), 500))
    workers = max(1, min(MAX_WORKERS, _to_int(raw.get("workers"), 4)))
    batch = max(1, _to_int(raw.get("batch"), 20))
    advanced = util.as_bool(raw.get("advanced", False))

    cfg = {
        "out": out,
        "statuses": statuses,
        "keys": keys,
        "min_sr": min_sr,
        "max_sr": max_sr,
        "min_favs": min_favs,
        "sort": sort,
        "limit": limit,
        "workers": workers,
        "batch": batch,
        "advanced": advanced,
    }

    if advanced:
        cfg.update(
            {
                "query": str(raw.get("query") or "").strip(),
                "title": str(raw.get("title") or "").strip(),
                "artist": str(raw.get("artist") or "").strip(),
                "creator": str(raw.get("creator") or "").strip(),
                "source": str(raw.get("source") or "").strip(),
                "exclude": util.parse_csv(raw.get("exclude") or ""),
                "genre": util.parse_csv(raw.get("genre") or ""),
                "language": util.parse_csv(raw.get("language") or ""),
                "min_plays": max(0, _to_int(raw.get("min_plays"), 0)),
                "include_nsfw": util.as_bool(raw.get("include_nsfw", False)),
            }
        )

        bpm_low, bpm_high = util.parse_range(
            raw.get("bpm_range") or "", float, "BPM", 0, 1000
        )
        cfg["min_bpm"] = bpm_low if bpm_low is not None else 0.0
        cfg["max_bpm"] = bpm_high if bpm_high is not None else MAX_BPM

        len_low, len_high = util.parse_range(
            raw.get("length_range") or "", int, "length", 0, 24 * 3600
        )
        cfg["min_length"] = len_low if len_low is not None else 0
        cfg["max_length"] = len_high if len_high is not None else MAX_LENGTH

        note_low, note_high = util.parse_range(
            raw.get("notes_range") or "", int, "note count", 0, 10**7
        )
        cfg["min_notes"] = note_low if note_low is not None else 0
        cfg["max_notes"] = note_high if note_high is not None else MAX_NOTES

        ranked_low, ranked_high = util.parse_date_range(
            raw.get("ranked_range") or "", "ranked date"
        )
        cfg["ranked_after"] = ranked_low or ""
        cfg["ranked_before"] = ranked_high or ""
    else:
        cfg.update(
            {
                "query": "",
                "title": "",
                "artist": "",
                "creator": "",
                "source": "",
                "exclude": [],
                "genre": [],
                "language": [],
                "min_bpm": 0.0,
                "max_bpm": MAX_BPM,
                "min_length": 0,
                "max_length": MAX_LENGTH,
                "min_notes": 0,
                "max_notes": MAX_NOTES,
                "min_plays": 0,
                "ranked_after": "",
                "ranked_before": "",
                "include_nsfw": False,
            }
        )
    cfg["genre_ids"] = resolve_ids(cfg["genre"], GENRE_IDS, "genre")
    cfg["language_ids"] = resolve_ids(cfg["language"], LANGUAGE_IDS, "language")
    # Derived once per run so the per-set filter does no parsing or set building.
    cfg["query_terms"] = util.simple_query_terms(cfg["query"])
    cfg["allowed_statuses"] = (
        None
        if "any" in statuses
        else frozenset().union(*(STATUS_SETS[item] for item in statuses))
    )
    return cfg


def status_allowed(cfg: dict, value: str) -> bool:
    allowed = cfg.get("allowed_statuses")
    if allowed is None:
        if "any" in cfg["statuses"]:
            return True
        allowed = frozenset().union(*(STATUS_SETS[item] for item in cfg["statuses"]))
    return value in allowed
