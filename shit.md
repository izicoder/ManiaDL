REDACTED-SECRET-ROTATE-ME

74093

Use PyInstaller. You don't need npm for this, only Python (your screenshot shows you're using uv).

**1. Use the updated script.**
Without a fix, a one-file exe unpacks itself to a temp folder that is deleted on exit, so your saved config and downloads would vanish every run. The updated `osu_mania_downloader.py` now keeps `mania_dl_config.json` and the default `downloads` folder next to the exe.

**2. Build it (on Windows, in your project folder):**
```
uv pip install pyinstaller textual aiohttp
pyinstaller --onefile --console --name ManiaDL --collect-all textual osu_mania_downloader.py
```
(With plain pip, use `pip install pyinstaller textual aiohttp` instead.)

Your exe will be at `dist\ManiaDL.exe`. The flags:
- `--onefile` makes a single exe.
- `--console` is required because this is a terminal app. Don't use `--noconsole` or it won't show anything.
- `--collect-all textual` bundles Textual's data files, which a plain build sometimes misses. If the build complains about a missing module, add `--hidden-import <name>`.

**Things to expect**
- I can't build it here (my sandbox is Linux with no network), so I haven't tested the exe. The packaging steps come from how PyInstaller usually works, not from a build I ran.
- The first launch is slow (a few seconds) because a one-file exe unpacks itself every time.
- Antivirus sometimes flags PyInstaller one-file exes as suspicious. If that happens, build with `--onedir` instead (a folder with the exe inside, faster to start and flagged less), or add an exclusion.
- Run it in Windows Terminal. Double-clicking the exe may open the old console window, where the colors and mouse support can be worse.
- Rebuild the exe whenever you change the script.