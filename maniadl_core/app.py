"""Application orchestration: auth -> search -> downloads.

The GUI calls :func:`run` from a worker thread. Nothing in here prompts or
prints; progress goes to a :class:`~maniadl_core.progress.TaskBoard` and log
lines go through :func:`maniadl_core.runtime.log`.
"""

from __future__ import annotations

import asyncio
import random
import time

import aiohttp

from . import api, mirrors, runtime, state, util
from .constants import (
    API_UA,
    BATCH_PAUSE,
    CONNECT_TIMEOUT,
    FAILED_LINKS_NAME,
    MIN_FREE_GB,
    SOCK_READ_TIMEOUT,
)
from .progress import StatusSink, TaskBoard


def batch_pause(cfg: dict) -> float:
    return max(BATCH_PAUSE, cfg["workers"] * 0.5) + random.uniform(0.0, 1.0)


async def _run_downloads(
    session, cfg: dict, todo: list, status: state.Status, progress, overall
):
    otid = overall.add_task("all", total=len(todo))
    started = time.time()
    failed: dict[int, str] = {}
    sem = asyncio.Semaphore(cfg["workers"])

    try:
        for index in range(0, len(todo), cfg["batch"]):
            if runtime.should_stop():
                runtime.log("Stopped by user.")
                break
            if util.free_gb(cfg["out"]) < MIN_FREE_GB:
                runtime.log("[red]Low disk space, stopping.[/]")
                break
            batch = todo[index : index + cfg["batch"]]
            runtime.log(f"Batch {index // cfg['batch'] + 1}: {len(batch)} sets")
            await asyncio.gather(
                *(
                    mirrors.download_set(
                        session,
                        set_data,
                        cfg,
                        progress,
                        overall,
                        otid,
                        sem,
                        failed,
                        status,
                    )
                    for set_data in batch
                )
            )
            status.flush()
            if runtime.should_stop():
                runtime.log("Stopped by user.")
                break
            await asyncio.sleep(batch_pause(cfg))
            if runtime.mirrors_exhausted:
                runtime.log(
                    "[red]Every mirror is rate-limiting us; stopping instead "
                    "of hammering them. Re-run later.[/]"
                )
                break
    finally:
        for leftover in cfg["out"].glob("*.part"):
            leftover.unlink(missing_ok=True)
        status.flush()
    return failed, time.time() - started


async def run(
    cfg: dict,
    cid,
    secret: str,
    progress: TaskBoard | None = None,
    overall: TaskBoard | None = None,
) -> dict:
    """Run one full search + download pass and return a summary dict."""
    runtime.reset_run()
    progress = progress or TaskBoard()
    overall = overall or TaskBoard()
    progress.reset()
    overall.reset()

    cfg["out"].mkdir(parents=True, exist_ok=True)
    for leftover in cfg["out"].glob("*.part"):
        leftover.unlink(missing_ok=True)
    # Older builds wrote a link report next to the maps; the GUI shows it now.
    (cfg["out"] / FAILED_LINKS_NAME).unlink(missing_ok=True)

    status = state.Status(cfg["out"]).load()

    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=CONNECT_TIMEOUT,
        sock_connect=CONNECT_TIMEOUT,
        sock_read=SOCK_READ_TIMEOUT,
    )
    connector = aiohttp.TCPConnector(
        limit=max(4, cfg["workers"] * 2),
        limit_per_host=runtime.HOST_MAX_CONCURRENCY,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )

    failed: dict[int, str] = {}
    elapsed = 0.0
    sets: list = []
    existing: set[int] = set()
    todo: list = []

    progress.set_message("Signing in to osu!...")
    async with aiohttp.ClientSession(
        timeout=timeout,
        headers={"User-Agent": API_UA},
        connector=connector,
    ) as session:
        token = await api.get_token(session, cid, secret)

        existing = state.scan_existing(cfg["out"]) | status.ids
        status.prune_failed(existing)
        if status.failed:
            runtime.log(
                f"{len(status.failed)} set(s) failed last run; they'll be retried."
            )

        progress.set_message("Searching osu!...")
        sets = await api.search_sets(session, token, cfg, StatusSink(progress))

        todo = [set_data for set_data in sets if set_data["id"] not in existing]
        runtime.log(
            f"Search finished: {len(sets)} matching, "
            f"{len(sets) - len(todo)} already downloaded, {len(todo)} to fetch."
        )

        if todo and not runtime.should_stop():
            progress.set_message(f"Downloading {len(todo)} sets...")
            failed, elapsed = await _run_downloads(
                session, cfg, todo, status, progress, overall
            )
        elif not todo:
            progress.set_message("Nothing new to download.")
            runtime.log("[green]Nothing new to download.[/]")
        else:
            progress.set_message("Stopped.")

    status.flush()
    if elapsed:
        progress.set_message(
            f"Done: {runtime.stats['ok']} downloaded, "
            f"{runtime.stats['fail']} failed in {elapsed:.1f}s."
        )
    return {
        "matched": len(sets),
        "existing": len(existing),
        "todo": len(todo),
        "failed": {
            sid: status.titles.get(str(sid), "") for sid in status.failed
        },
        "new_failed": failed,
        "titles": dict(status.titles),
        "elapsed": elapsed,
        "stopped": runtime.should_stop(),
        "mirrors_exhausted": runtime.mirrors_exhausted,
    }
