# ManiaDL

Interactive Python CLI that bulk-downloads osu!mania beatmap sets (`.osz`) from
osu! mirrors for import into osu!lazer. Filters by key count, status, star
rating and favourites; keeps per-folder download state.

## Fast start

- Install: `uv pip install aiohttp rich` (prereq: Python 3.14 venv at `.venv`, network)
- Run: `.venv\Scripts\python.exe maniadl.py` — interactive prompts, no args
- Credentials: env `OSU_CLIENT_ID` / `OSU_CLIENT_SECRET` override the saved config
- Test: no test suite; verify with a live run against the osu! API (needs credentials)
- Lint/format/typecheck: none configured
- Before committing: inspect `git diff` manually (no hooks or CI)

## Purpose and scope

- Solves "download hundreds of mania maps matching my taste" without a browser;
  written for the author's own osu!lazer library, Windows-first.
- In scope: search, filter, mirror fallback, parallel/batched downloads, resume state.
- Out of scope: importing into lazer, writing into the osu! `Songs/` folder,
  GUI (the old `dl.old.py` did the Songs-folder scan).
- Maturity: personal tool, 12 commits, no CI/tests/release config. The module
  docstring is the only documentation; `README` does not exist.

## Architecture

- Entry point: `maniadl.py` → `main()` at line ~681, run via `asyncio.run` under
  `if __name__ == "__main__"` with a `KeyboardInterrupt` handler.
- Single module, four implicit layers:
  - Settings/state: `load_saved`/`save_saved`, `ask_config`, `cfg_from_raw`,
    `Status` (JSON state), `parse_statuses`, `parse_keys`.
  - osu! API: `get_token`, `search_sets`, `search_one`, `qualifies`.
  - Downloading: `choose_mirror`, `fetch`, `download_set`.
  - TUI: module-level `console`, `stats`, `mstats`, `log_lines`, `render()`,
    `rich` `Live`/`Progress` panels.
- Main flow:
  1. `load_saved()` reads `mania_dl_config.json`; missing creds prompt once and
     are saved (`save_saved`, chmod 0600).
  2. `cfg_from_raw()` builds the run config; `show_summary()` then
     `Confirm.ask("Use these settings?")`.
  3. `get_token()` exchanges client credentials for an OAuth access token.
  4. `search_sets()` loops statuses × key counts, cursor-paginates
     `GET /beatmapsets/search`, keeps sets passing `qualifies()` (mode 3 diffs).
  5. `scan_existing(out) | status.ids` filters `todo`; batches of `cfg["batch"]`
     run `download_set` under an `asyncio.Semaphore(cfg["workers"])`.
  6. Each set: `choose_mirror()` ranks healthy mirrors → `fetch()` to `NNN.part`
     → `zipfile.is_zipfile` check → `os.replace` to `NNN.osz` → `mark_done()`.
- Domain data:
  - Output folder state: `status.json` written atomically (temp + `os.replace`),
    shape `{"version": 1, "updated": iso, "downloaded": {id: stamp}, "failed": [ids]}`.
  - Config file shape: `client_id`, `client_secret` plus all `SETTING_KEYS`
    (`out, statuses, keys, min_sr, max_sr, min_favs, sort, limit, slide_window, workers, batch`).
  - Status mapping `STATUS_SETS` (e.g. `ranked` → `{ranked, approved}`); sort keys in `SORTS`.
- External services: osu! v2 API (`API` = `https://osu.ppy.sh/api/v2`, token at
  `https://osu.ppy.sh/oauth/token`), mirrors listed in `MIRRORS` (`catboy`,
  `beatconnect`, `osu.direct`). No database, no cache, no queue.
- Hard constraints:
  - Do not send `BROWSER_HEADERS` to the osu! API; use `API_UA`. Browser UA +
    mirror `Referer` is only for mirror downloads (Cloudflare 403s otherwise).
  - Do not retry a 429 host inline; `RateLimited` parks the whole host in
    `mstats` and the run stops when all mirrors are parked.
  - Do not write `status.json` non-atomically or by hand; `Status.save()` owns it.
  - Do not drop or rename `SETTING_KEYS`; `main()` requires all of them or re-prompts.
  - Do not import or extend `dl.old.py`; it is a preserved previous version.

## Infrastructure

| Area | Command / file | Notes |
| --- | --- | --- |
| Toolchain | `.venv/pyvenv.cfg` | uv-managed CPython 3.14.8; deps from site-packages, no lockfile in repo |
| Install | `uv pip install aiohttp rich` | no `requirements.txt` / `pyproject.toml` |
| Run | `.venv\Scripts\python.exe maniadl.py` | no CLI flags; all input is prompted |
| Test | absent | manual live run only |
| Lint/format | absent | no ruff/mypy/black config |
| Build | `pyinstaller --onefile --console --name ManiaDL maniadl.py` | unverified; no `.spec` in repo, PyInstaller not installed |
| CI | absent | no `.github/`, `.gitlab-ci.yml` |
| Release | absent | no tags, no remote configured |
| Data | `status.json` in the chosen output folder | legacy `downloaded_ids.txt`/`failed.txt` imported once by `Status._migrate_legacy` |
| Env | `.gitignore` lines 237–247 | `mania_dl_config.json`, `status.json`, `*.part`, `*.osz` ignored |
| Hooks | absent | no husky/pre-commit |
| Observability | `log()` → `log_lines` deque (10 entries) + rich `Live` panel | no log files or metrics |

## Conventions

- One module, section banners `# ---- name ----`; tunables as uppercase constants
  near the top (`RETRIES`, `FILE_TIMEOUT`, `MIN_FREE_GB`).
- `snake_case` functions with docstrings on non-obvious helpers (see `new_matches`,
  `choose_mirror`); typing is partial (`dict`, `Path`, `-> None`).
- Persistence is plain `json` + `pathlib`, never a DB; paths derive from `HERE`
  (`sys.frozen`-aware) so a packaged exe keeps state beside the exe.
- User output goes through `rich` markup strings (`[green]+[/] ...`) via `log()`.
- Expected failures are custom exceptions (`MirrorMiss`, `RateLimited`); fatal
  auth/search errors use `SystemExit` with an explanatory panel.
- Commit history uses short imperative subjects ("Fix dead mirrors, spoof browser
  headers…", "Replace downloaded_ids.txt/failed.txt with a single status.json…").
- `shit.md` is scratch notes, not a README; do not treat it as current docs.

## Traps and tips

- `shit.md` build steps are stale: they name `osu_mania_downloader.py` and pass
  `--collect-all textual`, but the script is `maniadl.py` and imports only `rich`.
- `mania_dl_config.json` stores the OAuth secret in plaintext and is gitignored;
  never commit it, paste it, or add it to docs. Use env vars for shared machines.
- Deleting/relocating `status.json` or changing `out` re-downloads everything that
  is not still on disk as `NNN*.osz` (`scan_existing` parses the numeric prefix).
- A 403/404 is `MirrorMiss` (try another mirror); a 429 parks the host. Adding
  sleep-and-retry on 429 is how the IP gets banned — the stop is intentional.
- `slide_window=false` caps total matches at `limit`; `true` keeps paging until
  `limit` *new* sets are found. Changing it changes result counts, not filters.
- `--onefile` exes unpack to a temp dir; `HERE` already handles this — do not
  switch config/output paths to `__file__` unguarded.
- Download leftovers (`*.part`) are cleaned on startup and in `finally`; they are
  safe to delete but never rename to `.osz`.
- Debug affordances: the "Log" panel shows the last 10 events; failures land in
  `status.json` → `failed` and are retried on the next run.
- No automated tests: a code change needs a manual run with valid credentials and
  network; expect live mirror/Cloudflare variability.

## Open questions

- Whether the PyInstaller exe is actually built or distributed anywhere — no spec,
  no CI, no artifacts in the repo.
- Whether `textual` (installed in `.venv` but unimported) is still wanted.
- Community mirrors change or die often; `MIRRORS` needs manual maintenance.
