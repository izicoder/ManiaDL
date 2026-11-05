"""osu! API authentication, search and client-side filtering."""

from __future__ import annotations

import asyncio
import random

import aiohttp

from . import config, runtime, util
from .constants import (
    API,
    API_STATUSES,
    API_UA,
    SEARCH_DELAY,
    SEARCH_MAX_PAGES,
    SEARCH_RETRIES,
    TOKEN_URL,
)

GUIDE = """How to get your osu! API keys
1. Log in at https://osu.ppy.sh.
2. Open your settings: https://osu.ppy.sh/home/account/edit
3. Scroll to the OAuth section and click New OAuth Application.
4. Name it anything (e.g. "mania dl"). Callback URL: http://localhost
5. Click Register. You now see your Client ID (a number) and Client Secret
   (a long string). Copy both. If you lose the secret, you can reset it on
   the same page.
6. Keep the secret private. Never share it or post it publicly.
"""


class SearchRejected(Exception):
    """osu! returned HTTP 400 for the query; retry with fewer server filters."""


def search_delay() -> float:
    return SEARCH_DELAY + random.uniform(0.0, 0.5)


async def get_token(session: aiohttp.ClientSession, cid, secret: str) -> str:
    try:
        client_id = int(cid)
    except (TypeError, ValueError):
        raise SystemExit("osu! client ID must be a number.")

    payload = {
        "client_id": client_id,
        "client_secret": secret,
        "grant_type": "client_credentials",
        "scope": "public",
    }

    last_error = ""
    for attempt in range(3):
        async with session.post(TOKEN_URL, json=payload) as response:
            if response.status == 200:
                data = await response.json()
                token = data.get("access_token")
                if not token:
                    raise SystemExit("osu! returned no access token.")
                return token

            detail = (await response.text())[:200].strip()
            last_error = detail
            if response.status in (400, 401):
                bad = config.load_saved()
                if "client_id" in bad or "client_secret" in bad:
                    bad.pop("client_id", None)
                    bad.pop("client_secret", None)
                    config.save_saved(bad)
                    runtime.log(
                        "Saved credentials removed; please check and re-enter them."
                    )
                runtime.log(GUIDE)
                raise SystemExit(f"Auth failed (HTTP {response.status}). {detail}")

            if response.status == 429 or response.status >= 500:
                wait = util.retry_after(response.headers, 15)
                runtime.log(
                    f"osu! token endpoint returned HTTP {response.status}; "
                    f"waiting {wait}s before retry {attempt + 1}/3."
                )
                await asyncio.sleep(wait)
                continue

            runtime.log(
                f"osu! refused the token request (HTTP {response.status}). "
                "That's their server, not your keys; saved credentials were kept. "
                "Try again in a minute."
            )
            raise SystemExit(f"Auth failed (HTTP {response.status}). {detail}")

    raise SystemExit(f"Auth failed after retries. {last_error}")


def _text_field(set_data: dict, field: str) -> str:
    if field == "title":
        return f"{set_data.get('title') or ''} {set_data.get('title_unicode') or ''}"
    if field == "artist":
        return f"{set_data.get('artist') or ''} {set_data.get('artist_unicode') or ''}"
    return str(set_data.get(field) or "")


def _haystack(set_data: dict) -> str:
    parts = [
        _text_field(set_data, "title"),
        _text_field(set_data, "artist"),
        str(set_data.get("creator") or ""),
        str(set_data.get("source") or ""),
        str(set_data.get("tags") or ""),
    ]
    for beatmap in set_data.get("beatmaps") or []:
        parts.append(str(beatmap.get("version") or ""))
    return " ".join(parts).lower()


def _name(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "").lower()
    return ""


def _set_bpm(set_data: dict) -> float:
    try:
        return float(set_data.get("bpm") or 0)
    except (TypeError, ValueError):
        values = []
        for beatmap in set_data.get("beatmaps") or []:
            try:
                values.append(float(beatmap.get("bpm") or 0))
            except (TypeError, ValueError):
                pass
        return max(values, default=0.0)


def _set_length(set_data: dict) -> int:
    values = []
    try:
        values.append(int(set_data.get("total_length") or 0))
    except (TypeError, ValueError):
        pass
    for beatmap in set_data.get("beatmaps") or []:
        try:
            values.append(int(beatmap.get("total_length") or 0))
        except (TypeError, ValueError):
            pass
    return max(values, default=0)


def _diff_length(beatmap: dict, set_data: dict) -> int:
    try:
        return int(beatmap.get("total_length") or 0)
    except (TypeError, ValueError):
        return _set_length(set_data)


def _notes(beatmap: dict) -> int:
    total = 0
    for key in ("count_circles", "count_sliders", "count_spinners"):
        try:
            total += int(beatmap.get(key) or 0)
        except (TypeError, ValueError):
            pass
    return total


def _date_prefix(value) -> str:
    text = str(value or "")
    return text[:10] if text else ""


def _matches_prefix(filter_value: str, date_value: str) -> bool:
    """Compare a YYYY[-MM[-DD]] filter against an ISO ranked date."""
    if not date_value:
        return False
    return date_value[: len(filter_value)] >= filter_value


def _before_prefix(filter_value: str, date_value: str) -> bool:
    if not date_value:
        return False
    return date_value[: len(filter_value)] <= filter_value


def qualifies(set_data: dict, cfg: dict) -> bool:
    """All user filters, applied client-side so API quirks cannot leak sets in."""
    if not config.status_allowed(cfg, str(set_data.get("status") or "")):
        return False

    try:
        favourites = int(set_data.get("favourite_count") or 0)
    except (TypeError, ValueError):
        favourites = 0
    if favourites < cfg["min_favs"]:
        return False

    try:
        plays = int(set_data.get("play_count") or 0)
    except (TypeError, ValueError):
        plays = 0
    if plays < cfg["min_plays"]:
        return False

    if not cfg["include_nsfw"] and set_data.get("nsfw"):
        return False

    haystack = _haystack(set_data)

    for term in util.simple_query_terms(cfg["query"]):
        if term not in haystack:
            return False
    for term in cfg["exclude"]:
        if term in haystack:
            return False
    for field in ("title", "artist", "creator", "source"):
        needle = cfg.get(field, "").lower()
        if needle and needle not in _text_field(set_data, field).lower():
            return False

    if cfg["genre"]:
        genre = _name(set_data.get("genre"))
        if not any(term in genre for term in cfg["genre"]):
            return False
    if cfg["language"]:
        language = _name(set_data.get("language"))
        if not any(term in language for term in cfg["language"]):
            return False

    bpm = _set_bpm(set_data)
    if bpm < cfg["min_bpm"] or bpm > cfg["max_bpm"]:
        return False

    if cfg["ranked_after"] and not _matches_prefix(
        cfg["ranked_after"], _date_prefix(set_data.get("ranked_date"))
    ):
        return False
    if cfg["ranked_before"] and not _before_prefix(
        cfg["ranked_before"], _date_prefix(set_data.get("ranked_date"))
    ):
        return False

    for beatmap in set_data.get("beatmaps") or []:
        if beatmap.get("mode_int") != 3:
            continue
        try:
            key_count = int(beatmap.get("cs") or 0)
        except (TypeError, ValueError):
            continue
        if cfg["keys"] is not None and key_count not in cfg["keys"]:
            continue
        try:
            stars = float(beatmap.get("difficulty_rating") or 0)
        except (TypeError, ValueError):
            continue
        if not (cfg["min_sr"] <= stars <= cfg["max_sr"]):
            continue
        notes = _notes(beatmap)
        if notes < cfg["min_notes"] or notes > cfg["max_notes"]:
            continue
        length = _diff_length(beatmap, set_data)
        if length < cfg["min_length"] or length > cfg["max_length"]:
            continue
        return True
    return False


def _query_text(value: str) -> str:
    # Strip quotes that would break the API parser; keep normal words/spaces.
    return " ".join(str(value).replace('"', " ").split())


def build_query(cfg: dict, key: int | None) -> str:
    """Build an osu! search query. Client-side filters remain authoritative."""
    parts: list[str] = []
    if cfg["query"]:
        parts.append(_query_text(cfg["query"]))
    for field in ("title", "artist", "creator", "source"):
        value = cfg.get(field, "")
        if value:
            parts.append(_query_text(value))
    if key is not None:
        parts.append(f"keys={key}")
    if cfg["min_sr"] > 0:
        parts.append(f"stars>={cfg['min_sr']:g}")
    if cfg["max_sr"] < 99:
        parts.append(f"stars<={cfg['max_sr']:g}")
    if cfg["min_bpm"] > 0:
        parts.append(f"bpm>={cfg['min_bpm']:g}")
    if cfg["max_bpm"] < 9999:
        parts.append(f"bpm<={cfg['max_bpm']:g}")
    if cfg["min_length"] > 0:
        parts.append(f"length>={cfg['min_length']}")
    if cfg["max_length"] < 10**9:
        parts.append(f"length<={cfg['max_length']}")
    if cfg["min_favs"] > 0:
        parts.append(f"favourites>={cfg['min_favs']}")
    if cfg["ranked_after"]:
        parts.append(f"ranked>={cfg['ranked_after']}")
    if cfg["ranked_before"]:
        parts.append(f"ranked<={cfg['ranked_before']}")
    return " ".join(part for part in parts if part)


def minimal_query(cfg: dict, key: int | None) -> str:
    parts: list[str] = []
    if cfg["query"]:
        parts.append(_query_text(cfg["query"]))
    if key is not None:
        parts.append(f"keys={key}")
    return " ".join(part for part in parts if part)


async def search_one(
    session,
    headers,
    params,
    cfg,
    found,
    status,
) -> None:
    cursor = None
    seen_cursors: set[str] = set()
    pages = 0

    while len(found) < cfg["limit"]:
        if runtime.should_stop():
            return
        query = dict(params)
        if cursor:
            query["cursor_string"] = cursor

        data = None
        for attempt in range(SEARCH_RETRIES):
            try:
                async with session.get(
                    f"{API}/beatmapsets/search", params=query, headers=headers
                ) as response:
                    if response.status == 429:
                        wait = util.retry_after(response.headers, 15)
                        runtime.log(
                            f"[yellow]…[/] osu! API rate limit; waiting {wait}s"
                        )
                        await asyncio.sleep(wait)
                        continue
                    if response.status >= 500:
                        wait = min(2**attempt + random.uniform(0, 1.5), 30)
                        runtime.log(
                            f"[yellow]![/] osu! API HTTP {response.status}; "
                            f"retrying in {wait:.0f}s"
                        )
                        await asyncio.sleep(wait)
                        continue
                    if response.status == 400:
                        detail = (await response.text())[:200].strip()
                        raise SearchRejected(detail or "HTTP 400")
                    if response.status != 200:
                        raise SystemExit(
                            f"Search failed (HTTP {response.status})."
                        )
                    data = await response.json()
                break
            except SearchRejected:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                wait = min(2**attempt + random.uniform(0, 1.5), 30)
                runtime.log(
                    f"[yellow]![/] search error ({type(exc).__name__}); "
                    f"retrying in {wait:.0f}s"
                )
                await asyncio.sleep(wait)
        if data is None:
            raise SystemExit("Search failed after retries.")

        if data.get("error"):
            runtime.log(f"[yellow]![/] osu! search: {data['error']}")

        for set_data in data.get("beatmapsets") or []:
            if qualifies(set_data, cfg):
                found[set_data["id"]] = set_data

        status.update(
            f"Searching... {len(found)} matching sets"
        )

        cursor = data.get("cursor_string")
        if not cursor or not data.get("beatmapsets"):
            break
        if cursor in seen_cursors:
            break
        seen_cursors.add(cursor)
        pages += 1
        if pages >= SEARCH_MAX_PAGES:
            runtime.log("[yellow]![/] search page cap reached; stopping search.")
            break
        await asyncio.sleep(search_delay())


async def search_sets(session, token, cfg, status) -> list:
    headers = {"Authorization": f"Bearer {token}", "User-Agent": API_UA}
    found: dict = {}
    key_list = cfg["keys"] if cfg["keys"] is not None else [None]

    combos: list[tuple[str, int | None]] = []
    for user_status in cfg["statuses"]:
        api_statuses = ("any",) if user_status == "any" else API_STATUSES[user_status]
        for api_status in api_statuses:
            for key in key_list:
                combo = (api_status, key)
                if combo not in combos:
                    combos.append(combo)

    for api_status, key in combos:
        if len(found) >= cfg["limit"] or runtime.should_stop():
            break

        params = {
            "m": "3",
            "sort": cfg["sort"],
            "nsfw": "true" if cfg["include_nsfw"] else "false",
        }
        if api_status != "any":
            params["s"] = api_status
        query = build_query(cfg, key)
        if query:
            params["q"] = query

        try:
            await search_one(
                session, headers, params, cfg, found, status
            )
        except SearchRejected as exc:
            runtime.log(
                f"[yellow]![/] osu! rejected the advanced query ({exc}); "
                "retrying with fewer server-side filters."
            )
            fallback = dict(params)
            fallback_query = minimal_query(cfg, key)
            if fallback_query and fallback_query != params.get("q"):
                fallback["q"] = fallback_query
            else:
                fallback.pop("q", None)
            try:
                await search_one(
                    session, headers, fallback, cfg, found, status
                )
            except SearchRejected:
                fallback.pop("q", None)
                runtime.log(
                    "[yellow]![/] still rejected; searching without the text "
                    "query. Client-side filters still apply."
                )
                await search_one(
                    session, headers, fallback, cfg, found, status
                )

    sets = list(found.values())
    return sets[: cfg["limit"]]
