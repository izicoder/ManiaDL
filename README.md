# ManiaDL

Bulk osu!mania beatmap downloader for osu!lazer.

**[Download the latest Windows release](https://github.com/izicoder/ManiaDL/releases/latest)** —
a standalone `ManiaDL.exe`; no .NET install required.

Search the osu! API with the filters you care about, then download matching `.osz`
sets from community mirrors with automatic fallback, rate-limit handling and resume
support.

## Features

- Filter by status, key count, star rating, favourites, plays, BPM, length, notes,
  genre, language, ranked date, mapper/title/artist/source and NSFW.
- Free-text osu! search queries (`stars>=5`, `keys=4`, `ranked>=2020`, …).
- Searches paced at osu!'s requested ~60 requests/minute; genre/language narrow the
  query server-side.
- Parallel downloads with batching, per-host pacing and automatic mirror fallback
  (nerinyan, nekoha, catboy, beatconnect, osu.direct, sayobot).
- Resumable transfers and `.osz` validation before a file is accepted.
- Previously failed sets are retried on the next run.
- Live status panel: overall progress, active downloads, stats and log.
- Failed sets stay visible in the Failed downloads tab with direct osu! links.
- One `status.json` per download folder remembers what was fetched and what failed.

## Quick start

1. Download `ManiaDL.exe` from the latest release and run it.
2. Enter your osu! OAuth client ID and secret. Create them at
   <https://osu.ppy.sh/home/account/edit> ("How to get keys" in the app opens the same page).
3. Pick a download folder and your filters, then press **Start**.

## Requirements

- Windows 10 or 11.
- [WebView2 Evergreen Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)
  (preinstalled on current Windows).
- To build from source: .NET 8 SDK and Node.js 20+.

## Run from source

```powershell
cd ui
npm ci
npm run build
cd ..
dotnet run --project src/ManiaDL.Host
```

Or double-click `launch.bat`, which builds the frontend if needed and starts the app.

## Build the executable

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

The single-file, self-contained executable lands in `dist\ManiaDL.exe`.
`build_exe.bat` does the same thing with a double-click.

## Releases

Pushing a tag such as `v3.0.0` runs `.github/workflows/build.yml`, which tests,
publishes `ManiaDL.exe` and creates a GitHub release with generated notes.

## Configuration

- `mania_dl_config.json` is written beside the executable. It contains your osu!
  client secret in plain text, so keep it private.
- `OSU_CLIENT_ID` and `OSU_CLIENT_SECRET` environment variables override the saved
  values.
- The download folder contains only `.osz` files and one `status.json`.

## Tests

```powershell
dotnet test ManiaDL.sln
powershell -ExecutionPolicy Bypass -File scripts/e2e.ps1
```

The e2e suite drives the real WebView2 UI with Playwright and saves screenshots to
`ui/e2e/artifacts/`.

## Project layout

```text
src/ManiaDL.Core   engine, search, mirrors, state (no UI references)
src/ManiaDL.Host   WinForms + WebView2 shell and bridge
ui/                React + Vite frontend
tests/             xUnit tests and fixtures
scripts/           build and e2e helpers
```
