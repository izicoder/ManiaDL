# ManiaDL

Interactive Python CLI that bulk-downloads osu!mania beatmap sets (`.osz`) from
osu! mirrors for import into osu!lazer. Filters by key count, status, star
rating, favourites, metadata, BPM, length, notes, genre, language, ranked date
and more; keeps per-folder download state.

## Fast start

- Install: `uv sync` (or `uv pip install aiohttp rich`)
- Run: `uv run maniadl.py` — interactive prompts, no args
- Credentials: env `OSU_CLIENT_ID` / `OSU_CLIENT_SECRET` override the saved config
- Test: `uv run python -m unittest discover -s tests -t . -v` (offline, no API/mirror calls)
- Lint/format/typecheck: none configured
- Build: `uv run --extra build pyinstaller --onefile --console --name ManiaDL maniadl.py`
- Before committing: inspect `git diff` manually (no hooks or CI)

## Purpose and scope

- Solves "download hundreds of mania maps matching my taste" without a browser;
  written for the author's own osu!lazer library, Windows-first.
- In scope: search, filters, mirror fallback, parallel/batched downloads, resume
  state, failed-link reports, rate-limit avoidance.
- Out of scope: importing into lazer, writing into the osu! `Songs/` folder,
  GUI. The old `dl.old.py` (if present in history) is not used.
- Maturity: personal tool, no CI/release config. The package docstrings and this
  file are the documentation; there is no README.

## Architecture

`maniadl.py` is a thin entry point. The implementation lives in `maniadl_core/`:

- `app.py` — `main()` orchestration: config -> auth -> search -> downloads ->
  report. Also owns batch pacing.
- `config.py` — load/save config, migrate old configs, `cfg_from_raw()`,
  `risk_items()`.
- `ui.py` — rich banner, prompts (`ask_config`), settings/risk/search summaries,
  live dashboard (`make_progress`, `render_dashboard`).
- `api.py` — osu! OAuth token, search pagination, query building, client-side
  `qualifies()`, search-query fallback.
- `mirrors.py` — mirror selection, per-host rate limiting, resumable `fetch()`,
  `download_set()`.
- `state.py` — `Status` (`status.json`), legacy text-file import, `scan_existing`.
- `reports.py` — `failed_links.txt` writer and failed-download table.
- `runtime.py` — shared console, log buffer, stats, mirror health, per-host state.
- `util.py` — parsing, ranges/dates, disk space, atomic writes, `.osz` validation,
  direct links.
- `constants.py` — API URLs, mirrors, statuses, sort keys, setting keys, tunables.

Main flow:
1. `config.load_saved()` reads `mania_dl_config.json`; `migrate_saved()` fills
   new optional keys. Credentials are prompted once and saved (`save_saved`,
   atomic, chmod 0600).
2. `cfg_from_raw()` validates settings. `ui.show_summary()` and
   `ui.show_risk_report()` run before confirmation; high-risk settings require
   an explicit opt-in.
3. `api.get_token()` exchanges client credentials for an OAuth access token.
4. `api.search_sets()` loops API statuses × key counts, cursor-paginates
   `GET /beatmapsets/search`, and applies `qualifies()` client-side.
5. `state.scan_existing(out) | status.ids` filters `todo`; batches of
   `cfg["batch"]` run `download_set` under an `asyncio.Semaphore(cfg["workers"])`.
6. Each set: `choose_mirror()` ranks healthy mirrors → `fetch()` to `NNN.part`
   (Range resume when supported) → `valid_osz()` zip/`.osu` check → `os.replace`
   to `NNN.osz` → `status.note_success()`.
7. `reports.print_failed_links()` prints direct official/mirror links and writes
   `failed_links.txt` in the output folder.

## Domain data

- `status.json` (version 2, atomic writes via `Status.save()`):
  `{"version": 2, "updated": iso, "downloaded": {id: stamp}, "failed": [ids],
  "titles": {id: title}}`. Version 1 files are read and upgraded on first run;
  older builds ignore the extra `titles` key.
- Legacy `downloaded_ids.txt` / `failed.txt` are imported once by
  `Status._migrate_legacy()`.
- `failed_links.txt` in the output folder lists every failed set with the
  official page and all mirror URLs. It is regenerated/removed each run.
- Config shape: `client_id`, `client_secret`, legacy `SETTING_KEYS`
  (`out, statuses, keys, min_sr, max_sr, min_favs, sort, limit, slide_window,
  workers, batch`) plus new keys (`safe_mode, advanced, query, title, artist,
  creator, source, exclude, genre, language, bpm_range, length_range,
  notes_range, min_plays, ranked_range, include_nsfw`).
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
- Do not drop or rename `SETTING_KEYS`; `main()` requires all of them to reuse an
  old config. New keys belong in `NEW_SETTING_KEYS` with defaults.
- Do not import or extend `dl.old.py`.
- Keep strict anti-ban mode on by default: per-host spacing, per-host
  concurrency cap, jittered backoff, and `Retry-After` respect.

## Infrastructure

| Area | Command / file | Notes |
| --- | --- | --- |
| Toolchain | `pyproject.toml`, `.venv/` | uv-managed CPython 3.14; deps aiohttp + rich |
| Install | `uv sync` | optional build extra: `uv sync --extra build` |
| Run | `uv run maniadl.py` | no CLI flags; all input is prompted |
| Test | `uv run python -m unittest discover -s tests -t . -v` | offline fakes in `tests/fakes.py` |
| Lint/format | absent | no ruff/mypy/black config |
| Build | `uv run --extra build pyinstaller --onefile --console --name ManiaDL maniadl.py` | `ManiaDL.spec` kept in sync manually |
| CI | absent | no `.github/`, `.gitlab-ci.yml` |
| Release | absent | no tags, no remote configured |
| Data | `status.json`, `failed_links.txt` in the chosen output folder | legacy text files imported once |
| Env | `.gitignore` lines ~237–247 | config, status, `*.part`, `*.osz` ignored |
| Hooks | absent | no husky/pre-commit |
| Observability | `runtime.log()` → log panel + `failed_links.txt` | no log files or metrics |

## Conventions

- Modules are grouped by responsibility (see Architecture); keep new code in the
  matching module instead of growing `app.py`.
- Tunables are uppercase constants near the top of `constants.py`
  (`RETRIES`, `FILE_TIMEOUT`, `MIN_FREE_GB`, host limits).
- `snake_case` functions; docstrings on non-obvious helpers (`choose_mirror`,
  `valid_osz`, `qualifies`, `build_query`).
- Persistence is plain `json` + `pathlib`, never a DB; paths derive from `HERE`
  (`sys.frozen`-aware) so a packaged exe keeps state beside the exe.
- User output goes through `runtime.console` and rich markup strings.
- Expected failures are custom exceptions (`MirrorMiss`, `RateLimited`,
  `SearchRejected`); fatal auth/search errors use `SystemExit` with an
  explanatory panel.
- Commit history uses short imperative subjects.
- Tests use stdlib `unittest` + `IsolatedAsyncioTestCase`; no network calls.

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
- `slide_window=false` caps total matches at `limit`; `true` keeps paging until
  `limit` *new* sets are found. Changing it changes result counts, not filters.
- Advanced filters are applied twice: a server-side `q` narrows the search, and
  `api.qualifies()` is authoritative. If osu! rejects the query (HTTP 400),
  `search_sets()` falls back to fewer server-side filters automatically.
- `length` is checked per matching difficulty (the API filters nested beatmaps);
  BPM, genre, language, ranked date and favourites are set-level.
- `--onefile` exes unpack to a temp dir; `HERE` already handles this — do not
  switch config/output paths to `__file__` unguarded.
- Download leftovers (`*.part`) are cleaned on startup and after each run. They
  are safe to delete but never rename to `.osz`. Within a run, Range resume is
  attempted before falling back to a full download.
- Debug affordances: the live "Log" panel shows recent events; failures land in
  `status.json` → `failed` and in `failed_links.txt`.
- No automated live tests: mirror/Cloudflare behaviour still needs a manual run
  with valid credentials. The unit suite deliberately uses fakes only.

## Open questions

- Whether the PyInstaller exe is actually built or distributed anywhere — no
  spec changes are automated, no CI, no artifacts in the repo.
- Whether `textual` (still present in some venvs but unimported) is wanted.
- Community mirrors change or die often; `MIRRORS` needs manual maintenance.
