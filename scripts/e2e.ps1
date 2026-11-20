# Runs the WebView2 end-to-end suite against the real host with scripted engines.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/e2e.ps1 [-SkipBuild]
param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$ui = Join-Path $root "ui"
$hostProject = Join-Path $root "src\ManiaDL.Host\ManiaDL.Host.csproj"

if (-not $SkipBuild) {
    Push-Location $ui
    try {
        if (-not (Test-Path (Join-Path $ui "node_modules"))) {
            npm ci
        }
        npm run build
    }
    finally {
        Pop-Location
    }

    dotnet build $hostProject -c Debug --nologo
}

$exe = Join-Path $root "src\ManiaDL.Host\bin\Debug\net8.0-windows\ManiaDL.exe"
if (-not (Test-Path $exe)) {
    throw "ManiaDL.exe was not built at $exe"
}

$env:MANIADL_EXE = $exe
Push-Location $ui
try {
    npx playwright test
}
finally {
    Pop-Location
}

exit $LASTEXITCODE
