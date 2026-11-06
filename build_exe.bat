@echo off
cd /d "%~dp0"
uv run --extra build pyinstaller --onefile --windowed --name ManiaDL maniadl.py
pause
