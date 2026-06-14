# Storm Competitor Analysis

This repository tracks the Excel-based workflow for building competitor analysis workbooks.

## Canonical Template

The canonical blank template for the workflow is:

`Competitors Analysis Blank Template.xlsx`

That file is the starting point for new competitor analysis runs. Its current structure is:

- Columns stop at `P`.
- Rows `1:2` are the report header.
- Cell `A1` uses the generic title `Competitor Analysis`; retailer/category-specific titles are applied only when a workbook is generated.
- Each product section is a 13-row block: category row, picture row, product name row, SKU row, price heading rows, five feature/spec rows, and one blank spacer row.
- The first block starts at row `3`; additional blank blocks start at rows `16`, `29`, `42`, `55`, and `68`.
- The workbook used range is `A1:P80`.
- Hyperlinks are removed from the blank template.
- Product ownership color fills are not part of the blank template. Those colors are applied later to distinguish our products from competitor products.
- Product name rows use height `30.75` and centered alignment.
- Price rows and picture placeholder rows use centered alignment.
- Secondary product columns `B`, `D`, `F`, `H`, `J`, `L`, `N`, and `P` are widened so `Product on promo?` fits.
- Five feature rows are bordered across each two-column product slot.

Rebuild the blank template formatting with:

```powershell
uv run --python 3.12 --with requests --with beautifulsoup4 --with lxml --with openpyxl --with pillow python .\scripts\build_blank_template.py
```

## Source Files

- `Comp Analysis.xlsx`: working competitor analysis workbook used as the formatting/source reference.
- `Competitors Analysis Blank Template.xlsx`: canonical blank template for this workflow.
- `Makro-Eiger Smalls Cheat sheet.xlsx`: source/reference workbook for product and promotional data.
- `links.txt`: input file for competitor/category URLs.
- `library_options.md`: technical library notes for future automation work.

## Workflow Notes

1. Start from `Competitors Analysis Blank Template.xlsx`.
2. Add competitor product data into uncolored product slots.
3. Apply ownership color fills only after the blank template stage.
4. Use links from `links.txt` to scrape or match product data as needed.
5. Keep the blank template clean so it can be reused without old product data, hyperlinks, or ownership markings.

## Locked-In Scraper

The locked-in scraper stack is:

`requests + BeautifulSoup(lxml)`

Reusable scraping code lives in:

- `scripts/scraper_tools.py`: shared scraper functions and data models.
- `scripts/scrape_category.py`: command-line wrapper for category discovery.
- `config/parser_rules.json`: runtime-editable brand and category rules.

Lessons encoded in `scripts/scraper_tools.py`:

- Do not treat every category link as pagination. Filter/facet links can contain parameters such as `_mof_data` or `colour` and may return `403` or a filtered result set.
- For Magento category pagination, keep the original category query and only add or replace the `p=` page parameter.
- Scrape page 1, read visible toolbar page numbers, and also probe sequential `p=` pages because pagination links may be incomplete.
- Stop after repeated pages with no new products.
- Dedupe products by product URL.
- Decode the page as UTF-8 so product names with en dashes stay readable.
- Product detail pages are also static HTML on the tested site, so `scrape_product_detail()` can extract title, overview, description, specifications, and image URL without Playwright.

The parser rules are intentionally not hardcoded into the core scraper. To teach the parser a new brand or product category, edit `config/parser_rules.json`:

- Add brand aliases under `brands`.
- Add or remove owned brands under `own_brands`. Owned brands are color-filled in generated competitor analysis workbooks.
- Add ordered category rules under `category_rules`.
- Put more specific rules before broad rules. For example, `Combos` must appear before `Mousepads` because combo products can contain the word `Mousepad`.
- Use `default_category` to catch products that do not match any rule.

Validation fails when any product is assigned `Unknown` brand or `Uncategorized`, or when the brand/category totals do not equal the product count. This is deliberate: it exposes parser gaps instead of silently forcing bad categories.

Run the category scraper:

```powershell
uv run --python 3.12 --with requests --with beautifulsoup4 --with lxml python .\scripts\scrape_category.py
```

Run with an explicit URL and rules file:

```powershell
uv run --python 3.12 --with requests --with beautifulsoup4 --with lxml python .\scripts\scrape_category.py --url "https://www.incredible.co.za/products/gaming/accessories?cat=367561&product_list_dir=asc" --rules .\config\parser_rules.json --output-dir .\scraper_outputs\cat_367561_config
```

Outputs:

- `scraper_outputs/category_scrape.json`
- `scraper_outputs/category_scrape.md`

## Competitor Analysis Workbook Generation

The combined Excel generator is:

`scripts/build_competitor_analysis.py`

The blank template generator is:

`scripts/build_blank_template.py`

It reads all URLs from `links.txt`, scrapes each category, groups products by parser category, scrapes each product detail page for image/spec text, embeds product images, aligns comparable features with the local LLM, and colors owned-brand product blocks from `config/parser_rules.json`.

Current owned brands:

- Logitech
- VX Gaming
- VolkanoG

Run it with:

```powershell
uv run --python 3.12 --with requests --with beautifulsoup4 --with lxml --with openpyxl --with pillow python .\scripts\build_competitor_analysis.py
```

By default, workbook generation uses `config/local_llm.json` and Ollama to align comparable product features into five side-by-side feature rows. To bypass the model and write raw scraped feature order for debugging, run:

```powershell
uv run --python 3.12 --with requests --with beautifulsoup4 --with lxml --with openpyxl --with pillow python .\scripts\build_competitor_analysis.py --feature-alignment raw
```

Default output:

- `Competitors Analysis - Incredible Gaming.xlsx`
- `scraper_outputs/combined_competitor_analysis_summary.json`

Workbook output rules:

- Report title: `Incredible Connection Gaming Accessory Analysis`.
- Buyer/account stays as a generic field for later filtering.
- Month is filled in the workbook header.
- Raw SKU/product codes stay intact in scraped JSON, but Excel displays them without leading zeros.
- Products are sorted inside each category by everyday price from low to high, left to right, continuing into the next block when needed.
- Product images are embedded into the picture slot rather than left as image URLs.
- Feature rows use the local model's structured comparison output so comparable specs line up across neighboring products.
- Owned-brand products are full color-filled; competitor products remain unfilled.

Supported app modes:

- Start a fresh workbook from one URL.
- Start a fresh workbook from multiple URLs.
- Append one URL to an existing competitor analysis workbook.
- Append multiple URLs to an existing competitor analysis workbook.

## Desktop Application

The PySide6 desktop app lives in:

- `storm_app/main.py`: GUI entry point.
- `storm_app/workflow.py`: discovery, parser-rule updates, and workbook generation service.
- `storm_app/llm_manager.py`: Ollama/model availability checks and model download runner.
- `storm_app/update_manager.py`: GitHub release update-check hook.
- `config/app_settings.json`: local login and future update-check configuration.

Run the app with:

```powershell
.\scripts\run_desktop_app.ps1
```

Default local login:

- Username: `admin`
- Password: `admin`

The app currently supports:

- Paste one or more scrape URLs.
- Choose fresh workbook generation or append to an existing workbook.
- Choose where the output `.xlsx` should be saved.
- Run discovery before generation.
- Review newly discovered brands that are not yet in `config/parser_rules.json`.
- Mark newly discovered brands as `owned` or `competitor`.
- Review uncategorized products and add runtime category rules.
- Check local Ollama/model availability.
- Download the configured model with progress output when Ollama is available.
- Build the competitor analysis workbook through the existing scraper and Excel generator.

Update checks are wired through `storm_app/update_manager.py` and configured to use:

```text
https://github.com/Stormmurdock26/Competitors-analysis-.git
```

The checker looks for the latest GitHub release first, then falls back to the latest tag. Publish versions as tags/releases such as `v0.1.1`, `v0.2.0`, etc. If the repo has no release or tag yet, the app logs a clear "No GitHub release or version tag has been published yet." message instead of failing with a generic HTTP error.

For deployed/exe-only installs, every released version must have a GitHub Release asset containing the rebuilt `Storm Competitor Analysis.exe`. The executable is a release artifact only; it is ignored by git and must not be committed to the repository. When a newer release has a downloadable `.exe` asset, the app downloads that asset beside the running executable, closes the app, swaps in the new executable, and relaunches it. The helper writes progress and errors to `storm_update.log`.

For development/source folders, the updater still has a fallback path that can fetch the target tag from `origin`, rebuild with `scripts/build_exe.ps1`, and relaunch `dist/Storm Competitor Analysis.exe`. That fallback requires the local folder to remain a git clone of the update repo and these tools must be available on the machine:

```powershell
git --version
uv --version
gh --version
```

The GitHub CLI is installed on this machine, but it still needs authentication before pushing code or creating releases:

```powershell
gh auth login
```

Release builds are automated through `.github/workflows/release.yml`. When a `v*` tag is pushed, GitHub Actions builds `dist\Storm Competitor Analysis.exe` from source and attaches it to the GitHub Release. That release asset is what deployed exe-only installs download during self-update.

Manual release asset creation is only needed if the workflow is unavailable:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" release create v0.1.10 ".\dist\Storm Competitor Analysis.exe" --repo Stormmurdock26/Competitors-analysis- --title "v0.1.10" --notes "Release v0.1.10"
```

Packaging notes:

- Development launch uses `uv run --no-project` through `scripts/run_desktop_app.ps1` so no manually managed local `venv` is required.
- `pyproject.toml` defines the Python package and GUI entry point for future packaging.
- Build a local one-file Windows executable with:

```powershell
.\scripts\build_exe.ps1
```

- The generated executable is written to `dist\Storm Competitor Analysis.exe`.
- The `.exe`, `build`, and `.spec` outputs are ignored by git and should be rebuilt locally or by a release workflow.
- A minimal handoff to another Windows PC is a folder containing only `Storm Competitor Analysis.exe`; the app creates its runtime folders/config on first launch and updates from GitHub Release executable assets.

## Local Feature Alignment LLM

Feature comparison alignment is handled by a narrow local-LLM backend:

- `config/local_llm.json`: runtime model/provider config.
- `scripts/feature_alignment_llm.py`: strict JSON prompt, Ollama request wrapper, response validation, and fallback alignment.
- `scripts/test_feature_alignment.py`: test harness using real scraped products.
- `scripts/check_local_llm.py`: local model/GPU environment report.

The local model receives product names, categories, overview text, descriptions, and scraped spec bullets. It returns strict JSON rows that align comparable features side-by-side, for example DPI on one row, sensor on one row, buttons on one row, and warranty on one row.

The current config uses:

```json
{
  "provider": "ollama",
  "model": "gemma4:e4b"
}
```

Ollama will use available GPU acceleration where supported. If GPU acceleration is unavailable, it falls back to CPU/RAM. The application is intentionally locked to one required local LLM; the front end only reports whether the LLM is ready, missing, or in error.

Run the environment check:

```powershell
uv run --python 3.12 --with requests python .\scripts\check_local_llm.py
```

Run a feature-alignment sample:

```powershell
uv run --python 3.12 --with requests --with beautifulsoup4 --with lxml python .\scripts\test_feature_alignment.py --category "Wired mouse" --limit 4
```

Sample output:

- `scraper_outputs/feature_alignment_sample.json`

## Scraper Comparison

The scraper comparison workflow is implemented in:

`scripts/scraper_comparison.py`

It reads `links.txt`, tests multiple scraper approaches, writes normalized JSON/Markdown summaries, and creates filled Excel files from the canonical template under `scraper_outputs/`.

Current scraper approaches:

- BeautifulSoup
- lxml
- selectolax
- Scrapy selector
- Playwright
- Firecrawl, when `FIRECRAWL_API_KEY` is available

## Python Environment

Use `uv` for Python tooling in this project. Do not create a local `venv`.

Examples:

```powershell
uv run --python 3.12 --with openpyxl python script.py
uv run --python 3.12 --with beautifulsoup4 --with lxml --with requests python scrape.py
uv run --python 3.12 --with requests --with beautifulsoup4 --with lxml --with cssselect --with selectolax --with scrapy --with openpyxl --with playwright --with firecrawl-py python .\scripts\scraper_comparison.py
```
