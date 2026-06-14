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

Write-Host "Built: $root\dist\Storm Competitor Analysis.exe"
