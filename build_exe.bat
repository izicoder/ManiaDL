@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "scripts\build.ps1"
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)
echo Built dist\ManiaDL.exe
pause
