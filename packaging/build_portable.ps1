param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path "$PSScriptRoot/..").Path
Set-Location $repoRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required to build this project. Install from https://docs.astral.sh/uv/"
}

Write-Host "[1/5] Installing build dependencies..."
uv sync --frozen --group dev

Write-Host "[2/5] Building launcher executable..."
uv run pyinstaller --noconfirm --clean packaging/myfinmodel.spec

$distRoot = Join-Path $repoRoot "dist/MyFinModel"
$launcherDist = Join-Path $repoRoot "dist/MyFinModelLauncher"
$launcherExe = Join-Path $launcherDist "MyFinModelLauncher.exe"
$launcherInternal = Join-Path $launcherDist "_internal"

if (-not (Test-Path $launcherExe)) {
    throw "Expected launcher executable not found: $launcherExe"
}

if (-not (Test-Path $launcherInternal)) {
    throw "Expected PyInstaller contents directory not found: $launcherInternal"
}

if (Test-Path $distRoot) {
    Remove-Item $distRoot -Recurse -Force
}

Write-Host "[3/5] Assembling portable folder..."
New-Item -ItemType Directory -Path $distRoot | Out-Null
Copy-Item $launcherExe $distRoot
Copy-Item $launcherInternal $distRoot -Recurse
Copy-Item (Join-Path $repoRoot "packaging/launch_myfinmodel.bat") $distRoot
Copy-Item (Join-Path $repoRoot "packaging/README-Run.txt") $distRoot

Set-Content -Path (Join-Path $distRoot "VERSION.txt") -Value $Version

Write-Host "[4/5] Creating portable zip artifact..."
$zipName = "MyFinModel-v$Version-portable.zip"
$zipPath = Join-Path $repoRoot "dist/$zipName"

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path $distRoot -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host "[5/5] Portable artifact ready: $zipPath"
