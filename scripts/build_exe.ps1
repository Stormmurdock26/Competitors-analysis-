$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

uv run --no-project `
  --python 3.12 `
  --with pyinstaller `
  --with pyside6 `
  --with requests `
  --with beautifulsoup4 `
  --with lxml `
  --with openpyxl `
  --with pillow `
  pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "Storm Competitor Analysis" `
    --add-data "scripts;scripts" `
    --add-data "config;config" `
    --add-data "Competitors Analysis Blank Template.xlsx;." `
    --hidden-import "bs4" `
    --hidden-import "lxml" `
    --hidden-import "openpyxl" `
    --hidden-import "PIL" `
    "storm_app/main.py"

$initPath = Join-Path $root "storm_app\__init__.py"
$initText = Get-Content $initPath -Raw
if ($initText -match 'APP_VERSION\s*=\s*"([^"]+)"') {
  $version = $Matches[1]
  Set-Content -Path (Join-Path $root "dist\app_version.txt") -Value $version -Encoding UTF8
  Write-Host "Version: $version"
}

Write-Host "Built: $root\dist\Storm Competitor Analysis.exe"
