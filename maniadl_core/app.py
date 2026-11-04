"""Application orchestration: config -> auth -> search -> downloads -> report."""

from __future__ import annotations

import asyncio
import getpass
import os
import random
import time

import aiohttp
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from . import api, config, mirrors, reports, runtime, state, ui, util
from .constants import (
    API_UA,
    BATCH_PAUSE,
    CONNECT_TIMEOUT,
    MIN_FREE_GB,
    SETTING_KEYS,
    SOCK_READ_TIMEOUT,
)


def batch_pause(cfg: dict) -> float:
    return max(BATCH_PAUSE, cfg["workers"] * 0.5) + random.uniform(0.0, 1.0)


async def _run_downloads(session, cfg: dict, todo: list, status: state.Status):
    progress, overall = ui.make_progress()
    otid = overall.add_task("all", total=len(todo))
    started = time.time()
    failed: dict[int, str] = {}
    sem = asyncio.Semaphore(cfg["workers"])

    def render():
        return ui.render_dashboard(cfg, started, overall, progress)

    try:
        from rich.live import Live

        with Live(
            get_renderable=render,
            refresh_per_second=6,
            console=runtime.console,
            transient=False,
        ):
            for index in range(0, len(todo), cfg["batch"]):
                if util.free_gb(cfg["out"]) < MIN_FREE_GB:
                    runtime.log("[red]Low disk space, stopping.[/]")
                    break
                batch = todo[index : index + cfg["batch"]]
                runtime.log(
                    f"Batch {index // cfg['batch'] + 1}: {len(batch)} sets"
                )
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


def _print_done(cfg: dict, elapsed: float) -> None:
    failed = runtime.stats["fail"]
    border = "green" if not failed else "yellow"
    runtime.console.print(
        Panel(
            f"[green]{runtime.stats['ok']} downloaded[/]  "
            f"[red]{failed} failed[/]  "
            f"{runtime.stats['bytes'] / 1e6:,.1f} MB in {elapsed:.1f}s\n"
            f"Files in {cfg['out']}",
            title="Done",
            border_style=border,
        )
    )


async def main() -> None:
    ui.print_banner()

    saved = config.load_saved()
    saved, migrated = config.migrate_saved(saved)
    if migrated and (saved.get("client_id") or saved.get("client_secret")):
        config.save_saved(saved)

    cid = os.environ.get("OSU_CLIENT_ID") or saved.get("client_id")
    secret = os.environ.get("OSU_CLIENT_SECRET") or saved.get("client_secret")
    if not (cid and secret):
        runtime.console.print(
            Panel(api.GUIDE, title="First time? Get API keys")
        )
        cid = cid or Prompt.ask("osu! client ID", console=runtime.console)
        secret = secret or getpass.getpass("osu! client secret (hidden): ")
        saved["client_id"], saved["client_secret"] = str(cid), secret
        config.save_saved(saved)
        runtime.console.print(
            f"[green]Credentials saved to {config.CONFIG_PATH}[/] "
            "(plain text, keep it private / out of git)"
        )
    else:
        runtime.console.print("[dim]Using saved credentials.[/]")

    cfg = None
    if all(key in saved for key in SETTING_KEYS):
        try:
            cfg = config.cfg_from_raw(saved)
            ui.show_summary(cfg)
            high_risk = ui.show_risk_report(cfg)
            if high_risk:
                accepted = Confirm.ask(
                    "[bold red]High-risk settings detected. Continue anyway?[/]",
                    default=False,
                    console=runtime.console,
                )
            else:
                accepted = Confirm.ask(
                    "Use these settings?",
                    default=True,
                    console=runtime.console,
                )
            if not accepted:
                cfg = None
        except (KeyError, ValueError, TypeError) as exc:
            runtime.console.print(
                f"[yellow]Saved settings need attention: {exc}[/]"
            )
            cfg = None

    if cfg is None:
        cfg, raw = ui.ask_config(saved)
        saved.update(raw)
        config.save_saved(saved)
        ui.show_summary(cfg)
        high_risk = ui.show_risk_report(cfg)
        if high_risk:
            accepted = Confirm.ask(
                "[bold red]High-risk settings detected. Continue anyway?[/]",
                default=False,
                console=runtime.console,
            )
        else:
            accepted = Confirm.ask(
                "Use these settings?", default=True, console=runtime.console
            )
        if not accepted:
            runtime.console.print("[yellow]Cancelled.[/]")
            return

    cfg["out"].mkdir(parents=True, exist_ok=True)
    for leftover in cfg["out"].glob("*.part"):
        leftover.unlink(missing_ok=True)

    runtime.reset_run()
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

    elapsed = 0.0
    async with aiohttp.ClientSession(
        timeout=timeout,
        headers={"User-Agent": API_UA},
        connector=connector,
    ) as session:
        token = await api.get_token(session, cid, secret)

        existing = state.scan_existing(cfg["out"]) | status.ids
        status.prune_failed(existing)
        if status.failed:
            runtime.console.print(
                f"[dim]{len(status.failed)} set(s) failed last run; they'll be "
                "retried.[/]"
            )

        with runtime.console.status("[cyan]Searching osu!...[/]") as spinner:
            sets = await api.search_sets(session, token, cfg, spinner)

        todo = [set_data for set_data in sets if set_data["id"] not in existing]
        ui.show_search_summary(sets, todo, existing, cfg)

        if not todo:
            runtime.console.print("[green]Nothing new to download.[/]")
        elif not Confirm.ask(
            "Start downloading?", default=True, console=runtime.console
        ):
            runtime.console.print("[yellow]Cancelled.[/]")
        else:
            _, elapsed = await _run_downloads(session, cfg, todo, status)
            _print_done(cfg, elapsed)
            if runtime.mirrors_exhausted:
                runtime.console.print(
                    Panel(
                        "[yellow]Stopped early: the mirrors rate-limited this IP. "
                        "Nothing was hammered. Re-run later; finished sets are "
                        "already recorded.[/]",
                        border_style="yellow",
                        title="Paused safely",
                    )
                )

    reports.print_failed_links(cfg["out"], status.failed, status.titles)
