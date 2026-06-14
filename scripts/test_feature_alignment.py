from __future__ import annotations

import argparse
import json
from pathlib import Path

from feature_alignment_llm import ProductFeatureInput, align_features_with_local_llm
from scraper_tools import (
    DEFAULT_RULES_PATH,
    infer_brand,
    infer_product_category,
    load_parser_rules,
    make_session,
    scrape_category_pages,
    scrape_product_detail,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "scraper_outputs" / "feature_alignment_sample.json"


def build_inputs(url: str, category: str, limit: int, rules_path: Path) -> list[ProductFeatureInput]:
    parser_rules = load_parser_rules(rules_path)
    session = make_session()
    result = scrape_category_pages(url, parser_rules=parser_rules, session=session)
    products = [product for product in result.products if infer_product_category(product.name, parser_rules) == category][:limit]
    inputs: list[ProductFeatureInput] = []
    for index, product in enumerate(products, 1):
        detail = scrape_product_detail(product.product_url, session=session)
        inputs.append(
            ProductFeatureInput(
                product_id=f"p{index}",
                name=product.name,
                brand=infer_brand(product.name, parser_rules),
                category=category,
                overview=detail.overview,
                description=detail.description,
                specifications=detail.specifications,
            )
        )
    return inputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Test local LLM feature alignment on real scraped products.")
    parser.add_argument("--url", default="https://www.incredible.co.za/products/gaming/accessories?cat=367558&product_list_dir=asc")
    parser.add_argument("--category", default="Wired mouse")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    products = build_inputs(args.url, args.category, args.limit, args.rules)
    alignment = align_features_with_local_llm(products)
    payload = {
        "category": args.category,
        "products": [product.__dict__ for product in products],
        "alignment": {
            "source": alignment.source,
            "warnings": alignment.warnings,
            "rows": [{"label": row.label, "values": row.values} for row in alignment.rows],
        },
    }
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.output}")
    print(json.dumps(payload["alignment"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
