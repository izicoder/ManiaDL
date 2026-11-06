# ManiaDL

Desktop tkinter app that bulk-downloads osu!mania beatmap sets (`.osz`) from
osu! mirrors for import into osu!lazer. Filters by key count, status, star
rating, favourites, metadata, BPM, length, notes, genre, language, ranked date
and more; keeps per-folder download state.

## Fast start

- Install: `uv sync` (or `uv pip install aiohttp`)
- Run: `uv run maniadl.py` — opens the window, no CLI flags
- Credentials: env `OSU_CLIENT_ID` / `OSU_CLIENT_SECRET` override the saved config
- Test: `uv run python -m unittest discover -s tests -t . -v` (offline, no API/mirror calls)
- Lint/format/typecheck: none configured
- Build: `uv sync --extra build` then
  `uv run --extra build pyinstaller --onefile --windowed --name ManiaDL maniadl.py`
  (`ManiaDL.spec` is kept in sync manually)
- Before committing: inspect `git diff` manually (no hooks or CI)

## Purpose and scope

- Solves "download hundreds of mania maps matching my taste" without a browser;
  written for the author's own osu!lazer library, Windows-first.
- In scope: settings UI, search, filters, mirror fallback, parallel/batched
  downloads, resume state, failed-set view with direct links, rate-limit
  avoidance.
- Out of scope: importing into lazer, writing into the osu! `Songs/` folder,
  extra report files. The old `dl.old.py` (if present in history) is not used.
- Maturity: personal tool. The package docstrings, `README.md` and this file are
  the documentation.

## Architecture

`maniadl.py` is a thin entry point that launches the GUI. The implementation
lives in `maniadl_core/`:

- `gui.py` — tkinter window: scrollable left settings panel, right status
  panel (overall bar, stats, active transfers, log, failed sets), Start/Stop,
  worker thread and the 120 ms polling loop.
- `app.py` — `run()` orchestration: auth -> search -> downloads -> summary.
  Also owns batch pacing. No prompts or printing.
- `progress.py` — thread-safe `TaskBoard` (rich-Progress-compatible subset used
  by the downloader) plus `StatusSink` for search messages.
- `config.py` — load/save config, migrate old configs, `cfg_from_raw()`.
- `ui.py` — pure label helpers (`range_label`, `date_label`, `summary_rows`,
  `search_rows`) used by the GUI; no widgets, no rich.
- `api.py` — osu! OAuth token, search pagination, query building, client-side
  `qualifies()`, search-query fallback.
- `mirrors.py` — mirror selection, per-host rate limiting, resumable `fetch()`,
  `download_set()`.
- `state.py` — `Status` (`status.json`), legacy text-file import, `scan_existing`.
- `reports.py` — in-memory failed-set rows and clipboard text (no file output).
- `runtime.py` — shared log feed + listener, stats, mirror health, per-host
  state, stop flag, `reset_run()`.
- `util.py` — parsing, ranges/dates, disk space, atomic writes, `.osz` validation,
  direct links.
- `constants.py` — API URLs, mirrors, statuses, sort keys, setting keys, tunables.

Main flow:
1. `gui.ManiaDLApp` loads `mania_dl_config.json`, migrates it and fills every
   widget; `runtime.set_log_listener()` forwards log lines to a queue.
2. Start validates the form with `cfg_from_raw()`, saves config, and runs
   `app.run()` in a daemon worker thread under `asyncio.run()`.
3. `api.get_token()` exchanges client credentials for an OAuth access token.
4. `api.search_sets()` loops API statuses × key counts, cursor-paginates
   `GET /beatmapsets/search`, and applies `qualifies()` client-side.
5. `state.scan_existing(out) | status.ids` filters `todo`; batches of
   `cfg["batch"]` run `download_set` under an `asyncio.Semaphore(cfg["workers"])`.
6. Each set: `choose_mirror()` ranks healthy mirrors → `fetch()` to `NNN.part`
   (Range resume when supported) → `valid_osz()` zip/`.osu` check → `os.replace`
   to `NNN.osz` → `status.note_success()`.
7. The worker posts a summary on an event queue; the Tk thread fills the status
   panel and the Failed downloads tab with direct official/mirror links.

## Domain data

- `status.json` (version 2, atomic writes via `Status.save()`):
  `{"version": 2, "updated": iso, "downloaded": {id: stamp}, "failed": [ids],
  "titles": {id: title}}`. Version 1 files are read and upgraded on first run;
  older builds ignore the extra `titles` key.
- The download folder contains only `.osz` files and `status.json`; no reports.
  Stale `failed_links.txt` files from older builds are deleted on the next run.
- Legacy `downloaded_ids.txt` / `failed.txt` are imported once by
  `Status._migrate_legacy()` and then deleted.
- Config shape: `client_id`, `client_secret`, legacy `SETTING_KEYS`
  (`out, statuses, keys, min_sr, max_sr, min_favs, sort, limit, workers,
  batch`) plus new keys (`advanced, query, title, artist, creator, source,
  exclude, genre, language, bpm_range, length_range, notes_range, min_plays,
  ranked_range, include_nsfw`). Retired `safe_mode` / `slide_window` keys are
  dropped by `migrate_saved()`.
- Status mapping `STATUS_SETS` (e.g. `ranked` → `{ranked, approved}`); API
  statuses live in `API_STATUSES` (e.g. `pending` → `pending` + `wip`).
- External services: osu! v2 API (`https://osu.ppy.sh/api/v2`, token at
  `https://osu.ppy.sh/oauth/token`), mirrors in `MIRRORS` (`nerinyan`, `nekoha`,
  `catboy`, `beatconnect`, `osu.direct`, `sayobot`). No database/cache/queue.

## Hard constraints

- Do not send `BROWSER_HEADERS` to the osu! API; use `API_UA`. Browser UA +
  mirror `Referer` is only for mirror downloads (Cloudflare 403s otherwise).
- Do not retry a mirror 429 inline. `RateLimited` parks the whole host in
  `runtime.mstats`; the run stops when all mirrors are parked.
- Do not write `status.json` non-atomically or by hand; `Status.save()` owns it.
  Saves are batched (`SAVE_EVERY` / `SAVE_INTERVAL`) and flushed per batch.
- Do not add files to the download folder. Failures belong in the GUI.
- Do not drop or rename `SETTING_KEYS` casually; an old config is only reused
  when all of them are present. Extra old keys are ignored, and retired keys can
  be dropped in `migrate_saved()`. New keys belong in `NEW_SETTING_KEYS`.
- Do not import or extend `dl.old.py`.
- To bridge the downloader and GUI, use `TaskBoard` (not rich); the downloader
  only relies on `add_task` / `update` / `remove_task`.
- Request pacing is internal and always on: per-host spacing, per-host
  concurrency cap, jittered backoff, and `Retry-After` respect. It is not a
  user-facing setting; do not add controls or warnings for it.

## Infrastructure

| Area | Command / file | Notes |
| --- | --- | --- |
| Toolchain | `pyproject.toml`, `.venv/` | uv-managed CPython 3.14; dep aiohttp, tkinter from stdlib |
| Install | `uv sync` | optional build extra: `uv sync --extra build` |
| Run | `uv run maniadl.py` | opens the tkinter window; all input in the UI |
| Test | `uv run python -m unittest discover -s tests -t . -v` | offline fakes in `tests/fakes.py` |
| Lint/format | absent | no ruff/mypy/black config |
| Build | `uv run --extra build pyinstaller --onefile --windowed --name ManiaDL maniadl.py` | `ManiaDL.spec` kept in sync manually (`console=False`) |
| CI | `.github/workflows/build.yml` | tests + windowed exe; release on `v*` tags |
| Release | tag `v2.0.0` (or manual workflow) | publishes `ManiaDL.exe` on GitHub |
| Data | `status.json` in the chosen output folder | `.osz` files only besides that |
| Env | `.gitignore` lines ~237–247 | config, status, `*.part`, `*.osz` ignored |
| Hooks | absent | no husky/pre-commit |
| Observability | "Log" tab + "Failed downloads" tab | no log files or metrics |

## Conventions

- Modules are grouped by responsibility (see Architecture); keep new code in the
  matching module instead of growing `gui.py` or `app.py`.
- Tunables are uppercase constants near the top of `constants.py`
  (`RETRIES`, `FILE_TIMEOUT`, `MIN_FREE_GB`, host limits).
- `snake_case` functions; docstrings on non-obvious helpers (`choose_mirror`,
  `valid_osz`, `qualifies`, `build_query`).
- Persistence is plain `json` + `pathlib`, never a DB; paths derive from `HERE`
  (`sys.frozen`-aware) so a packaged exe keeps state beside the exe.
- Log lines go through `runtime.log()`; the GUI applies plain-text tags itself.
- Expected failures are custom exceptions (`MirrorMiss`, `RateLimited`,
  `SearchRejected`); fatal auth/search errors use `SystemExit` and are surfaced
  by the GUI worker as an error dialog.
- Commit history uses short imperative subjects.
- Tests use stdlib `unittest` + `IsolatedAsyncioTestCase`; no network calls, no
  Tk window (GUI formatting helpers are tested directly).

## Traps and tips

- `HERE` in `constants.py` points at the directory containing `maniadl.py`, not
  the package directory. Keep it that way or configs move unexpectedly.
- `mania_dl_config.json` stores the OAuth secret in plaintext and is gitignored;
  never commit it, paste it, or add it to docs. Use env vars for shared machines.
- Deleting/relocating `status.json` or changing `out` re-downloads everything
  that is not still on disk as `NNN*.osz` (`scan_existing` parses the numeric
  prefix).
- A 403/404 is `MirrorMiss` (try another mirror); a 429 parks the host. Adding
  sleep-and-retry on 429 is how the IP gets banned — the stop is intentional.
- `limit` caps total matches; already-downloaded sets are filtered out after
  the search, so raise `limit` when you want to reach further into the results.
- Advanced filters are applied twice: a server-side `q` narrows the search, and
  `api.qualifies()` is authoritative. If osu! rejects the query (HTTP 400),
  `search_sets()` falls back to fewer server-side filters automatically.
- `length` is checked per matching difficulty (the API filters nested beatmaps);
  BPM, genre, language, ranked date and favourites are set-level.
- Stop is cooperative: `runtime.request_stop()` is checked between batches, in
  `download_set`, and inside search pagination. In-flight files finish; sets
  that were not started stay queued for the next run.
- Tk widgets may only be touched from the Tk thread. Worker code calls
  `runtime.log()`, `TaskBoard` methods and queues; never `widget.configure()`.
- `--onefile` exes unpack to a temp dir; `HERE` already handles this — do not
  switch config/output paths to `__file__` unguarded.
- Download leftovers (`*.part`) are cleaned on startup and after each run. They
  are safe to delete but never rename to `.osz`. Within a run, Range resume is
  attempted before falling back to a full download.
- No automated live tests: mirror/Cloudflare behaviour still needs a manual run
  with valid credentials. The unit suite deliberately uses fakes only.

## Open questions

- Whether the PyInstaller exe is distributed outside GitHub releases — CI now
  builds it on tags, but nothing verifies the executable beyond PyInstaller's
  own success.
- Community mirrors change or die often; `MIRRORS` needs manual maintenance.
