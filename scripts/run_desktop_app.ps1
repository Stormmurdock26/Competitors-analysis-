$ErrorActionPreference = "Stop"

uv run --no-project `
  --python 3.12 `
  --with pyside6 `
  --with requests `
  --with beautifulsoup4 `
  --with lxml `
  --with openpyxl `
  --with pillow `
  python -m storm_app.main
