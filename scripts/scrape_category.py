from __future__ import annotations

import argparse
import json
from pathlib import Path

from scraper_tools import (
    DEFAULT_RULES_PATH,
    infer_brand,
    infer_product_category,
    load_parser_rules,
    read_links,
    result_to_dict,
    scrape_category_pages,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LINKS_PATH = ROOT / "links.txt"
DEFAULT_OUTPUT_DIR = ROOT / "scraper_outputs"


def write_markdown(result, output_path: Path, parser_rules) -> None:
    lines = [
        "# Category Scrape",
        "",
        f"Source URL: `{result.source_url}`",
        "",
        "## Pages",
        "",
        "| Page | Status | Products on page | New products | URL | Notes |",
        "| ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for page in result.pages:
        lines.append(
            f"| {page.page_number} | {page.status_code} | {page.products_on_page} | "
            f"{page.new_products} | {page.page_url} | {page.skipped_reason} |"
        )
    lines.extend(
        [
            "",
            f"Total products: **{len(result.products)}**",
            "",
            "## Validation",
            "",
            f"- Product count: `{result.validation['product_count']}`",
            f"- Brand total: `{result.validation['brand_total']}`",
            f"- Category total: `{result.validation['category_total']}`",
            f"- Unknown brand count: `{result.validation['unknown_brand_count']}`",
            f"- Uncategorized count: `{result.validation['uncategorized_count']}`",
            f"- All products have a brand: `{result.validation['all_products_have_brand']}`",
            f"- All products have a category: `{result.validation['all_products_have_category']}`",
            f"- Valid: `{result.validation['is_valid']}`",
            "",
            "## Brands",
            "",
        ]
    )
    lines.extend(["| Brand | Products |", "| --- | ---: |"])
    for brand, count in result.brand_counts.items():
        lines.append(f"| {brand} | {count} |")
    lines.extend(["", "## Product Categories", "", "| Category | Products |", "| --- | ---: |"])
    for category, count in result.category_counts.items():
        lines.append(f"| {category} | {count} |")
    lines.extend(["", "## Brand By Category", "", "| Brand | Category breakdown |", "| --- | --- |"])
    for brand, categories in result.brand_category_counts.items():
        breakdown = ", ".join(f"{category}: {count}" for category, count in categories.items())
        lines.append(f"| {brand} | {breakdown} |")
    lines.extend(["", "## Products", "", "| # | Brand | Category | Product | Price | Promo | URL |", "| ---: | --- | --- | --- | ---: | --- | --- |"])
    for index, product in enumerate(result.products, 1):
        price = product.final_price or product.old_price
        lines.append(
            f"| {index} | {infer_brand(product.name, parser_rules)} | {infer_product_category(product.name, parser_rules)} | "
            f"{product.name} | {price} | {product.promo} | {product.product_url} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape all pages of a Magento-style category URL safely.")
    parser.add_argument("--url", help="Category URL to scrape. Defaults to the first URL in links.txt.")
    parser.add_argument("--links", type=Path, default=DEFAULT_LINKS_PATH, help="Text file containing category URLs.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for JSON and Markdown outputs.")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum p= pages to probe.")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH, help="Runtime parser rules JSON file.")
    args = parser.parse_args()

    url = args.url
    if not url:
        links = read_links(args.links)
        if not links:
            raise SystemExit(f"No links found in {args.links}")
        url = links[0]

    parser_rules = load_parser_rules(args.rules)
    result = scrape_category_pages(url, max_pages=args.max_pages, parser_rules=parser_rules)
    args.output_dir.mkdir(exist_ok=True)
    json_path = args.output_dir / "category_scrape.json"
    md_path = args.output_dir / "category_scrape.md"
    json_path.write_text(json.dumps(result_to_dict(result), indent=2), encoding="utf-8")
    write_markdown(result, md_path, parser_rules)
    print(f"Scraped {len(result.products)} products from {len(result.pages)} page attempts")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
