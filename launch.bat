@echo off
setlocal
cd /d "%~dp0"

if not exist "ui\dist\index.html" (
    pushd ui
    call npm ci || goto :error
    call npm run build || goto :error
    popd
)

dotnet build src\ManiaDL.Host\ManiaDL.Host.csproj -c Release --nologo || goto :error
start "" "src\ManiaDL.Host\bin\Release\net8.0-windows\ManiaDL.exe"
exit /b 0

:error
echo Build failed.
pause
exit /b 1
