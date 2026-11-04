"""Small pure helpers shared by the rest of the package."""

from __future__ import annotations

import os
import re
import shutil
import time
import zipfile
from pathlib import Path

from .constants import DISK_CACHE_TTL, MAX_RETRY_AFTER, MIRRORS

_DISK_CACHE = {"path": None, "at": 0.0, "value": 0.0}

_RANGE_PAIR = re.compile(
    r"^\s*(?P<a>-?\d+(?:\.\d+)?)\s*(?:-|\.\.|to|,)\s*"
    r"(?P<b>-?\d+(?:\.\d+)?)\s*$",
    re.I,
)
_RANGE_OP = re.compile(r"^\s*(?P<op>>=|<=|>|<|=)\s*(?P<v>-?\d+(?:\.\d+)?)\s*$")
_RANGE_ONE = re.compile(r"^\s*(?P<v>-?\d+(?:\.\d+)?)\s*$")

_DATE_TOKEN = re.compile(r"^\d{4}(?:[-/.]\d{1,2}(?:[-/.]\d{1,2})?)?$")
_DATE_OP = re.compile(r"^\s*(?P<op>>=|<=|>|<|=)\s*(?P<v>\S+)\s*$")
_DATE_PAIR = re.compile(r"^\s*(?P<a>\S+?)\s*(?:\.\.|to)\s*(?P<b>\S+)\s*$", re.I)
_DATE_YEAR_PAIR = re.compile(r"^\s*(?P<a>\d{4})\s*-\s*(?P<b>\d{4})\s*$")

_QUERY_OP = re.compile(
    r"\b(?:stars?|ar|cs|od|hp|dr|bpm|length|keys?|status|creator|artist|"
    r"title|source|tag|favourites|ranked|updated|created|circles|sliders)"
    r"\s*(?:>=|<=|>|<|=|:)",
    re.I,
)


def as_text(value) -> str:
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(item) for item in value)
    return str(value)


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def parse_csv(value) -> list[str]:
    """Lowercase, comma/semicolon separated list. Spaces are kept inside terms."""
    if isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value]
    else:
        parts = re.split(r"[,;]", str(value or ""))
    return [part.strip().lower() for part in parts if part.strip()]


def parse_range(
    text,
    cast=float,
    name: str = "value",
    minimum: float | None = None,
    maximum: float | None = None,
) -> tuple[float | int | None, float | int | None]:
    """Parse '150-220', '>=150', '<=220', '150' or blank into (low, high)."""
    raw = str(text or "").strip()
    if not raw or raw.lower() in ("any", "all", "*"):
        return None, None

    low = high = None
    pair = _RANGE_PAIR.match(raw)
    if pair:
        low, high = float(pair.group("a")), float(pair.group("b"))
    else:
        op = _RANGE_OP.match(raw)
        if op:
            value = float(op.group("v"))
            token = op.group("op")
            if token in (">", ">="):
                low = value
            elif token in ("<", "<="):
                high = value
            else:  # "=" means an exact value
                low = high = value
        else:
            one = _RANGE_ONE.match(raw)
            if not one:
                raise ValueError(f"Invalid {name} range: {raw!r}")
            low = high = float(one.group("v"))

    if low is not None and high is not None and low > high:
        raise ValueError(f"{name} range starts above it ends: {raw!r}")
    if minimum is not None and low is not None and low < minimum:
        raise ValueError(f"{name} must be >= {minimum:g}")
    if maximum is not None and high is not None and high > maximum:
        raise ValueError(f"{name} must be <= {maximum:g}")

    if cast is int:
        low = int(round(low)) if low is not None else None
        high = int(round(high)) if high is not None else None
    else:
        low = float(low) if low is not None else None
        high = float(high) if high is not None else None
    return low, high


def _normalise_date(token: str) -> str:
    token = token.strip().replace("/", "-").replace(".", "-")
    if not _DATE_TOKEN.match(token):
        raise ValueError(f"Invalid date: {token!r} (use YYYY, YYYY-MM or YYYY-MM-DD)")
    parts = token.split("-")
    if len(parts) > 1:
        parts[1] = parts[1].zfill(2)
    if len(parts) > 2:
        parts[2] = parts[2].zfill(2)
    return "-".join(parts)


def parse_date_range(text, name: str = "date") -> tuple[str | None, str | None]:
    """Parse '2020..2024', '2020-01-01..2024-12-31', '>=2020' or blank."""
    raw = str(text or "").strip()
    if not raw or raw.lower() in ("any", "all", "*"):
        return None, None

    low = high = None
    pair = _DATE_PAIR.match(raw)
    if pair:
        low, high = pair.group("a"), pair.group("b")
    else:
        year_pair = _DATE_YEAR_PAIR.match(raw)
        if year_pair:
            low, high = year_pair.group("a"), year_pair.group("b")
        else:
            op = _DATE_OP.match(raw)
            if op:
                value = op.group("v")
                if op.group("op").startswith(">"):
                    low = value
                else:
                    high = value
            else:
                low = high = raw

    low = _normalise_date(low) if low is not None else None
    high = _normalise_date(high) if high is not None else None
    if low and high and low > high:
        raise ValueError(f"{name} range starts above it ends: {raw!r}")
    return low, high


def parse_statuses(text: str) -> list[str]:
    parts = [part.strip().lower() for part in str(text).split(",") if part.strip()]
    if not parts or "any" in parts:
        return ["any"]
    valid = {"graveyard", "ranked", "loved", "qualified", "pending"}
    bad = [part for part in parts if part not in valid]
    if bad:
        raise ValueError(f"Unknown status: {', '.join(bad)}")
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(parts))


def parse_keys(text: str):
    raw = str(text).strip().lower()
    if raw in ("", "all", "any"):
        return None
    keys = sorted({int(item) for item in re.split(r"[,\s]+", raw) if item})
    if any(key < 1 or key > 18 for key in keys):
        raise ValueError("Key counts must be between 1 and 18")
    return keys


def stamp(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts or time.time()))


def free_gb(path: Path) -> float:
    """Cached disk-free lookup so the live dashboard does not stat constantly."""
    key = str(path)
    now = time.monotonic()
    if _DISK_CACHE["path"] == key and now - _DISK_CACHE["at"] < DISK_CACHE_TTL:
        return _DISK_CACHE["value"]
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        value = shutil.disk_usage(probe).free / 1e9
    except OSError:
        value = 0.0
    _DISK_CACHE.update(path=key, at=now, value=value)
    return value


def reset_disk_cache() -> None:
    _DISK_CACHE.update(path=None, at=0.0, value=0.0)


def retry_after(headers, default: int = 15) -> int:
    """Parse Retry-After as seconds or HTTP-date, capped for sanity."""
    value = headers.get("Retry-After") if headers else None
    if not value:
        return default
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        try:
            from email.utils import parsedate_to_datetime
            import datetime as _dt

            when = parsedate_to_datetime(str(value))
            if when.tzinfo is None:
                when = when.replace(tzinfo=_dt.timezone.utc)
            seconds = int((when - _dt.datetime.now(_dt.timezone.utc)).total_seconds())
        except Exception:
            seconds = default
    return max(1, min(seconds, MAX_RETRY_AFTER))


def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def valid_osz(path: Path) -> bool:
    """A real .osz is a zip with at least one .osu difficulty inside."""
    try:
        if not path.is_file() or path.stat().st_size < 22:
            return False
        with zipfile.ZipFile(path) as archive:
            return any(name.lower().endswith(".osu") for name in archive.namelist())
    except (OSError, ValueError, zipfile.BadZipFile):
        return False


def mirror_host(template: str) -> str:
    return template.split("://", 1)[-1].split("/", 1)[0]


def mirror_headers(url: str) -> dict[str, str]:
    scheme, _, rest = url.partition("://")
    host = rest.split("/", 1)[0]
    return {"Referer": f"{scheme}://{host}/"}


def direct_links(sid: int) -> list[tuple[str, str]]:
    links = [("osu!", f"https://osu.ppy.sh/beatmapsets/{sid}")]
    seen = {links[0][1]}
    for name, template in MIRRORS:
        url = template.format(id=sid)
        if url not in seen:
            seen.add(url)
            links.append((name, url))
    return links


def simple_query_terms(query: str) -> list[str]:
    """Terms to verify client-side for plain text queries.

    Queries using osu! operators are left to the API, because reproducing the
    parser locally would only cause false negatives.
    """
    raw = str(query or "").strip()
    if not raw or _QUERY_OP.search(raw):
        return []
    return [part.strip('"').lower() for part in re.split(r"\s+", raw) if part.strip('"')]
