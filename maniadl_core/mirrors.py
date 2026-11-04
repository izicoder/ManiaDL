"""Mirror scheduling, per-host rate limiting and resumable downloads."""

from __future__ import annotations

import asyncio
import os
import random
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiohttp

from . import runtime, util
from .constants import (
    BROWSER_HEADERS,
    CHUNK_SIZE,
    FILE_TIMEOUT,
    MAX_RETRY_AFTER,
    MIN_FREE_GB,
    MIRRORS,
    RETRIES,
)


class MirrorMiss(Exception):
    """Mirror refuses or lacks this set (HTTP 403/404); try another mirror."""


class RateLimited(Exception):
    """HTTP 429: park the whole host instead of hammering it."""

    def __init__(self, seconds: int):
        super().__init__(f"rate limited, retry after {seconds}s")
        self.seconds = seconds


def _host_state(host: str) -> dict:
    state = runtime.host_state.get(host)
    if state is None:
        state = {
            "lock": asyncio.Lock(),
            "sem": asyncio.Semaphore(runtime.HOST_MAX_CONCURRENCY),
            "last": 0.0,
            "inflight": 0,
        }
        runtime.host_state[host] = state
    return state


def host_inflight(host: str) -> int:
    state = runtime.host_state.get(host)
    return int(state["inflight"]) if state else 0


@asynccontextmanager
async def host_slot(host: str):
    """Space request starts per host, then cap concurrent streams per host."""
    state = _host_state(host)
    async with state["lock"]:
        interval = runtime.HOST_MIN_INTERVAL * random.uniform(0.85, 1.15)
        wait = state["last"] + interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        state["last"] = time.monotonic()

    await state["sem"].acquire()
    state["inflight"] += 1
    try:
        yield
    finally:
        state["inflight"] -= 1
        state["sem"].release()


def choose_mirror(attempt: int, tried: set[str] | None = None):
    """Pick the healthiest ready mirror, excluding ones that missed this set.

    Returns (mirror, wait). ``mirror is None`` with ``wait > 0`` means every
    mirror host is cooling down; the caller should stop the run.
    """
    tried = tried or set()
    now = time.time()
    ready = [
        item
        for item in MIRRORS
        if runtime.mstats[item[0]]["until"] <= now
    ]
    if not ready:
        soonest = min(MIRRORS, key=lambda item: runtime.mstats[item[0]]["until"])
        return None, max(0.0, runtime.mstats[soonest[0]]["until"] - now)

    untried = [item for item in ready if item[0] not in tried]
    if not untried:
        return None, 0.0

    ranked = sorted(
        untried,
        key=lambda item: (
            host_inflight(util.mirror_host(item[1])),
            runtime.mstats[item[0]]["streak"],
            runtime.mstats[item[0]]["last"],
            -runtime.mstats[item[0]]["ok"],
            random.random(),
        ),
    )
    chosen = ranked[0]
    runtime.mstats[chosen[0]]["last"] = now
    return chosen, 0.0


def park_host(template: str, seconds: int) -> None:
    host = util.mirror_host(template)
    until = time.time() + min(max(int(seconds), 30), MAX_RETRY_AFTER)
    until += random.uniform(0, 5)
    for name, other in MIRRORS:
        if util.mirror_host(other) == host:
            runtime.mstats[name]["until"] = until
            runtime.mstats[name]["streak"] += 1
    runtime.log(
        f"[yellow]…[/] {host} cooling down for "
        f"{max(0, int(until - time.time()))}s"
    )


def _reset_progress(part: Path, progress, tid) -> None:
    size = 0
    try:
        if part.exists():
            size = part.stat().st_size
    except OSError:
        size = 0
    progress.update(tid, completed=size, total=None)


async def fetch(session, url: str, part: Path, progress, tid) -> None:
    """Stream to .part, resuming with Range when the mirror supports it."""
    existing = 0
    try:
        if part.exists():
            existing = part.stat().st_size
    except OSError:
        existing = 0

    headers = {**BROWSER_HEADERS, **util.mirror_headers(url)}
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"

    async with host_slot(util.mirror_host(url)):
        async with session.get(
            url, allow_redirects=True, headers=headers
        ) as response:
            if response.status == 429:
                raise RateLimited(util.retry_after(response.headers, 15))
            if response.status in (401, 403, 404, 451):
                raise MirrorMiss(f"HTTP {response.status}")
            if response.status == 416:
                part.unlink(missing_ok=True)
                raise aiohttp.ClientError("range not satisfiable; restarting")
            if response.status not in (200, 206):
                raise aiohttp.ClientError(f"HTTP {response.status}")

            if response.status == 206:
                match = re.match(
                    r"bytes\s+(\d+)-(\d+)/(\d+|\*)",
                    response.headers.get("Content-Range", ""),
                )
                if not match or int(match.group(1)) != existing:
                    part.unlink(missing_ok=True)
                    raise aiohttp.ClientError("bad Content-Range; restarting")
                start = existing
                total = (
                    int(match.group(3)) if match.group(3) != "*" else None
                )
                mode = "ab"
            else:
                start = 0
                total = response.content_length
                mode = "wb"
                if existing > 0:
                    runtime.log(
                        "[dim]mirror ignored Range; restarting this file[/]"
                    )

            progress.update(tid, completed=start, total=total)
            received = start
            with open(part, mode) as handle:
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    handle.write(chunk)
                    received += len(chunk)
                    runtime.stats["bytes"] += len(chunk)
                    progress.update(tid, advance=len(chunk))

            if total is not None and received != total:
                raise aiohttp.ClientPayloadError(
                    f"incomplete payload (got {received} of {total} bytes)"
                )
            if received == 0:
                raise aiohttp.ClientPayloadError("empty response body")


async def download_set(
    session,
    set_data: dict,
    cfg: dict,
    progress,
    overall,
    otid,
    sem,
    failed: dict,
    status,
) -> None:
    sid = int(set_data["id"])
    title = str(set_data.get("title") or "")
    dest = cfg["out"] / f"{sid}.osz"
    part = dest.with_suffix(".part")

    async with sem:
        tid = progress.add_task(f"{sid} {title[:38]}", total=None)
        runtime.stats["active"] += 1
        tried: set[str] = set()
        try:
            if dest.exists() and util.valid_osz(dest):
                runtime.log(f"[dim]…[/] {sid} already on disk")
                status.note_success(sid)
                return

            for attempt in range(RETRIES):
                if util.free_gb(cfg["out"]) < MIN_FREE_GB:
                    runtime.log("[red]Low disk space, stopping this set.[/]")
                    break

                mirror, wait = choose_mirror(attempt, tried)
                if mirror is None:
                    if wait > 0:
                        runtime.mirrors_exhausted = True
                        runtime.log(
                            "[yellow]…[/] all mirrors are cooling down; "
                            "stopping this set"
                        )
                    else:
                        runtime.log(
                            f"[yellow]![/] {sid}: no untried mirror left"
                        )
                    break

                name, template = mirror
                url = template.format(id=sid)
                try:
                    await asyncio.wait_for(
                        fetch(session, url, part, progress, tid),
                        FILE_TIMEOUT,
                    )
                    if not util.valid_osz(part):
                        part.unlink(missing_ok=True)
                        raise ValueError("not a valid .osz")
                    os.replace(part, dest)
                    status.note_success(sid)
                    runtime.mstats[name]["ok"] += 1
                    runtime.mstats[name]["streak"] = 0
                    runtime.mstats[name]["until"] = 0.0
                    runtime.stats["ok"] += 1
                    runtime.log(f"[green]+[/] {sid} via {name}")
                    return
                except RateLimited as exc:
                    park_host(template, exc.seconds)
                    _reset_progress(part, progress, tid)
                except MirrorMiss as exc:
                    tried.add(name)
                    runtime.mstats[name]["fail"] += 1
                    runtime.mstats[name]["streak"] += 1
                    _reset_progress(part, progress, tid)
                    runtime.log(
                        f"[yellow]![/] {sid} {name}: {exc} "
                        f"(try {attempt + 1}/{RETRIES})"
                    )
                except (
                    asyncio.TimeoutError,
                    aiohttp.ClientError,
                    ValueError,
                    OSError,
                ) as exc:
                    runtime.mstats[name]["fail"] += 1
                    runtime.mstats[name]["streak"] += 1
                    _reset_progress(part, progress, tid)
                    is_payload = isinstance(exc, aiohttp.ClientPayloadError)
                    runtime.log(
                        f"[yellow]![/] {sid} {name}: {type(exc).__name__} {exc} "
                        f"(try {attempt + 1}/{RETRIES})"
                    )
                    if (
                        isinstance(exc, OSError)
                        and util.free_gb(cfg["out"]) < MIN_FREE_GB
                    ):
                        runtime.log("[red]Low disk space, stopping this set.[/]")
                        break
                    delay = min(2**attempt + random.uniform(0, 1.5), 45)
                    if cfg.get("safe_mode", True):
                        delay *= 1.25
                    if is_payload:
                        delay = max(delay, 10)
                    await asyncio.sleep(delay)

            runtime.stats["fail"] += 1
            failed[sid] = title
            status.note_failure(sid, title)
            runtime.log(f"[red]x[/] {sid} gave up after {RETRIES} tries")
            runtime.log(
                f"[cyan]→[/] download manually: "
                f"https://osu.ppy.sh/beatmapsets/{sid}"
            )
        finally:
            runtime.stats["active"] -= 1
            progress.remove_task(tid)
            overall.update(otid, advance=1)
