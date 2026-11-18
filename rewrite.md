# ManiaDL: C# Rewrite (single source of truth)

This one file replaces `AGENTS.md`, `README.md`, `spec.txt` and the earlier architecture report. Everything the rewrite needs from them is merged here.

| Part | What it is |
|---|---|
| **A. Brief** | Goal, scope, rules for the agent, conflicts between the old docs, open questions |
| **B. Behavioral reference** | What the current Python app does, section by section (the contract to preserve) |
| **C. Rewrite guide** | Stack decisions, project layout, phased plan (0–8), tests, definition of done |

Conventions:

- `[B5.3]`, `[B15 risk 4]` point into Part B. `C2.1`, `C5` point into Part C. Part A items are `A1`, `A2`, …
- The Python source (`maniadl.py`, `maniadl_core/`, `tests/`) **stays in the repo as the reference implementation until the port reaches parity**. Several exact values (constants, regexes, genre/language tables) are not reproduced in this document and must be copied from it (see A6). Do not delete the Python code during the port.
- **Where Python behavior and this document disagree, Python behavior wins.** Note the discrepancy in `tests/PORTING.md`.

---

## A1. Goal

Rewrite ManiaDL, a bulk osu!mania beatmap downloader, as a **C# application with a WebView2-hosted web UI**, with **behavior unchanged** from the current Python app.

Reasons (from the maintainer): the tkinter UI is poor and Python is not the language they want to maintain. A further requirement is that a coding agent must be able to drive and screenshot the real UI to test it, which is why the UI is web-based and hosted in WebView2.

## A2. Product summary

Bulk osu!mania beatmap downloader for osu!lazer. Searches the osu! API with the filters you care about, then downloads matching `.osz` sets from community mirrors with automatic fallback, rate-limit handling and resume support.

Features to preserve:

- Filter by status, key count, star rating, favourites, plays, BPM, length, notes, genre, language, ranked date, mapper/title/artist/source and NSFW.
- Free-text osu! search query support (`stars>=5`, `keys=4`, `ranked>=2020`, …).
- Fast searches: requests paced at osu!'s requested ~60/minute; genre/language narrow the query server-side instead of only being checked after every page. Nothing is cached between runs.
- Parallel downloads with batching, per-host pacing and automatic mirror fallback (nerinyan, nekoha, catboy, beatconnect, osu.direct, sayobot).
- Resumable transfers and `.osz` validation before a file is accepted.
- Live status panel: overall progress, active downloads, stats and log.
- Failed sets stay visible in the Failed downloads tab with direct links.
- One `status.json` per download folder remembers what was fetched and what failed. Nothing else is written there besides the `.osz` files.
- Credentials: entered in the window, saved to `mania_dl_config.json` beside the exe in plain text (never commit it), with `OSU_CLIENT_ID` / `OSU_CLIENT_SECRET` environment variables overriding saved values. A "How to get keys" link opens <https://osu.ppy.sh/home/account/edit>.

Requirements: Windows only, forever. Single user.

Out of scope: importing into lazer, writing into the osu! `Songs/` folder, extra report files, any CLI mode, the old `dl.old.py` (ignore it), the uncommitted lazer-dedup prototype.

## A3. Original brief (from `spec.txt`, still binding)

```text
goal:
full rewrite into gui program
behavior is unchaged from cli one
output folder should only have one status.json as always, no other files besides osz and status.json

ui:
left panel has all settings
right panel has all status shit

tips:
dont break shit
continue working on this branch
```

How it applies now:

- "Behavior unchanged": the reference is the current Python app (Part B). The old CLI is history.
- Folder contract: the download folder holds only `.osz` files and exactly one `status.json`.
- Layout: left panel has all settings, right panel has all status [B10.1].
- "Don't break stuff": see A4.
- "Continue on this branch": see A4.

## A4. Rules for the agent

1. **Stay on the current branch.** Do not create new branches, rebase, or rewrite history. Commit small and often; subjects are short and imperative (e.g. `Add status store`).
2. **Don't break the existing app.** Keep the Python implementation working and untouched until the maintainer approves removal after parity (Phase 8). Put C# in `src/`, `ui/`, `tests/` alongside it.
3. **Inspect `git diff` before every commit.** There are no hooks.
4. **Never commit, print, or paste secrets.** `mania_dl_config.json` holds a plaintext OAuth secret. Tests must use temp dirs and fake credentials. Do not add real credentials to docs, fixtures or logs.
5. **Port behavior first, improve second.** Phases 0–6 preserve behavior; Phase 7 holds deliberate changes. Do not mix them.
6. **Ask the maintainer before:** changing the folder contract, changing `.part` cross-run resume behavior, deleting any Python file, adding dependencies beyond the list in C9.
7. **Do not add user-facing controls or warnings for request pacing.** It is internal and always on [B8.3].

## A5. Conflicts and stale claims in the old docs (resolved)

| # | Old claim | Reality | Decision |
|---|---|---|---|
| 1 | Maintainer notes: "an old config is only reused when all `SETTING_KEYS` are present" | Code never uses `SETTING_KEYS`; `migrate_saved()` fills missing keys from defaults and preserves existing values [B5.1] | Port the **code** behavior (fill missing, preserve existing). Decide in Phase 7 whether to drop `SETTING_KEYS` entirely. |
| 2 | README: live status panel shows "mirror health" | Current `main` UI has six stat cards, active transfers, log and failed tab, and no mirror-health view [B10.6] | Not required for parity. Optional follow-up: a small mirror-health strip fed by the engine (the data exists in mirror stats). |
| 3 | Maintainer notes: "no hooks or CI" | A CI workflow exists (`build.yml`) | CI exists. Phase 8 updates it for .NET + Node. |
| 4 | Maintainer notes: "uv-managed CPython 3.14" | `pyproject` says Python ≥3.10; CI uses 3.12 | Irrelevant to C#. Ignore. |
| 5 | Maintainer notes: "Download leftovers (`*.part`) are cleaned on startup and after each run" | Matches [B9] | Preserve: delete `*.part` at start and in the run's `finally`. |
| 6 | README: sets recorded in `status.json` are skipped even if the `.osz` was later removed | Matches `existing = scan ∪ status.ids` [B6.5] | Preserve explicitly (add a test). |
| 7 | Env credentials override saved config | They are also written back to config on Start [B15 risk 4] | Preserve in Phases 0–6, fix in Phase 7 item 1. |

## A6. Values to copy verbatim from the Python source

These are not reproduced here. Open `maniadl_core/constants.py` (and the named module) and copy exact values and wording into C# constants, with a test per group:

- `API_UA` and `BROWSER_HEADERS` (never mix them up) and `API`, `TOKEN_URL`
- `SEARCH_INTERVAL` and every pacer constant (jitter, decay, cap)
- Host pacing constants (spacing, concurrency cap, park clamp, jitter)
- `RETRIES`, `FILE_TIMEOUT`, `MIN_FREE_GB`, `SAVE_EVERY`, `SAVE_INTERVAL`, chunk size, log caps
- `MIRRORS` (exact templates; Part B lists them, but verify)
- `STATUS_SETS`, `API_STATUSES`, `SORTS`
- `GENRE_IDS`, `LANGUAGE_IDS` (full tables)
- `NEW_DEFAULTS`, `NEW_SETTING_KEYS`, `SETTING_KEYS`
- The osu! operator regex used by `simple_query_terms`
- The "key guide" text logged on auth failure, and any user-facing message strings (footer messages, summary row labels in `ui.py`)
- Exact `qualifies()` comparison semantics (inclusive/exclusive bounds) from `api.py`

## A7. Open questions (defaults chosen; maintainer may override)

| Question | Default if unanswered |
|---|---|
| Is the exe distributed outside GitHub releases? Nothing verifies the built executable beyond the build succeeding. | GitHub releases only. Add a CI smoke test (Phase 8). |
| Mirrors change or die often. | Keep the list as constants now; data-driven override in Phase 7. |
| `.part` cross-run resume: keep deleting (parity) or keep and resume? | Keep deleting (parity). Ask before changing. |
| Version number for the C# release | `3.0.0` (Python was `2.0.0`); single source in `Directory.Build.props`. |
| Keep `launch.bat` / `build_exe.bat`? | Replace with equivalents that call the .NET build, after parity. |

---

# PART B: Behavioral reference (current Python `main`, commit `00c8c9e`)

This is the contract the C# port must reproduce. Sections are numbered B1–B16 and cited in Part C as `[B5.3]`, `[B15 risk 4]`, and so on. It describes only the committed Python application (87 offline tests passing). An uncommitted osu!lazer-dedup prototype existed during analysis and is **not** part of `main`.

---

## B1. System context

ManiaDL is a single-user, single-process Windows desktop application that:

1. Authenticates against the osu! OAuth API.
2. Searches osu! beatmapsets filtered to osu!mania.
3. Applies additional filters client-side.
4. Downloads matching `.osz` sets from community mirrors.
5. Keeps per-folder download state in one `status.json`.
6. Shows progress, logs, stats and failed downloads in a dark UI.

There is no server, database, cache service, queue, background daemon, or CLI mode.

| Dependency | Purpose |
|---|---|
| `https://osu.ppy.sh/oauth/token` | OAuth client-credentials token |
| `https://osu.ppy.sh/api/v2` | Beatmapset search |
| 6 mirror hosts / 7 endpoint templates | `.osz` downloads |
| Local filesystem | config, `.osz`, `.part`, `status.json` |
| Environment variables | optional credential override (`OSU_CLIENT_ID`, `OSU_CLIENT_SECRET`) |

---

## B2. Python repository and module catalog (reference only)

```text
maniadl.py                    entry point; calls gui.main()
maniadl_core/
  __init__.py                 version string
  constants.py                tunables, mirrors, API constants, persisted keys
  util.py                     pure parsing/filesystem/HTTP helpers
  config.py                   config load/save/migrate/validate
  runtime.py                  mutable per-run state, log feed, stop flag
  progress.py                 TaskBoard + StatusSink
  state.py                    Status persistence + folder scan
  api.py                      OAuth, search, query building, qualifies()
  mirrors.py                  mirror scheduling, host pacing, resume, download
  app.py                      orchestration: auth -> search -> downloads
  reports.py                  in-memory failed rows + clipboard text
  ui.py                       pure UI label/summary helpers
  gui.py                      tkinter application
tests/                        offline stdlib unittest suite (tests/fakes.py)
.github/workflows/build.yml   test + PyInstaller + GitHub release
```

| Module | Responsibility | Key public surface |
|---|---|---|
| `constants.py` | Every tunable, mirror, API URL, status map, setting key | `API`, `MIRRORS`, `STATUS_SETS`, `API_STATUSES`, `SORTS`, limits |
| `util.py` | Ranges, dates, lists, disk, atomic writes, `.osz` validation, links | `parse_range`, `parse_date_range`, `parse_statuses`, `parse_keys`, `valid_osz`, `free_gb`, `retry_after`, `atomic_write_text`, `direct_links` |
| `config.py` | Load/save JSON, migration, validation, derived cfg | `load_saved`, `save_saved`, `migrate_saved`, `resolve_ids`, `cfg_from_raw`, `status_allowed` |
| `runtime.py` | Global run state, logs, stop | `log`, `set_log_listener`, `request_stop`, `should_stop`, `reset_run` |
| `progress.py` | Thread-safe progress snapshots | `TaskBoard`, `StatusSink` |
| `state.py` | `status.json`, legacy import, folder scan | `scan_existing`, `Status` |
| `api.py` | Token, search, pacing, query building, client filter | `get_token`, `search_sets`, `search_one`, `SearchPacer`, `build_query`, `minimal_query`, `search_params`, `qualifies` |
| `mirrors.py` | Mirror choice, host pacing, resume, download | `fetch`, `download_set`, `choose_mirror`, `park_host` |
| `app.py` | End-to-end orchestration and batching | `run`, `batch_pause` |
| `reports.py` | Failed-row models and clipboard text | `failed_entries`, `links_text` |
| `ui.py` | Pure labels/summary rows | `range_label`, `date_label`, `keys_label`, `summary_rows`, `search_rows` |
| `gui.py` | Entire tkinter UI, worker lifecycle, polling | `ManiaDLApp`, `main` |

Build/runtime facts of the Python app:

- Python `>=3.10`, managed with `uv`; runtime dependency `aiohttp`; build extra `pyinstaller`.
- Build: `pyinstaller --onefile --windowed --name ManiaDL maniadl.py`. `ManiaDL.spec` mirrors it (`console=False`, UPX).
- `constants.HERE` is frozen-aware: source → directory containing `maniadl.py` (**not** the package dir); frozen → directory containing `ManiaDL.exe`. Config and default downloads live beside the executable/script.
- Helper scripts: `launch.bat`, `build_exe.bat`.
- CI (`.github/workflows/build.yml`): `windows-latest`, Python 3.12, `uv sync --extra build`, offline tests, PyInstaller, upload `dist/ManiaDL.exe`, publish a GitHub release on `v*` tags (also manually triggerable).
- `.gitignore` excludes config, `status.json`, legacy state files, `*.part`, `*.osz`.

---

## B3. Runtime topology

Two execution contexts and one global state layer.

```text
Tk main thread
  ├─ widgets, polling, dialogs
  ├─ 120 ms _tick
  │   ├─ drain log queue
  │   ├─ drain event queue
  │   └─ refresh live progress/stats
  └─ Start/Stop/close handling

Worker thread (one per run)
  └─ asyncio.run(app.run(...))
      ├─ aiohttp ClientSession
      ├─ token request
      ├─ search loop (sequential pages)
      ├─ batch downloads (asyncio.gather)
      │   ├─ workers semaphore
      │   ├─ per-host concurrency semaphore
      │   └─ per-host start spacing lock
      └─ status flush
```

| Channel | Direction | Mechanism |
|---|---|---|
| Logs | worker → UI | `runtime.log()` → listener → `queue.Queue` |
| Progress | worker → UI | `TaskBoard` mutated under lock; UI polls snapshot |
| Events | worker → UI | `queue.Queue` with `done`, `error` |
| Stop | UI → worker | `runtime._stop` (`threading.Event`) |
| Run result | worker → UI | event queue `("done", result_dict)` |

`runtime.py` is a mutable singleton imported by almost every module. It owns: `stats = {ok, fail, active, bytes}`; `mstats[mirror] = {ok, fail, streak, until, last}`; `host_state[host] = {lock, sem, last, inflight}`; `mirrors_exhausted`; `log_lines` (deque, max 500); the log listener; the stop flag; host pacing constants. This global singleton is the main architectural smell and the main rewrite hazard.

## B4. Dependency direction

```text
gui ──► app ──► api, mirrors, state, util
 │       └──► runtime
 ├──► config ──► util
 ├──► reports ──► util
 ├──► ui ──► constants
 └──► progress
```

`runtime` is the shared mutable hub. `gui.py` is the only tkinter module. Keep new code in the module matching its responsibility rather than growing `gui.py` or `app.py`.

---

## B5. Data contracts

### B5.1 Config file

Path: `HERE / "mania_dl_config.json"`

- JSON object, UTF-8, plaintext `client_secret` (gitignored; never commit, paste, or document it).
- `load_saved()` returns `{}` on missing/invalid/read error.
- `save_saved()` uses atomic temp-file replace, then `chmod(0o600)` (effectively a no-op on Windows).
- Environment variables `OSU_CLIENT_ID` / `OSU_CLIENT_SECRET` override saved values when the GUI loads.
- On `Start`, the displayed credential values are written back to config, **including environment-provided values**. That is current behavior and a privacy trap (fixed in Phase 7).

Persisted raw keys:

```text
client_id, client_secret,
out, statuses, keys, min_sr, max_sr, min_favs, sort, limit, workers, batch,
advanced, query, title, artist, creator, source, exclude, genre, language,
bpm_range, length_range, notes_range, min_plays, ranked_range, include_nsfw
```

Migration (`migrate_saved`):

- Drops retired `safe_mode` and `slide_window`.
- Fills every `NEW_SETTING_KEYS` entry from `NEW_DEFAULTS` if missing.
- Preserves existing values.
- The migration is saved on startup only if credentials exist.
- `SETTING_KEYS` (the legacy ten: `out, statuses, keys, min_sr, max_sr, min_favs, sort, limit, workers, batch`) exists in constants but is **unused** by current code. The older maintainer notes call it a "reuse gate"; the code does not implement one (see A5).

### B5.2 Derived config (`cfg_from_raw`)

The GUI collects raw strings/bools, then produces a typed-ish dict consumed by the core.

| Field | Rule |
|---|---|
| `out` | `~` expansion; default `HERE/downloads` |
| `statuses` | comma-separated; empty/`any` → `["any"]`; invalid status raises |
| `keys` | `all`/blank → `None`; integers 1–18; invalid raises |
| `min_sr` | `>= 0` |
| `max_sr` | `>= min_sr` |
| `min_favs` | clamped to `>= 0` |
| `sort` | must be one of `SORTS`, else first sort |
| `limit` | clamped to `>= 1` |
| `workers` | clamped 1–32 |
| `batch` | clamped `>= 1` |
| `advanced` | bool |
| `bpm_range` | parser accepts pairs/operators/single; bounds 0–1000 |
| `length_range` | 0–86400 seconds |
| `notes_range` | 0–10,000,000 |
| `ranked_range` | date parser; normalized `YYYY`, `YYYY-MM`, `YYYY-MM-DD` |

When `advanced` is false: all advanced text filters are forced empty/default; `exclude`, `genre`, `language` become `[]`; BPM/length/notes become sentinel full ranges; `min_plays = 0`, ranked dates empty, `include_nsfw = false`.

Derived keys added to cfg: `genre_ids, language_ids, query_terms, allowed_statuses, min_bpm, max_bpm, min_length, max_length, min_notes, max_notes, ranked_after, ranked_before, include_nsfw, min_plays`. Sentinels: `MAX_BPM = 9999`, `MAX_LENGTH = 10**9`, `MAX_NOTES = 10**9`.

### B5.3 `status.json`

Path: `<out>/status.json`, version 2.

```json
{
  "version": 2,
  "updated": "YYYY-MM-DDTHH:MM:SS",
  "downloaded": { "123": "YYYY-MM-DDTHH:MM:SS" },
  "failed": [456],
  "titles": { "456": "Set title" }
}
```

Rules:

- `downloaded` keys are string set IDs, values are local timestamps.
- `failed` is a sorted unique integer list.
- `titles` is retained **only for failed IDs**.
- `updated` is local time, no timezone.
- Saves are batched: every 8 dirty notes (`SAVE_EVERY`) or 5 seconds (`SAVE_INTERVAL`). `flush()` forces a save.
- Writes are atomic: `<name>.tmp` then `os.replace`. Nothing but `Status.save()` writes this file.
- Version 1 is read and upgraded on load. Older builds ignore the extra `titles` key.
- Invalid JSON is logged and rebuilt on the next save.
- Legacy `downloaded_ids.txt` / `failed.txt` are imported once (only when `status.json` is absent) and then deleted. If `status.json` exists, stale legacy text files are deleted.
- `scan_existing()` reads `NNN*.osz` and does **not** write those IDs into `status.json`.
- `prune_failed(present_ids)` removes failures that are now on disk.

Folder contract:

> The download folder contains `.osz` files and exactly one `status.json`.
> No reports, no `.part` after a normal run, no extra state files.

Stale `failed_links.txt` files from older builds are deleted on the next run.

### B5.4 Search result DTO

The API response is consumed as an untyped dict. Fields used:

Set level: `id, title, title_unicode, artist, artist_unicode, creator, source, tags, status, favourite_count, play_count, nsfw, bpm, genre_id, language_id, ranked_date, beatmaps[]`

Beatmap level: `mode_int, cs, difficulty_rating, count_circles, count_sliders, count_spinners, total_length, version`

`mode_int == 3` means osu!mania. Results carry `genre_id`/`language_id`, **not** name objects.

### B5.5 Progress contract

`TaskBoard` snapshot:

```json
{
  "message": "Searching...",
  "tasks": [
    { "id": 1, "description": "123 Title", "completed": 0.0, "total": 12345.0 }
  ]
}
```

- `add_task(description, total)` returns an integer ID.
- `update(id, completed=, total=, advance=, description=)`; `remove_task(id)`; `set_message(text)`.
- The downloader relies only on `add_task` / `update` / `remove_task` (a rich-Progress-compatible subset).
- The UI polls the snapshot every 120 ms. `StatusSink` adapts a TaskBoard to `update(text)` for search status.

### B5.6 Log contract

`runtime.log(message)`: prefixes local `%H:%M:%S` and two spaces; strips rich-style tags such as `[yellow]`, `[/]`; appends to a 500-line deque; invokes the registered listener from the worker thread.

The GUI reclassifies plain lines by substring:

| Pattern | Tag/color |
|---|---|
| `" via "`, `" + "` | green |
| `" x "`, `"gave up"`, `"Stopping"` | red |
| `"!"`, `"cooling"`, `"(try "` | yellow |
| `"…"`, `"already on disk"` | muted |

This string protocol is brittle; the port replaces it with structured levels.

---

## B6. End-to-end control flow

### B6.1 Startup

1. `maniadl.py` calls `gui.main()`.
2. `main` enables Windows DPI awareness (`SetProcessDpiAwareness(1)`), then constructs `ManiaDLApp`.
3. `ManiaDLApp.__init__`: loads config; migrates saved keys; saves migration only if credentials exist; creates log/event queues and two `TaskBoard`s; builds theme and layout; loads settings into widgets; syncs advanced-filter enabled state; registers the log listener; binds close/wheel handlers; schedules `_tick` after 120 ms; schedules dark title bar after 80 ms; logs `"ManiaDL ready."`.

### B6.2 Start

1. `_collect_raw()` reads all widgets into a raw dict.
2. `config.cfg_from_raw(raw)` validates and derives cfg.
3. Credentials are required; client ID must be digits.
4. Raw config + credentials are saved.
5. UI resets log, failed tree, stats cards, progress bar, summary.
6. State chip becomes "Running"; Start disabled, Stop enabled.
7. Worker thread starts with `asyncio.run(app.run(cfg, cid, secret, progress, overall))`.

### B6.3 Authentication

`api.get_token`: POST to `TOKEN_URL`; JSON body `client_id` (int), `client_secret`, `grant_type=client_credentials`, `scope=public`.

- 200 → `access_token`.
- 400/401 → remove saved credentials if present, log key guide, fatal `SystemExit`.
- 429/5xx → wait `Retry-After` (default 15 s), retry up to 3 attempts.
- other statuses → fatal, keep credentials.

### B6.4 Search

1. `api.search_sets` builds combinations: for each user status → API statuses; for each key count → key or `None`.
2. One shared `SearchPacer` is used across all combinations.
3. `search_one` cursor-paginates `GET /beatmapsets/search`: `m=3`, `sort`, `nsfw`, `q`, optional `g`/`l`, optional `s`, `cursor_string`; 50 sets per page; stops at `limit`, no cursor, repeated cursor, empty page, stop request, or 1000 pages.
4. Each set goes through `api.qualifies()`.
5. On HTTP 400: retry with minimal query (free text + `keys=N`, keeping non-query params); if still rejected, retry with no `q`.
6. Final list is `found.values()` truncated to `limit` (insertion order).

### B6.5 Dedup

```python
existing = scan_existing(out) | status.ids
status.prune_failed(existing)
todo = [s for s in sets if s["id"] not in existing]
```

- Sets recorded in `status.json` are skipped **even if their `.osz` was later removed**.
- `limit` caps total matches; already-downloaded sets are filtered out *after* the search, so raising `limit` is how you reach further into results.
- `status.failed` is only a failure ledger, not a retry queue: failed sets are retried only if the search returns them again.

### B6.6 Download

`app._run_downloads`:

1. Create overall task `"all"` with total `len(todo)`.
2. Create `asyncio.Semaphore(workers)`.
3. Split `todo` into batches of `batch`.
4. For each batch: check stop and free disk; `asyncio.gather` all set downloads; flush status; check stop; sleep `max(3, workers * 0.5) + random(0, 1)` seconds; if `runtime.mirrors_exhausted`, stop.
5. Finally: delete all `*.part`, flush status.

Per set, `mirrors.download_set`:

1. Acquire worker semaphore.
2. Add progress task.
3. If destination exists and is a valid `.osz`, record success and return.
4. Up to 6 attempts: stop check; free disk check; choose mirror; fetch to `.part`; validate `.osz`; atomically replace `.part` with `<id>.osz`; record success.
5. On rate limit: park whole host, keep `.part` for retry.
6. On mirror miss (401/403/404/451): mark mirror tried, reset progress, try another.
7. On transient error/timeout/IO: backoff, retry.
8. On stop: return without recording failure.
9. After retries: mark failed, store title, log manual osu! link.
10. Finally: decrement active, remove task, advance overall.

### B6.7 Completion

Worker posts `("done", result)` or `("error", message)`. `_on_done`:

- re-enables Start; refreshes stats once; sets state chip Done/Stopped;
- fills summary rows via `ui.search_rows`;
- fills Failed downloads tree via `reports.failed_entries`;
- chooses footer message based on stopped / no todo / new failures / old failures / clean success;
- handles `mirrors_exhausted` with a "Paused safely" state.

### B6.8 Stop and close

- Stop sets `runtime._stop`. Downloads finish current chunk/file; batches stop between sets. Sets not started stay queued for the next run.
- `.part` files are cleaned at batch-run end.
- Close with a run active asks for confirmation, requests stop, polls until idle, then destroys.
- No force-cancel of in-flight HTTP requests.
- Fatal auth/search errors (`SystemExit`) are surfaced by the worker as an error dialog.

---

## B7. Search subsystem details

### B7.1 Server-side vs client-side

Server-side: mode `m=3`, sort, NSFW, free-text/query terms, genre `g` only when exactly one ID resolved, language `l` only when exactly one ID resolved, API status `s`, and ranking/favourites/BPM/length/key constraints embedded in the `q` string.

Client-side authoritative filters in `qualifies()`, in order:

1. status allowed; 2. favourites minimum; 3. play count minimum; 4. NSFW; 5. query terms; 6. exclude terms; 7. title/artist/creator/source contains; 8. genre IDs; 9. language IDs; 10. BPM; 11. ranked date range; 12. any mania difficulty satisfying key count, star rating, note count and length.

A set passes if **at least one** mania beatmap passes the per-difficulty checks. Length is checked per matching difficulty; BPM, genre, language, ranked date and favourites are set-level. Notes and play count have no server-side filter, so those filters can scan many pages when set narrowly.

### B7.2 Text matching

`_haystack` lowercases and joins: title + title_unicode, artist + artist_unicode, creator, source, tags, and every beatmap `version`.

`simple_query_terms` returns `[]` if the query contains an osu! operator such as `stars>=`, `keys:`, `title=`; those queries are left to the API to avoid false negatives. Plain-text queries are additionally checked client-side.

### B7.3 Pacing and retries

`SearchPacer`: base `SEARCH_INTERVAL` (≈1.05 s, ~60 requests/minute as osu! requests); jitter up to 8%; gap measured from **request start**, not response completion; serialized by an async lock; `success()` decays interval by 10% toward base; `penalise(seconds)` doubles interval (at least `seconds`), caps at 30 s, and parks `_next`.

Search retries: 5 attempts with exponential backoff + jitter, capped 30 s.

429 handling: no inline `sleep`; the pacer's next wait performs the delay. This is deliberate.

### B7.4 Query grammar

`build_query` appends: free text, title, artist, creator, source, `keys=N`, `stars>=x`, `stars<=x`, `bpm>=x`, `bpm<=x`, `length>=x`, `length<=x`, `favourites>=x`, `ranked>=date`, `ranked<=date`. Double quotes are stripped and whitespace collapsed. `minimal_query` contains only free text and `keys=N`.

---

## B8. Download subsystem details

### B8.1 Mirrors

```text
nerinyan     https://api.nerinyan.moe/d/{id}
nekoha       https://mirror.nekoha.moe/api/download/{id}
catboy       https://catboy.best/d/{id}n
beatconnect  https://beatconnect.io/b/{id}/
osu.direct   https://osu.direct/api/d/{id}
sayobot      https://dl.sayobot.cn/beatmaps/download/full/{id}
catboy-video https://catboy.best/d/{id}
```

`catboy` and `catboy-video` share a host, so parking one parks both. Mirrors change or die often; the list needs manual maintenance.

### B8.2 Selection

`choose_mirror(attempt, tried)`: excludes mirrors whose `until` is in the future; if all are cooling, returns `(None, soonest_wait)`; excludes already-tried mirrors for this set; ranks by (1) inflight requests on that host, (2) failure streak, (3) last-used time, (4) successful downloads, (5) random tie-break. The `attempt` parameter is currently unused.

### B8.3 Host limiting

Per host: minimum start spacing `0.9 s` × random 0.85–1.15; concurrency cap 2; inflight counter; state created lazily in `runtime.host_state`.

429 parks the entire host for `clamp(Retry-After, 30, 300)` plus 0–5 s jitter. All mirrors parked → `runtime.mirrors_exhausted = True` → run stops after the current batch. This is intentional: sleep-and-retry on 429 is how the IP gets banned.

Request pacing is internal and always on (per-host spacing, per-host concurrency cap, jittered backoff, `Retry-After` respect). It is **not** a user-facing setting; no controls or warnings for it.

### B8.4 Transfer

`fetch()`:

- Browser UA (`BROWSER_HEADERS`) + `Referer: scheme://host/` (mirror downloads only).
- `Range: bytes=<existing>-` if a `.part` exists.
- 429 → `RateLimited`; 401/403/404/451 → `MirrorMiss`; 416 → delete part, transient error; only 200/206 accepted.
- 206 validates `Content-Range` start equals existing bytes; 200 with existing part restarts from zero and truncates.
- Streams 128 KiB chunks; checks stop each chunk; counts bytes; verifies received length against total; rejects empty bodies.

### B8.5 Retry semantics

- 6 attempts per set.
- Mirror miss excludes that mirror for the set.
- Rate limit parks host, keeps `.part`.
- Transient errors back off `min(2^attempt + jitter, 45) * 1.25`; payload errors at least 10 s.
- Low disk logs and stops the set; because the loop breaks without stop, the set is then marked failed.
- Stop abandons without recording failure.
- `.part` is deleted at the end of `_run_downloads` (and on startup), so Range resume is effectively **within one run only**, not across restarts. `.part` files are safe to delete and must never be renamed to `.osz`.

### B8.6 Validation

`valid_osz`: file exists; size ≥ 22 bytes; ZIP archive opens; at least one entry name ends with `.osu`, case-insensitive. It does not validate `.osu` content.

---

## B9. Persistence and filesystem behavior

Output folder lifecycle:

1. `mkdir -p`.
2. Delete all `*.part`.
3. Delete stale `failed_links.txt`.
4. Load `status.json`; migrate v1/legacy if needed.
5. Scan existing `.osz` files.
6. Download to `<id>.part`.
7. Validate.
8. `os.replace` to `<id>.osz`.
9. Update status.
10. Flush per batch and at end.
11. Delete leftover `*.part` at run end.

`scan_existing` regex: `^(\d+)(?:[ .]|$)` with suffix `.osz`. So `123.osz` and `123 Title.osz` count; `123.part` and `notanid.osz` do not. Deleting/relocating `status.json` or changing `out` re-downloads everything not still on disk as `NNN*.osz`.

Disk check: `free_gb(path)` caches for 3 s; walks up until an existing parent; `shutil.disk_usage(...).free / 1e9`; threshold `MIN_FREE_GB = 5.0`.

Atomic writes: write `<name>.tmp` then `os.replace(<name>.tmp, <name>)`. No cross-volume handling.

Out of scope: importing into osu!lazer, writing into the osu! `Songs/` folder, extra report files.

---

## B10. UI behavior to reproduce

(tkinter-specific details such as ttk `clam` styling and the mouse-wheel guard disappear in a web UI; the behaviors remain.)

### B10.1 Layout

Window defaults 1200×820, min 1000×680. Per the original brief: **left panel has all settings; right panel has all status.**

```text
Header: title + subtitle
Main split:
  Left: scrollable settings panel (440 px)
    - osu! API  (with "How to get keys" link → https://osu.ppy.sh/home/account/edit)
    - Download folder
    - Filters
    - Download behaviour
    - Advanced filters
  Right:
    - Run status card + state chip
    - Overall progress card
    - 6 stat cards: downloaded, failed, active, data, speed, free disk
    - Active downloads table
    - Tabs: Log, Failed downloads
Footer: status text + Stop + Start
```

### B10.2 Settings panel behaviors

- Advanced fields are disabled unless "Enable advanced filters" is checked.
- Reset restores `NEW_DEFAULTS`.
- Status checkboxes: "Any" clears others; selecting a real status clears "Any"; if none remain, Ranked is restored.
- Credentials field loads env values over saved values.

### B10.3 Theme

```text
BG #111318, PANEL #191c23, PANEL_ALT #232834,
FG #e5e9f0, MUTED #8f98a8, ACCENT #7aa2f7,
GREEN #9ece6a, RED #f7768e, YELLOW #e0af68,
BORDER #2b303b, FIELD #1e222b
```

Windows-specific: DPI awareness at process start; dark title bar via `DwmSetWindowAttribute` attributes 20/19.

### B10.4 Threading rule

Only the UI thread touches widgets. Worker code may call `runtime.log()`, mutate `TaskBoard`, put events on queues, and read stats.

### B10.5 Polling and live values

Every 120 ms: drain logs, drain events, and (if running) refresh live values: overall task → percentage and label; active transfers → table rows; stats → downloaded/failed/active/data/speed/free; current status message. Speed is average bytes/sec over the run, not instantaneous.

### B10.6 Log and failed tabs

Log: read-only, monospace (Consolas 9), colored by level, capped at 3000 displayed lines.

Failed downloads: ID + title rows; double-click or button opens the osu! page; "Copy links" copies plain text for selected or all failures. No failed-link file is written. Previous failures are not loaded on startup; they appear only after a completed run.

The README also advertises "mirror health" in the live status panel; the current `main` UI described above has no dedicated mirror-health view (see A5).

---

## B11. Filtering and parsing semantics

### B11.1 Range parser

```text
"" / any / all / *        -> (None, None)
150-220 / 150..220 / 150 to 220 / 150,220
>=150 / <=220 / >150 / <220
=180 / 180
```

Inverted range raises; optional minimum/maximum bounds; integer casts round.

### B11.2 Date parser

```text
"" / any / all / *
2020
2020-1
2020/01/02
2020..2024
2020-01-01..2024-12-31
>=2020 / <=2024
```

Separators `/` and `.` become `-`; month/day are zero-padded; inverted range raises. Comparison in `qualifies()` is lexicographic prefix comparison on `ranked_date`. `=` maps to an upper bound, not an exact date.

### B11.3 Status and keys

- Statuses: `graveyard`, `ranked`, `loved`, `qualified`, `pending`, `any`.
- Client-side `ranked` means `ranked` + `approved` (`STATUS_SETS`). API-side `pending` means `pending` + `wip` (`API_STATUSES`).
- Keys: `all`/blank/any → no key filter; otherwise 1–18.

### B11.4 Genre and language

Fixed dictionaries `GENRE_IDS` / `LANGUAGE_IDS` mirror osu!'s taxonomy. UI terms are lowercased, comma/semicolon-separated; partial names match by substring (`term in name`); multiple matches produce multiple IDs; server-side `g`/`l` sent only when exactly one ID resolves; unknown term raises a config error.

### B11.5 Advanced gate

`advanced = false` means all advanced filters are ignored. The GUI auto-enables advanced on load if any saved advanced text field is non-empty, or `min_plays > 0`, or `include_nsfw` is true. `include_nsfw` is only honored when advanced is enabled. NSFW is excluded by default.

---

## B12. Error and cancellation model

| Type | Origin | Meaning | Handling |
|---|---|---|---|
| `SystemExit` | API auth/search | Fatal user-facing failure | Worker posts `error`, UI shows error |
| `SearchRejected` | HTTP 400 | Query rejected | Fallback search with fewer filters |
| `MirrorMiss` | 401/403/404/451 | Mirror lacks set | Try another mirror |
| `RateLimited` | 429 | Host rate-limited | Park host, no inline retry |
| `Stopped` | User stop | Abandon transfer | No failure recorded |
| `aiohttp.ClientError` | network/HTTP | Transient | Backoff/retry |
| `asyncio.TimeoutError` | timeout | Transient | Backoff/retry |
| `ValueError` | bad `.osz` / parse | Set-level failure | Retry another mirror |
| `OSError` | disk/I/O | Transient or low disk | Retry or stop |
| `zipfile.BadZipFile` | invalid `.osz` | Invalid download | Retry |

Stop is cooperative: checked between batches, inside `download_set`, inside search pagination, and inside every chunk write. In-flight transfers are not forcibly cancelled; a stop is noticed at the next chunk boundary.

---

## B13. Existing Python test architecture

- stdlib `unittest` + `IsolatedAsyncioTestCase`, no network, no Tk window. `tests/fakes.py` provides `FakeResponse`, `FakeContent`, `FakeSession`, `FakeProgress`, `FakeOverall`, `FakeSpinner`, `make_osz_bytes`.
- Run: `uv run python -m unittest discover -s tests -t . -v`.
- 87 tests covering: query construction and params; client-side qualification; pagination, 400 fallback, 429 retry; pacer behavior; full app orchestration with fake session; mirror fetch, resume, rate limit, miss, stop, bad Content-Range; mirror choice and host parking; status migration, batching, pruning, scanning; config defaults, advanced parsing, validation, migration; UI label helpers; util parsers, `.osz` validation, Retry-After, links, disk free.
- Gaps: no GUI interaction tests; no live API/mirror tests (mirror/Cloudflare behavior needs a manual run with valid credentials); no test of the exact `status.json` byte format; no concurrency stress test; no test that `.part` cleanup/resume across runs behaves as documented.
- No lint/format/typecheck is configured. No git hooks.

## B14. Build and release (Python, for reference)

```text
uv sync
uv run maniadl.py
uv sync --extra build
uv run --extra build pyinstaller --onefile --windowed --name ManiaDL maniadl.py
```

`pyproject.toml`: `maniadl` 2.0.0, Python >=3.10, `aiohttp>=3.9`, build extra `pyinstaller>=6.0`. The exe lands in `dist/ManiaDL.exe`. Release: tag `v2.0.0` publishes `ManiaDL.exe` on GitHub.

---

## B15. Latent risks and invariants

### Risks / traps

1. **C# concurrency:** `runtime.stats`, `mstats`, `host_state` are not thread-safe in a multi-threaded runtime. Python's event loop made this benign; C# needs locks, `Interlocked`, or concurrent collections.
2. **Pacing:** never replace start-based pacing with post-response sleeps. Never inline-retry mirror 429s.
3. **Resume:** `.part` cleanup at run end means cross-run resume is not real. Preserve it or fix it deliberately.
4. **Credential leak:** environment credentials are copied into plaintext config on Start.
5. **Portable-path assumption:** config/status beside the executable fails under `Program Files` permissions.
6. **Unknown config keys:** a typed config serializer can silently drop keys Python would preserve.
7. **`SETTING_KEYS`:** constants suggest a reuse gate the code does not implement.
8. **Failed-set retry:** "they'll be retried" is only true if search returns them again.
9. **Ordering:** `found` is an insertion-ordered dict; C# must preserve first-seen order intentionally.
10. **Date comparisons:** lexicographic prefix comparison, not real date arithmetic.
11. **`=` in date parser:** maps to an upper bound, not an exact date.
12. **Stats semantics:** a valid `.osz` already on disk counts as success in status but does not increment `stats["ok"]`.
13. **Low disk:** can mark the current set failed rather than leaving it queued.
14. **UI log colors:** substring-based and easy to break.
15. **Failed tree:** previous failures are not loaded on startup.
16. **Mirror availability:** endpoints change/die; list needs maintenance.
17. **`valid_osz`:** checks only for a `.osu` entry, not content validity.
18. **Realm/lazer detection:** not present on `main`; if reintroduced, raw `client.realm` reading is heuristic and must handle file locks.

### Invariants to preserve

- Only `.osz` + `status.json` in the download folder.
- Same config and status file names/shapes for user migration.
- Atomic status writes and batched saves.
- No browser UA/headers on the osu! API (use `API_UA`, never `BROWSER_HEADERS`); browser UA + mirror `Referer` for mirror downloads (Cloudflare 403s otherwise).
- ~60 osu! requests/minute with adaptive backoff.
- Per-host mirror spacing/concurrency and host-wide 429 parking.
- Request pacing is internal, always on, not a user setting.
- Client-side `qualifies()` is authoritative.
- Search fallback on HTTP 400.
- Cooperative stop; queued sets remain queued.
- No extra output/report files; failures belong in the GUI.
- Failed sets remain visible with direct links.

---

## B16. Maintainer notes carried over (originally AGENTS.md)

- Purpose: "download hundreds of mania maps matching my taste" without a browser, for the author's own osu!lazer library, Windows-first. Personal tool; docs are the source of truth.
- `HERE` semantics matter: keep config/state beside the exe/script; do not switch to `__file__`-style paths unguarded. A `--onefile` exe unpacks to a temp dir; use the real exe directory.
- Advanced filters are applied twice: server-side `q` (plus `g`/`l` for a single resolved genre/language) narrows the search; `qualifies()` is authoritative. If osu! rejects the query (HTTP 400) the search falls back to fewer server-side filters automatically.
- The UI accepts partial genre/language names; they map via `GENRE_IDS`/`LANGUAGE_IDS`.
- Tk-only concerns (not applicable to the web UI): widgets from the Tk thread only; `_wheel_safe()` for comboboxes/spinboxes/scales.
- Commit history uses short imperative subjects.
- Secrets: never commit, paste, or document `mania_dl_config.json` contents; env vars are preferred on shared machines.

---

# PART C: Rewrite guide

Audience: the coding agent doing the port.

**Prime directive:** port behavior first, fix things second. Phases 0–6 are a behavior-preserving port. Phase 7 holds the deliberate improvements. Phase 8 handles repo, CI, docs and retiring Python. Do not mix them. Read Part A (especially A4 and A6) before starting.

---

## C0. Decisions (do not relitigate)

| Topic | Decision |
|---|---|
| Target | `net8.0-windows`, C# 12, nullable enabled, warnings as errors |
| UI | Web frontend (**React 18 + Vite + TypeScript strict**, plain CSS variables, no component library) rendered in **WebView2**. Chosen so the agent can drive and screenshot the real UI. |
| Host | Minimal **WinForms** window containing one `WebView2` control (`Microsoft.Web.WebView2`). The host owns no business logic. |
| Bridge | `window.chrome.webview.postMessage` (UI → host) and `CoreWebView2.PostWebMessageAsJson` (host → UI). JSON, camelCase, versioned. See Phase 6. |
| Agent UI testing | Playwright `chromium.connectOverCDP` against the real app, enabled only by a `--debug-port` flag. A `--fake-engine` flag gives deterministic runs. |
| HTTP | One `HttpClient` per run via `SocketsHttpHandler`. No Polly. Retry/pacing logic is bespoke and must stay explicit. |
| JSON | `System.Text.Json` only. |
| Tests | xUnit + temp dirs + fake `HttpMessageHandler` + `TimeProvider` for Core; Playwright (`@playwright/test`) for UI e2e; Vitest optional for frontend reducers |
| Packaging | `dotnet publish -c Release -r win-x64 --self-contained -p:PublishSingleFile=true`. Do not use trimming (reflection-based JSON). The built frontend (`ui/dist`) is embedded as resources in the host so the exe stays a single file. WebView2 Evergreen runtime is assumed present; detect and show a clear message if not. |
| Global state | None. Everything lives in a per-run `RunContext` passed by constructor. |
| Config/status filenames | Unchanged: `mania_dl_config.json`, `<out>/status.json`. Users must migrate without noticing. |
| Folder contract | Download folder holds only `.osz` + `status.json` **[B5.3]**. |

---

## C1. Solution layout

```text
ManiaDL.sln
src/
  ManiaDL.Core/                 net8.0, no UI refs
    Constants/                  Mirrors.cs, ApiConstants.cs, Defaults.cs, Lookups.cs (genre/lang/status)
    Parsing/                    RangeParser.cs, DateRangeParser.cs, StatusParser.cs, KeyParser.cs
    Config/                     RawConfig.cs, AppConfig.cs, ConfigStore.cs, ConfigValidator.cs
    Api/                        OsuApiClient.cs, SearchPacer.cs, QueryBuilder.cs, Qualifier.cs, Beatmapset.cs
    Mirrors/                    MirrorScheduler.cs, HostGate.cs, MirrorClient.cs, DownloadService.cs, Exceptions.cs
    State/                      StatusStore.cs, FolderScanner.cs
    Run/                        RunContext.cs, RunStats.cs, DownloadOrchestrator.cs, RunResult.cs
    Progress/                   TaskBoard.cs, ProgressSnapshot.cs
    Logging/                    LogEntry.cs, LogLevel.cs, RunLog.cs
    Util/                       OszValidator.cs, AtomicFile.cs, DiskSpace.cs, RetryAfter.cs, Links.cs
  ManiaDL.Host/                 net8.0-windows, WinForms + WebView2, bridge, embedded ui/dist
ui/                             React + Vite + TS frontend
  src/{bridge,state,components,styles}/
  e2e/                          Playwright specs + artifacts/ (screenshots)
scripts/
  e2e.ps1                       build ui + host, launch with flags, run Playwright, kill app
tests/
  ManiaDL.Core.Tests/
  Fixtures/                     golden JSON, sample API responses, tiny .osz builder
  Fixtures/protocol/            golden bridge messages shared by C# and frontend tests
```

Rule: `ManiaDL.Core` must never reference WinForms, WebView2 or any UI type. `ManiaDL.Host` is the only project that knows about the window and the bridge. The frontend is the only place that knows about the DOM.

---

## C2. Core types (write these first)

### C2.1 Config

Two layers: `RawConfig` (what the GUI edits and the file stores, mostly strings) and `AppConfig` (validated, typed, immutable).

```csharp
public sealed class RawConfig
{
    public string ClientId { get; set; } = "";
    public string ClientSecret { get; set; } = "";
    public string Out { get; set; } = "";
    public string Statuses { get; set; } = "ranked";
    public string Keys { get; set; } = "all";
    public string MinSr { get; set; } = "0";   // keep as string-or-number tolerant, see below
    // ... one property per persisted key in [B5.1]
    public bool Advanced { get; set; }
    public bool IncludeNsfw { get; set; }

    // CRITICAL: preserve unknown keys across load/save [B15 risk 6]
    [JsonExtensionData] public Dictionary<string, JsonElement>? Extra { get; set; }
}
```

Requirements:

- JSON names must be the exact snake_case keys from **[B5.1]**: use `[JsonPropertyName("client_id")]` etc. (or a snake_case naming policy and a test asserting every key).
- Numeric fields (`min_sr`, `workers`, …) may be stored by Python as numbers or strings. Use a lenient converter that accepts both.
- `ConfigStore.Load()` returns an empty `RawConfig` on missing/invalid/IO error, never throws.
- `ConfigStore.Save()` is atomic (`.tmp` then `File.Move(overwrite: true)`).
- Migration: drop `safe_mode` and `slide_window`; fill missing keys from defaults; keep existing values.
- `ConfigValidator.Build(RawConfig) -> AppConfig` implements the table in **[B5.2]** exactly. Throw `ConfigException` (user-facing message) on invalid status/keys/ranges/genre/language.

`AppConfig` must be a `record` with real types: `IReadOnlySet<string> AllowedStatuses`, `int? Keys`, `double MinSr`, `RangeD Bpm`, `DateBound? RankedAfter`, etc. Use the sentinels `MAX_BPM=9999`, `MAX_LENGTH=MAX_NOTES=1_000_000_000` only if it keeps `Qualifier` identical to Python; otherwise use `int?` open-ended bounds, **but** add tests proving equivalent results.

Advanced gate **[B11.5]**: when `Advanced == false`, the validator forces every advanced field to its neutral value (including `IncludeNsfw=false`, `MinPlays=0`).

### C2.2 RunContext (replaces `runtime.py`)

```csharp
public sealed class RunContext
{
    public required CancellationTokenSource Stop { get; init; }
    public RunStats Stats { get; } = new();
    public MirrorStats Mirrors { get; } = new();          // thread-safe
    public HostGates Hosts { get; } = new();              // thread-safe
    public TaskBoard Progress { get; } = new();
    public RunLog Log { get; } = new();
    public TimeProvider Time { get; init; } = TimeProvider.System;
    public Random Rng { get; init; } = Random.Shared;
    public volatile bool MirrorsExhausted;
}

public sealed class RunStats   // Interlocked only
{
    long _ok, _fail, _active, _bytes;
    public void AddOk() => Interlocked.Increment(ref _ok);
    public void AddFail() => Interlocked.Increment(ref _fail);
    public void AddActive(int d) => Interlocked.Add(ref _active, d);
    public void AddBytes(long n) => Interlocked.Add(ref _bytes, n);
    public StatsSnapshot Snapshot() => new(Volatile.Read(ref _ok), /* … */);
}
```

A new `RunContext` is created per Start press. Nothing static, nothing mutable at class level.

### C2.3 Logging (structured, not string-parsed)

```csharp
public enum LogLevel { Info, Success, Warning, Error, Muted }
public readonly record struct LogEntry(DateTimeOffset Time, LogLevel Level, string Message);
```

- `RunLog` wraps a `Channel<LogEntry>` (unbounded, single reader = UI) and keeps a 500-line ring for any late subscriber.
- Message format shown to the user: `HH:mm:ss  message` (local time, two spaces) **[B5.6]**. Format in the view, not in the log.
- Replace the substring heuristics **[B5.6]** with explicit levels at each call site:
  - `" via "`, `" + "` → `Success`
  - `" x "`, `"gave up"`, `"Stopping"` → `Error`
  - `"!"`, `"cooling"`, `"(try "` → `Warning`
  - `"…"`, `"already on disk"` → `Muted`
- No rich-markup tags anywhere.
- UI log view caps at 3000 lines.

### C2.4 Progress

`TaskBoard` with a lock; methods `AddTask(desc, total) -> int`, `Update(id, completed?, total?, advance?, description?)`, `RemoveTask(id)`, `SetMessage(text)`, `Snapshot()` returning immutable `ProgressSnapshot(string Message, IReadOnlyList<TaskItem> Tasks)` **[B5.5]**. The engine (Phase 6) coalesces snapshots into a `progress` event at most every 120 ms while a run is active.

---

## C3. Phased plan

Each phase ends with green tests. Do not start the next phase until the current one passes.

### Phase 0: Walking skeleton (prove the agent's UI test loop first)

Do this before porting anything. If this loop does not work, nothing else matters.

1. `ManiaDL.Host`: WinForms window with one `WebView2` control showing a static "hello" page from the embedded `ui/dist`.
2. Launch flag `--debug-port 9222` sets `CoreWebView2EnvironmentOptions.AdditionalBrowserArguments = "--remote-debugging-port=9222"` **before** `CoreWebView2Environment.CreateAsync` (env var `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` is the fallback). Without the flag the port must not open.
3. `ui/e2e/smoke.spec.ts`: `chromium.connectOverCDP("http://127.0.0.1:9222")`, take `browser.contexts()[0].pages()[0]`, assert the hello text, click a button that round-trips through the bridge (JS `postMessage` → C# → `PostWebMessageAsJson` → DOM change), save a screenshot to `ui/e2e/artifacts/`.
4. `scripts/e2e.ps1` does everything non-interactively: build UI, build host, launch with flags, poll `http://127.0.0.1:9222/json/version` until ready, run Playwright, kill the app (even on failure).

Exit criteria: from a clean checkout, one command passes and leaves a screenshot. Add `--data-dir <path>` now too (WebView2 user data folder + isolated config/status for tests; default `%LOCALAPPDATA%\ManiaDL\WebView2` for the webview cache).

### Phase 1: Pure helpers and parsing

Port `util.py`, `constants.py`, `ui.py`, and the parsing half of `config.py`.

- `RangeParser`: all forms in **[B11.1]**. Inverted range throws. Integer casts **round** (Python `round`: banker's rounding; use `Math.Round(x, MidpointRounding.ToEven)` and test `.5` cases).
- `DateRangeParser`: **[B11.2]**. Normalize to `YYYY`, `YYYY-MM`, `YYYY-MM-DD`. `=` maps to an upper bound (known quirk **[B15 risk 11]**), so preserve it.
- `StatusParser`: statuses `graveyard, ranked, loved, qualified, pending, any`. Client-side `ranked` ⇒ `ranked`+`approved`. API-side `pending` ⇒ `pending`+`wip`.
- `OszValidator.IsValid(path)`: exists, size ≥ 22, opens as zip (`System.IO.Compression.ZipFile.OpenRead`), has ≥1 entry ending in `.osu` (case-insensitive). Catch `InvalidDataException`.
- `RetryAfter.Parse`: accept delta-seconds and HTTP-date, return `double?`.
- `DiskSpace.FreeGb(path)`: cache 3 s (use `TimeProvider`), walk up to an existing parent, `DriveInfo`/`new DriveInfo(root).AvailableFreeSpace / 1e9`. Threshold `MIN_FREE_GB = 5.0`. UNC paths: fall back to `GetDiskFreeSpaceEx` or treat as unknown and skip the check, with a log line.
- `Links.Direct(id)` → `https://osu.ppy.sh/beatmapsets/{id}`.

**Port every Python test that touches these.** Translate test names 1:1 so coverage is traceable.

### Phase 2: Config + State persistence

- `ConfigStore` and `ConfigValidator` (see C2.1).
- `StatusStore` implementing **[B5.3]** exactly:
  - Model: `version=2`, `updated` (local `yyyy-MM-ddTHH:mm:ss`, no zone), `downloaded: Dictionary<string,string>`, `failed: sorted unique int list`, `titles` (**only** for failed IDs).
  - Serialize with indented JSON, UTF-8 without BOM. Check key order: `version, updated, downloaded, failed, titles`.
  - Thread-safe: one `lock` (or `SemaphoreSlim`) guarding mutation; save under snapshot.
  - Batched save: flush when 8 dirty notes **or** ≥5 s since last save; `Flush()` forces.
  - Atomic: write `status.json.tmp` then `File.Move(overwrite:true)`.
  - Load: v1 → upgrade; invalid JSON → log + start fresh, rebuild on next save; legacy `downloaded_ids.txt`/`failed.txt` imported **only** if `status.json` is absent; delete stale legacy files when `status.json` exists.
  - `PruneFailed(IReadOnlySet<int> present)`.
- `FolderScanner.ScanExisting(dir)`: regex `^(\d+)(?:[ .]|$)` on the file stem with `.osz` extension (case-insensitive extension). Does **not** write into status **[B5.3]**.

**Golden tests:** commit sample `status.json` files produced by the Python app (v1 and v2, plus legacy text files). C# must read them and re-emit v2 that Python can read back. Add a byte-level round-trip test **[B13 gap]**.

### Phase 3: Search

Port `api.py`.

**`SearchPacer`** (async, `TimeProvider`-based) **[B7.3]**:

```csharp
public sealed class SearchPacer
{
    const double Base = 1.05;
    readonly SemaphoreSlim _lock = new(1, 1);
    double _interval = Base;
    DateTimeOffset _next;                       // earliest next *start*

    public async Task WaitAsync(CancellationToken ct)
    {
        await _lock.WaitAsync(ct);
        try
        {
            var now = _time.GetUtcNow();
            if (_next > now) await Task.Delay(_next - now, _time, ct);
            // gap measured from request START, so set _next now, before the request is sent
            var jitter = 1 + _rng.NextDouble() * 0.08;
            _next = _time.GetUtcNow() + TimeSpan.FromSeconds(_interval * jitter);
        }
        finally { _lock.Release(); }
    }
    public void Success() => _interval = Math.Max(Base, _interval * 0.9);
    public void Penalise(double seconds)
    {
        _interval = Math.Min(30, Math.Max(seconds, _interval * 2));
        _next = _time.GetUtcNow() + TimeSpan.FromSeconds(_interval);   // park
    }
}
```

> **Do not** sleep after the response. **Do not** sleep inline on 429. The pacer's next `WaitAsync` does the delay. This is deliberate **[B15 risk 2]**.

Match the Python numbers exactly (verify against `api.py` when porting; the snippet above shows the shape, not the final constants).

**`OsuApiClient`:**

- `GetTokenAsync` **[B6.3]**: POST JSON `{client_id:int, client_secret, grant_type:"client_credentials", scope:"public"}`.
  - 200 → token.
  - 400/401 → raise `AuthFatalException(clearCredentials: true)`. The caller, not the API client, removes saved credentials and logs the key guide.
  - 429/5xx → wait `Retry-After` (default 15 s), 3 attempts.
  - other → `AuthFatalException(clearCredentials: false)`.
- **No browser UA or headers on osu! API calls** **[B15 invariants]**. Send `API_UA` exactly as defined in `constants.py` (Part A6) and never `BROWSER_HEADERS`; those are for mirror downloads only.
- `SearchSetsAsync(AppConfig, IProgress<string>, ct) -> IReadOnlyList<Beatmapset>`:
  - Combinations: each user status → API statuses × each key count (or `null`). One shared pacer.
  - `SearchOneAsync` cursor pagination, `m=3`, 50/page. Stop at `limit`, no cursor, repeated cursor, empty page, stop, or 1000 pages.
  - Retries: 5 attempts, exponential backoff + jitter, cap 30 s.
  - HTTP 400 → `SearchRejectedException` → retry with `MinimalQuery` (free text + `keys=N`, keep non-query params); if still rejected → retry with no `q`.
  - Result list preserves **first-seen insertion order**, deduped by ID, truncated to `limit`. Use `OrderedDictionary<int, Beatmapset>` (.NET 9) or `Dictionary` + `List<int>` order list on .NET 8. Don't rely on `Dictionary` enumeration order.
- `QueryBuilder.Build` / `MinimalQuery` / `SearchParams` **[B7.4]**. Strip `"` and collapse whitespace.

**DTOs:** use typed records with `[JsonPropertyName]` for the fields in **[B5.4]**, all nullable-tolerant. Missing/`null` fields must behave like Python's `.get(..., default)`. Unknown fields ignored.

**`Qualifier.Qualifies(Beatmapset, AppConfig)`** is authoritative **[B7.1]**. Preserve order and semantics:

1. status allowed → 2. favourites min → 3. play-count min → 4. NSFW → 5. query terms → 6. exclude terms → 7. title/artist/creator/source contains → 8. genre IDs → 9. language IDs → 10. BPM → 11. ranked date → 12. **any** mania beatmap (`mode_int == 3`) satisfying key count AND star rating AND note count (`count_circles+count_sliders+count_spinners`) AND length (`total_length`).

Details:
- Haystack = lowercased join of `title, title_unicode, artist, artist_unicode, creator, source, tags` and every beatmap `version` **[B7.2]**. Use `ToLowerInvariant`.
- `SimpleQueryTerms` returns empty if the query contains any osu! operator (`stars>=`, `keys:`, `title=` …). Port the operator regex verbatim.
- Ranked-date comparison is **lexicographic prefix** string comparison on `ranked_date`, not `DateTime` arithmetic. Use `string.CompareOrdinal`.
- Genre/language partial match: `term in name` (substring), multiple matches → multiple IDs. Server-side `g`/`l` sent only when exactly one ID.

**Tests:** replay recorded JSON pages from `Fixtures/` through a fake handler. Port the 400-fallback and 429 tests. For 429: assert **no** `Task.Delay` happens inside the request path (inject a fake `TimeProvider` and assert the next `WaitAsync` is what advances time).

### Phase 4: Mirrors and downloads

Port `mirrors.py`.

**Mirror table** **[B8.1]**, as data:

```csharp
public sealed record Mirror(string Name, string Template);   // "{id}" placeholder
static readonly Mirror[] All = {
    new("nerinyan",     "https://api.nerinyan.moe/d/{id}"),
    new("nekoha",       "https://mirror.nekoha.moe/api/download/{id}"),
    new("catboy",       "https://catboy.best/d/{id}n"),
    new("beatconnect",  "https://beatconnect.io/b/{id}/"),
    new("osu.direct",   "https://osu.direct/api/d/{id}"),
    new("sayobot",      "https://dl.sayobot.cn/beatmaps/download/full/{id}"),
    new("catboy-video", "https://catboy.best/d/{id}"),
};
```

Host key = `Uri.Host`. `catboy` and `catboy-video` share a host, so parking one parks both.

**`HostGate`** (per host, lazily created in a `ConcurrentDictionary<string, HostGate>`):
- `SemaphoreSlim(2)` concurrency cap.
- Start-spacing: `0.9 s × U(0.85, 1.15)`, serialized by an async lock, measured **from start**.
- `int Inflight` via `Interlocked`.
- `ParkedUntil` (`long` ticks, `Volatile`).

**`MirrorScheduler.Choose(tried) -> (Mirror? m, TimeSpan? soonestWait)`** **[B8.2]**:
1. exclude mirrors whose `Until > now`; if none left → `(null, soonest wait)`;
2. exclude `tried`;
3. order by: host inflight ↑, failure streak ↑, last-used ↑, ok-count ↓, random tie-break.

Drop the unused `attempt` parameter.

**429 handling:** `RateLimited` → park the **whole host** for `clamp(RetryAfter, 30, 300) + U(0,5)` s. Keep the `.part`. No inline retry. If all mirrors are parked → `ctx.MirrorsExhausted = true`.

**`MirrorClient.FetchAsync`** **[B8.4]**, in order:
- Headers: browser UA + `Referer: {scheme}://{host}/`.
- `Range: bytes={existing}-` if `.part` exists.
- Use `HttpCompletionOption.ResponseHeadersRead`; stream with a 128 KiB buffer.
- 429 → `RateLimited`; 401/403/404/451 → `MirrorMiss`; 416 → delete `.part`, throw transient; any non-200/206 → transient error.
- 206: `Content-Range` start must equal existing length, else error. 200 with existing `.part` → truncate and restart from 0.
- Check stop flag on every chunk. On stop: throw `StoppedException`.
- Verify received length vs. total when known; reject empty bodies.
- Add bytes to `Stats` as they arrive. On truncate/reset, subtract or reset the task progress consistently with Python (port that logic exactly).
- Disable automatic decompression and automatic redirects *only if* Python's `aiohttp` behavior differs; otherwise leave defaults. Check this against `mirrors.py` and note the decision in a code comment.

**`DownloadService.DownloadSetAsync`** **[B6.6]**: follow the numbered steps in order.
- Acquire worker semaphore → add progress task → if `<id>.osz` exists and valid, record success **without** incrementing `Stats.Ok` **[B15 risk 12]** and return.
- Up to 6 attempts: stop check → disk check → choose mirror → fetch to `<id>.part` → validate → `File.Move(part, osz, overwrite:true)` → record success.
- Backoff on transient: `min(2^attempt + jitter, 45) × 1.25`; payload errors minimum 10 s. Use `Task.Delay(..., ctx.Time, ct)`.
- Low disk: log and break (so the set is marked failed; preserved quirk **[B15 risk 13]**).
- Stop: return, record no failure.
- After retries: `MarkFailed(id, title)` + log manual osu! link.
- `finally`: `Active--`, remove task, advance overall.

**Exceptions:** `MirrorMissException`, `RateLimitedException`, `StoppedException`, `SearchRejectedException`, `AuthFatalException`, `ConfigException`. Map from **[B12]**. `OperationCanceledException` from the stop token maps to `StoppedException`; never let it surface as a failure.

**Tests:** port all fetch tests (resume, bad Content-Range, rate limit, miss, stop). Add:
- concurrency test: 200 parallel `Choose` + record calls; stats totals must be exact;
- host spacing test with fake time: N starts on one host are ≥ 0.9×0.85 s apart;
- `catboy` parks `catboy-video`.

### Phase 5: Orchestrator

Port `app.py`.

```csharp
public sealed class DownloadOrchestrator
{
    public async Task<RunResult> RunAsync(AppConfig cfg, string clientId, string secret, RunContext ctx);
}
```

Flow **[B6.3–6.6]**:
1. `Directory.CreateDirectory(out)`.
2. Delete all `*.part`, delete stale `failed_links.txt` **[B9]**.
3. Load `StatusStore`; `FolderScanner.ScanExisting`.
4. Token → search (status text via `Progress.SetMessage`).
5. `existing = scan ∪ status.Ids; status.PruneFailed(existing); todo = sets.Where(not in existing)` (preserve search order).
6. Batches of `cfg.Batch`: stop check + disk check → `Task.WhenAll(batch.Select(DownloadSetAsync))` → `status.Flush()` → stop check → pause `max(3, workers*0.5) + U(0,1)` s → if `MirrorsExhausted`, stop.
7. `finally`: delete all `*.part`; `status.Flush()`.

`RunResult` carries what `_on_done` needs: sets found, todo count, ok, failed IDs, stopped flag, mirrors-exhausted flag, search summary rows.

Do **not** use `Parallel.ForEachAsync`. Use `WhenAll` per batch exactly as Python does, because batch boundaries are part of the pacing design.

**Tests:** port the full orchestration tests using a fake handler serving both the API and the mirrors. Add a test that stop mid-batch leaves queued sets absent from status.

### Phase 6: Engine facade, bridge, host, and frontend

Split into four parts. 6a and 6d can be developed before the real UI exists.

#### 6a. Engine facade (in Core)

```csharp
public interface IEngine
{
    EngineState State { get; }                       // Idle, Running, Stopping
    Task<StartOutcome> StartAsync(RawConfig raw);    // validate, require credentials, save config, launch worker
    void Stop();                                     // cooperative
    ChannelReader<EngineEvent> Events { get; }       // single consumer: the host
}

public abstract record EngineEvent;
public sealed record StateChanged(string State, string? Detail) : EngineEvent;   // idle|running|stopping|done|stopped|paused|error
public sealed record LogBatch(IReadOnlyList<LogEntry> Entries) : EngineEvent;
public sealed record Progress(ProgressDto Value) : EngineEvent;                  // coalesced, at most every 120 ms while running
public sealed record Done(RunResultDto Result) : EngineEvent;
public sealed record EngineError(string Message, string? Field) : EngineEvent;
```

- `Engine` wraps `DownloadOrchestrator` and a fresh `RunContext` per run.
- `ProgressDto` contains: message, overall (completed/total/percent), active tasks, stats (ok, fail, active, bytes, average speed over the run), free disk GB (cached 3 s).
- `RunResultDto` carries everything the old `_on_done` needed, **already formatted**: summary rows (port `ui.py` helpers: `range_label`, `date_label`, `keys_label`, `summary_rows`, `search_rows`), failed entries (`reports.failed_entries`), footer message key + text, paused-safely flag. The frontend must not re-derive any of this.
- Validation errors are returned as `EngineError(message, field)`, not thrown across the bridge.
- `FakeEngine : IEngine` plays scripted scenarios with deterministic timing for e2e (see 6d).

#### 6b. Bridge protocol

Envelope: `{ "type": "<name>", ...fields }`. camelCase. Handshake carries `protocolVersion: 1`.

UI → host:

| type | fields | notes |
|---|---|---|
| `ready` | | UI loaded; host replies with `init` |
| `saveSettings` | `settings` | raw, as stored in config |
| `resetSettings` | | host replies with `settings` (defaults) |
| `start` | `settings` | host validates; errors come back as `error` |
| `stop` | | |
| `openUrl` | `url` | host **allow-lists** `https://osu.ppy.sh/beatmapsets/<digits>`; ignore anything else |
| `copyText` | `text` | host writes clipboard |
| `pickFolder` | | host shows folder dialog, replies `folderPicked` |
| `closeConfirmed` | | answer to `closeRequested` |

Host → UI: `init {protocolVersion, appVersion, settings, failed[]}`, `settings`, `state`, `log {entries:[{t, level, msg}]}`, `progress`, `done {result}`, `error {message, field?}`, `folderPicked {path}`, `closeRequested`.

Rules:
- Logs are batched (≤ one message per tick). `level` is the `LogLevel` enum name in lowercase.
- Host rejects any web message whose `Source` is not the app origin.
- Golden fixtures for every message type live in `tests/Fixtures/protocol/*.json`. A C# test serializes the DTOs and compares; a Vitest/Playwright test parses the same files with the TS types. This is the contract test.

#### 6c. Host (`ManiaDL.Host`)

- WinForms `Form`, 1200×820 default, min 1000×680. Set `WebView2.DefaultBackgroundColor` to `#111318` to avoid a white flash.
- Serve the embedded frontend from a virtual origin (e.g. `https://maniadl.app/`) via `WebResourceRequested`. Optional `--dev-url http://localhost:5173` loads the Vite dev server instead.
- Lock down: cancel `NavigationStarting` to other origins; handle `NewWindowRequested` by cancelling; disable default context menu, browser accelerator keys, and status bar. Re-enable DevTools only when `--debug-port` is passed.
- Process DPI: `PerMonitorV2` in the app manifest. Dark title bar via `DwmSetWindowAttribute` (attribute 20, fall back to 19) on the form handle.
- Missing runtime: catch `WebView2RuntimeNotFoundException`, show a `MessageBox` with the Evergreen runtime download link, exit.
- Event pump: one background task reads `IEngine.Events` and posts to the UI via `PostWebMessageAsJson` on the UI thread (`Control.BeginInvoke`).
- Close handling **[B6.8]**: on `FormClosing` while running, cancel the close, send `closeRequested`; the UI shows its own confirm dialog (so e2e can test it); on `closeConfirmed` request stop, wait for idle, then close. No native modal.
- CLI flags: `--debug-port <n>`, `--fake-engine <scenario>`, `--data-dir <path>`, `--dev-url <url>`. In Debug builds only: `--api-base <url>`, `--mirror-base <url>` so tests can point the real engine at a local fake server.

#### 6d. Frontend (`ui/`)

- React 18 + Vite + TS (`strict`), plain CSS with the palette as variables: `--bg #111318, --panel #191c23, --panel-alt #232834, --fg #e5e9f0, --muted #8f98a8, --accent #7aa2f7, --green #9ece6a, --red #f7768e, --yellow #e0af68, --border #2b303b, --field #1e222b`.
- One `useReducer` store fed by bridge events. `src/bridge/bridge.ts` wraps `window.chrome.webview` behind a tiny interface so tests can inject a fake.
- The UI is **dumb**: it shows what the host sends. It implements only these local behaviors **[B10.2]**:
  - advanced fields disabled unless "Enable advanced filters" is on; auto-enable on load if any advanced text is non-empty, `min_plays > 0`, or `include_nsfw`;
  - status checkboxes: "Any" clears others, a real status clears "Any", none left restores Ranked;
  - Reset button (sends `resetSettings`).
- Layout **[B10.1]**: header; left settings panel (≈440 px, scrolls independently, sections: osu! API, Download folder, Filters, Download behaviour, Advanced filters); right column with run status card + state chip, overall progress, six stat cards (downloaded, failed, active, data, speed, free disk), active-downloads table, tabs for Log and Failed downloads; footer with message + Stop + Start.
- Log: color by `level`, read-only, capped at 3000 lines, auto-scroll unless the user scrolled up.
- Failed tab: rows of ID + title; double-click or button sends `openUrl`; "Copy links" sends `copyText` for selected or all.
- Validation errors: inline banner next to the field named in `error.field` plus a footer message. No native dialogs.
- Required `data-testid`s (the agent's contract; do not rename casually): `start-btn`, `stop-btn`, `state-chip`, `footer-message`, `overall-progress`, `stat-downloaded`, `stat-failed`, `stat-active`, `stat-data`, `stat-speed`, `stat-free`, `active-row`, `log-view`, `log-line` (with `data-level`), `tab-log`, `tab-failed`, `failed-row`, `copy-links-btn`, `advanced-toggle`, `error-banner`, `confirm-close-dialog`, `confirm-close-yes`, and `setting-<key>` for every setting using the config key names.

#### 6e. Agent test harness (`scripts/e2e.ps1`, `ui/e2e/*.spec.ts`)

Fake scenarios for `--fake-engine`: `success`, `failures`, `mirrors-exhausted`, `auth-error`, `slow` (long enough to stop or close mid-run).

Required specs:
1. Startup shows saved settings from a seeded config in `--data-dir`.
2. Advanced gate and status-checkbox rules.
3. Start with missing credentials shows `error-banner` on the right field.
4. `success`: state chip goes Running → Done, stats and overall progress update, summary rows appear.
5. `failures`: Failed tab populated; Copy links puts expected text on the host's clipboard fake.
6. `slow` + Stop: ends in Stopped, Start re-enabled.
7. `mirrors-exhausted`: "Paused safely" footer.
8. Close during `slow`: `confirm-close-dialog` appears; confirm ends the process cleanly.
9. After every spec, save a screenshot to `ui/e2e/artifacts/<spec>.png` so the agent can visually check layout and theme.

Optional 6e-2: one real-engine e2e where `--api-base`/`--mirror-base` point at a local fake HTTP server that serves search pages and tiny `.osz` files; asserts files and `status.json` on disk.

### Phase 7: Deliberate improvements (only after parity is verified)

Each one is a separate commit with its own test. Flag each in the changelog.

| # | Change | Reason |
|---|---|---|
| 1 | Do **not** persist env-provided credentials on Start. Track whether the field value came from env and unchanged. | **[B15 risk 4]** privacy |
| 2 | Config/status location fallback: if the exe directory is not writable, use `%LOCALAPPDATA%\ManiaDL`. Keep portable-first. | **[B15 risk 5]** |
| 3 | Load prior failures into the Failed tab on startup. | **[B15 risk 15]** |
| 4 | Decide on `.part` cross-run resume: either keep deleting (parity) or keep `.part` and drop the cleanup. If kept, `.part` becomes a legal folder artifact and the folder contract must be updated. **Ask the maintainer before changing.** | **[B15 risk 3]** |
| 5 | Replace the unused `SETTING_KEYS` concept with a real reuse gate, or delete it. | **[B15 risk 7]** |
| 6 | Make the mirror list data-driven (embedded default + optional override file). | **[B15 risk 16]** |
| 7 | Optionally cancel in-flight HTTP on stop via the linked token (still mapped to `Stopped`, still no failure recorded). | responsiveness |

---

### Phase 8: Repo, CI, docs, and retiring Python

Do this only after Phases 0–6 are green, and with the maintainer's approval for anything destructive.

1. **`.gitignore`:** keep the existing entries (config, `status.json`, legacy state files, `*.part`, `*.osz`). Add `bin/`, `obj/`, `node_modules/`, `ui/dist/`, `ui/e2e/artifacts/`, `*.user`.
2. **Build scripts:** `scripts/build.ps1` runs `npm ci && npm run build` in `ui/`, then `dotnet publish src/ManiaDL.Host -c Release -r win-x64 --self-contained -p:PublishSingleFile=true -o dist`, producing `dist/ManiaDL.exe`. Provide `build_exe.bat` and `launch.bat` equivalents that call it.
3. **CI (`.github/workflows/build.yml`):** `windows-latest`; `setup-dotnet` 8; `setup-node` 20; `dotnet test`; `npm ci`; `npm run build`; `scripts/e2e.ps1` (verify the runner has the WebView2 Evergreen runtime; install it in the job if not); single-file publish; upload `dist/ManiaDL.exe`; publish a GitHub release on `v*` tags; keep the manual trigger. Add a smoke step that launches the exe with `--debug-port` and `--fake-engine success` and asserts one UI element (this answers the old "nothing verifies the executable" question).
4. **Version:** `3.0.0` in `Directory.Build.props`, shown in the UI via `init.appVersion`.
5. **Docs:** write a new `README.md` (features from A2, requirements, run, build, releases, download folder, credentials note, tests) and a new `AGENTS.md` (fast start with `dotnet`/`npm` commands, purpose and scope, project architecture and bridge, hard constraints from B15, traps from B16 and C7, conventions, open questions) for the C# project. After that, the maintainer may archive or delete this file.
6. **Retire Python (needs approval):** tag the last Python commit (e.g. `python-final`), then in a separate commit remove `maniadl.py`, `maniadl_core/`, the Python `tests/`, `pyproject.toml`, `uv.lock`, `ManiaDL.spec` and the old batch scripts. Never combine this with C# changes.

## C4. Concurrency rules (C# specific)

Python's event loop hid races. In C#, `Task.WhenAll` continuations run on the thread pool.

1. No shared mutable field without a lock, `Interlocked`, `Volatile`, or a concurrent collection.
2. `MirrorStats` per-mirror fields (`ok, fail, streak, until, last`): either one lock per mirror or immutable-record swap via `Interlocked.Exchange`. Pick one and use it everywhere.
3. `HostGate` creation: `ConcurrentDictionary.GetOrAdd` with a factory that has no side effects.
4. `StatusStore`: single lock; never hold it across `await` or I/O. Snapshot under lock, serialize outside.
5. Never use `.Result`/`.Wait()` in core code.
6. Every `Task.Delay` takes the `TimeProvider` overload and a token.
7. Core never touches UI or bridge objects; it exposes `IEngine` with commands and an event stream, and the host forwards events to the frontend.
8. Random: `Random.Shared` is thread-safe on .NET 6+; inject `Random` only where tests need determinism.

---

## C5. Invariants checklist (must hold at the end)

Copy to the PR description and tick each:

- [ ] Download folder contains only `.osz` + `status.json` after any normal or stopped run
- [ ] `status.json` v2 shape, key order, local timestamps, failed-only titles; Python can read C#'s output and vice versa
- [ ] Config file name/keys unchanged; unknown keys preserved on save
- [ ] Atomic writes for config and status; status flush every 8 dirty or 5 s, plus per batch and at end
- [ ] osu! API calls carry no browser UA/headers; mirror calls carry browser UA + `Referer`
- [ ] ≈60 osu! requests/min with adaptive penalty; pacing measured from request start; no inline 429 sleep
- [ ] Per-host mirror spacing (0.9 s ±15%), concurrency 2, host-wide 429 parking (30–300 s + jitter); catboy pair shares a host
- [ ] `Qualifies()` authoritative; any-mania-difficulty semantics; lexicographic date compare
- [ ] 400 fallback chain: full query → minimal query → no `q`
- [ ] First-seen search order preserved
- [ ] Cooperative stop: no failure recorded, queued sets stay queued, `.part` cleaned at end
- [ ] Already-on-disk valid `.osz` counted in status but not `Stats.Ok`
- [ ] Failed sets shown with direct osu! links; no report files written
- [ ] Request pacing is internal and always on; no UI control or warning for it
- [ ] Sets recorded in `status.json` are skipped even if their `.osz` was removed
- [ ] 87 Python tests have C# equivalents (track in `tests/PORTING.md`)

---

## C6. Test plan

- **Port first, then extend.** Create `tests/PORTING.md` mapping each Python test name to its C# test.
- **Fakes:** `FakeHandler : HttpMessageHandler` with a scripted queue of responses (status, headers, body chunks, optional delay/exception). Support streaming bodies in chunks so resume/Range tests work. `MakeOsz(params string[] entries)` builds in-memory zips.
- **Time:** use `Microsoft.Extensions.TimeProvider.Testing` `FakeTimeProvider` and advance it explicitly. No real sleeps in tests.
- **Filesystem:** each test gets a temp directory; cleaned in `Dispose`.
- **Golden files:** Python-produced `status.json` (v1/v2), `mania_dl_config.json` (old and new key sets), recorded search pages.
- **New tests the Python suite lacks [B13]:** exact `status.json` bytes, concurrency stress on stats/mirror choice, `.part` cleanup at run end, UI-free view-model tests for the Start/validation path.
- **UI:** Playwright over CDP against the real WebView2 app (see Phase 6d). Frontend reducers and bridge parsing may also get Vitest tests. Golden protocol fixtures keep C# and TypeScript in agreement.

---

## C7. Known quirks to preserve (and not "fix" in phases 0–6)

From **[B15]**; each should have a test or a code comment saying "intentional parity":

- `=` in the date parser is an upper bound
- Failed IDs are retried only when search returns them again
- Low-disk marks the current set failed
- Valid pre-existing `.osz` doesn't bump `Stats.Ok`
- `valid_osz` checks only for a `.osu` entry
- Speed is a whole-run average
- `scan_existing` does not write to status

---

## C8. Definition of done

1. All phases 0–6 merged, Core tests and `scripts/e2e.ps1` green on `windows-latest`.
2. Manual smoke on a real run against a small query (e.g. 1 key count, `limit=5`): search → download → stop → restart → no duplicates, no `.part` left, status correct.
3. The C# build, run against a folder last managed by the Python build, downloads nothing it already has and preserves existing `status.json` entries and failures.
4. Single-file self-contained `ManiaDL.exe` builds in CI and is attached on `v*` tags.
5. Invariants checklist (C5) fully ticked.
6. Phase 7 items either done with tests or explicitly deferred in `CHANGELOG.md`.
7. Phase 8 done (CI, new `README.md` and `AGENTS.md`); Python retired only with maintainer approval.

## C9. Working agreement for the agent

- Work phase by phase; commit after each green phase.
- Follow Part A4 (stay on the current branch, keep Python intact until approved, no secrets, `git diff` before commits).
- When Python and this document disagree, **Python behavior wins**. Note the discrepancy in `tests/PORTING.md`.
- When something here says "check `X.py`", open the file and copy the exact constants. Don't guess numbers.
- Ask the maintainer before any change listed under Phase 7 item 4, or any change to the folder contract.
- Don't add dependencies beyond: `Microsoft.Web.WebView2`, `Microsoft.Extensions.TimeProvider.Testing` (tests), xUnit; frontend: `react`, `react-dom`, `vite`, `typescript`, `@playwright/test`, optionally `vitest`. No UI component libraries, no state libraries.