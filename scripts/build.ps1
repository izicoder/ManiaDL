# Builds the React frontend and publishes the single-file Windows executable.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build.ps1 [-Configuration Release]
param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$ui = Join-Path $root "ui"

Push-Location $ui
try {
    if (Test-Path (Join-Path $ui "package-lock.json")) {
        npm ci
    }
    else {
        npm install
    }
    npm run build
}
finally {
    Pop-Location
}

dotnet publish (Join-Path $root "src\ManiaDL.Host\ManiaDL.Host.csproj") `
    -c $Configuration `
    -r win-x64 `
    --self-contained `
    -p:PublishSingleFile=true `
    -o (Join-Path $root "dist")

Write-Host "Built dist\ManiaDL.exe"
