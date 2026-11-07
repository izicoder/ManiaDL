# ManiaDL

Bulk osu!mania beatmap downloader for osu!lazer, with a dark tkinter desktop UI.

Search the osu! API with the filters you care about, then download matching
beatmap sets (`.osz`) from community mirrors with automatic fallback,
rate-limit handling and resume support.

## Features

- Filter by status, key count, star rating, favourites, plays, BPM, length,
  notes, genre, language, ranked date, mapper/title/artist/source and NSFW.
- Free-text osu! search query support (`stars>=5`, `keys=4`, `ranked>=2020`, ...).
- Fast searches: requests are paced at osu!'s requested ~60 per minute, and
  genre/language filters narrow the query on the server instead of only being
  checked after every page. Nothing is cached between runs.
- Parallel downloads with batching, per-host pacing and automatic mirror
  fallback (nerinyan, nekoha, catboy, beatconnect, osu.direct, sayobot).
- Resumable transfers and `.osz` validation before a file is accepted.
- Live status panel: overall progress, active downloads, mirror health, stats
  and log.
- Failed sets stay visible in the Failed downloads tab with direct links.
- One `status.json` per download folder remembers what was fetched and what
  failed. Nothing else is written there besides the `.osz` files.

## Requirements

- Windows (the UI is tkinter, but the core should run elsewhere)
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for the commands below

## Run

Double-click `launch.bat`, or run:

```powershell
uv sync
uv run maniadl.py
```

Enter your osu! OAuth client ID and secret in the window. If you do not have
them yet, click **How to get keys** — it links to
<https://osu.ppy.sh/home/account/edit>.

The credentials are saved to `mania_dl_config.json` next to `maniadl.py` in
plain text. Keep that file private and out of git. `OSU_CLIENT_ID` /
`OSU_CLIENT_SECRET` environment variables override saved values.

## Build

Double-click `build_exe.bat`, or run:

```powershell
uv sync --extra build
uv run --extra build pyinstaller --onefile --windowed --name ManiaDL maniadl.py
```

The executable is written to `dist/ManiaDL.exe`. `ManiaDL.spec` is kept in
sync for reproducible builds.

## Releases

`.github/workflows/build.yml` runs the offline test suite and builds the
windowed executable. Pushing a tag such as `v2.0.0` publishes a GitHub release
with `ManiaDL.exe` attached. The workflow can also be started manually from the
Actions tab.

## Download folder

`status.json` stores downloaded and failed set IDs plus titles. Already
downloaded sets are skipped, including sets recorded in `status.json` whose
`.osz` was later removed. Old `downloaded_ids.txt` / `failed.txt` files from
earlier versions are imported once and deleted.

## Tests

```powershell
uv run python -m unittest discover -s tests -t . -v
```

The suite is offline: API and mirror calls are replaced with fakes.
