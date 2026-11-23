# Agent notes

ManiaDL is a single-user Windows desktop app: a C# engine (`ManiaDL.Core`), a
WinForms + WebView2 host (`ManiaDL.Host`) and a React frontend (`ui/`). There is no
server, database, CLI mode or background daemon.

## Commands

```powershell
dotnet test ManiaDL.sln                      # unit tests
dotnet run --project src/ManiaDL.Host        # run (build ui/dist first)
powershell -File scripts/build.ps1           # single-file dist\ManiaDL.exe
powershell -File scripts/e2e.ps1             # Playwright against the real UI
```

The frontend must be built before running or publishing: `cd ui; npm ci; npm run build`.
`ui/dist` is embedded into the host at build time.

## Layout

- `src/ManiaDL.Core` — constants, parsing, config, API/search, mirrors, state,
  orchestrator, engine facade. Must not reference WinForms or WebView2.
- `src/ManiaDL.Host` — window, bridge, embedded UI, CLI flags.
- `ui/src` — reducer-driven UI. The frontend is dumb: it renders host messages.
- `tests/ManiaDL.Core.Tests` — xUnit; `tests/Fixtures` holds golden files.

## Hard constraints

- Download folder contains only `.osz` files and one `status.json`.
- `status.json` stays version 2 with keys `version, updated, downloaded, failed,
  titles`; local timestamps, titles only for failed IDs.
- Config file name and snake_case keys stay compatible with existing installs;
  unknown keys are preserved.
- osu! API requests use the API user agent, never browser headers. Mirror requests
  use browser headers plus `Referer`.
- Search pacing is ~60 requests/minute measured from request start; never sleep
  inline on 429.
- Per-host mirror spacing (0.9 s ±15%), concurrency 2, host-wide 429 parking.
- Client-side qualification is authoritative; preserve search order.
- Stop is cooperative: no failure recorded, queued sets stay queued, `.part` files
  are removed at run end.
- A valid `.osz` already on disk is recorded in status but does not increment the
  downloaded counter.
- No report files are written; failures live in the UI.
- Request pacing is internal and always on. Do not add UI controls or warnings for it.

## Conventions

- Short imperative commit subjects; no new branches unless asked.
- Core code is async and thread-safe: no shared mutable state, no `.Result`/`.Wait()`,
  every `Task.Delay` takes a `TimeProvider` and a token.
- Never commit or log credentials. Tests use temp folders and fake values.
