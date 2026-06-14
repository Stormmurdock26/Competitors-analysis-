from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from .paths import APP_TEMPLATE_PATH, CONFIG_DIR, OUTPUT_DIR, ROOT, ensure_external_resources, ensure_script_imports

ensure_external_resources()
ensure_script_imports()

from build_competitor_analysis import (  # noqa: E402
    DEFAULT_OUTPUT_PATH,
    build_workbook,
)
from scraper_tools import (  # noqa: E402
    CategoryProduct,
    ParserRules,
    infer_brand,
    infer_product_category,
    load_parser_rules,
    make_session,
    scrape_category_pages,
)


LOCAL_LLM_CONFIG_PATH = CONFIG_DIR / "local_llm.json"
APP_RULES_PATH = CONFIG_DIR / "parser_rules.json"
BUILD_SUMMARY_PATH = OUTPUT_DIR / "combined_competitor_analysis_summary.json"


@dataclass
class DiscoveryResult:
    products: list[CategoryProduct]
    brand_counts: dict[str, int]
    category_counts: dict[str, int]
    unknown_brand_counts: dict[str, int]
    uncategorized_products: list[CategoryProduct]
    link_summaries: list[dict]


@dataclass
class BuildRequest:
    links: list[str]
    output_path: Path
    rules_path: Path = APP_RULES_PATH
    template_path: Path = APP_TEMPLATE_PATH
    append_to: Path | None = None
    feature_alignment: str = "llm"


def normalize_links(raw_links: str | list[str]) -> list[str]:
    if isinstance(raw_links, str):
        candidates = raw_links.replace(",", "\n").splitlines()
    else:
        candidates = raw_links
    return [link.strip() for link in candidates if link.strip()]


def known_brand_names(rules: ParserRules) -> set[str]:
    return {str(brand.get("name", "")).casefold() for brand in rules.brands if brand.get("name")}


def known_category_names(rules: ParserRules) -> set[str]:
    return {str(rule.get("category", "")).casefold() for rule in rules.category_rules if rule.get("category")}


def discover_links(links: list[str], rules_path: Path = APP_RULES_PATH) -> DiscoveryResult:
    parser_rules = load_parser_rules(rules_path)
    session = make_session()
    all_products: list[CategoryProduct] = []
    link_summaries: list[dict] = []
    seen: set[str] = set()

    for link in links:
        result = scrape_category_pages(link, parser_rules=parser_rules, session=session)
        link_summaries.append(
            {
                "source_url": link,
                "product_count": len(result.products),
                "brand_counts": result.brand_counts,
                "category_counts": result.category_counts,
                "validation": result.validation,
            }
        )
        for product in result.products:
            key = product.product_url or product.name.casefold()
            if key in seen:
                continue
            seen.add(key)
            all_products.append(product)

    brand_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    unknown_brand_counts: dict[str, int] = {}
    uncategorized_products: list[CategoryProduct] = []
    known_brands = known_brand_names(parser_rules)

    for product in all_products:
        brand = infer_brand(product.name, parser_rules)
        category = infer_product_category(product.name, parser_rules)
        brand_counts[brand] = brand_counts.get(brand, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        if brand.casefold() not in known_brands:
            unknown_brand_counts[brand] = unknown_brand_counts.get(brand, 0) + 1
        if category == parser_rules.default_category:
            uncategorized_products.append(product)

    return DiscoveryResult(
        products=all_products,
        brand_counts=dict(sorted(brand_counts.items())),
        category_counts=dict(sorted(category_counts.items())),
        unknown_brand_counts=dict(sorted(unknown_brand_counts.items())),
        uncategorized_products=uncategorized_products,
        link_summaries=link_summaries,
    )


def load_rules_json(rules_path: Path = APP_RULES_PATH) -> dict:
    return json.loads(rules_path.read_text(encoding="utf-8-sig"))


def save_rules_json(data: dict, rules_path: Path = APP_RULES_PATH) -> None:
    rules_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_brand_rule(brand_name: str, ownership: str, rules_path: Path = APP_RULES_PATH) -> None:
    brand_name = brand_name.strip()
    if not brand_name:
        return
    data = load_rules_json(rules_path)
    brands = data.setdefault("brands", [])
    existing = {str(brand.get("name", "")).casefold() for brand in brands}
    if brand_name.casefold() not in existing:
        brands.append({"name": brand_name, "patterns": [brand_name.casefold()]})

    own_brands = data.setdefault("own_brands", [])
    own_set = {str(brand).casefold() for brand in own_brands}
    if ownership == "owned" and brand_name.casefold() not in own_set:
        own_brands.append(brand_name)
    if ownership == "competitor":
        data["own_brands"] = [brand for brand in own_brands if str(brand).casefold() != brand_name.casefold()]
    save_rules_json(data, rules_path)


def add_category_rule(category_name: str, match_terms: str, rules_path: Path = APP_RULES_PATH) -> None:
    category_name = category_name.strip()
    terms = [term.strip().casefold() for term in match_terms.replace(",", "\n").splitlines() if term.strip()]
    if not category_name or not terms:
        return
    data = load_rules_json(rules_path)
    rules = data.setdefault("category_rules", [])
    candidate = {"category": category_name, "match_any": terms}
    if candidate not in rules:
        rules.append(candidate)
    save_rules_json(data, rules_path)


def run_build(request: BuildRequest) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    temp_links = OUTPUT_DIR / "app_selected_links.txt"
    temp_links.write_text("\n".join(request.links), encoding="utf-8")
    args = SimpleNamespace(
        url=None,
        links=temp_links,
        rules=request.rules_path,
        template=request.template_path,
        output=request.output_path,
        append_to=request.append_to,
        output_dir=OUTPUT_DIR,
        llm_config=LOCAL_LLM_CONFIG_PATH,
        feature_alignment=request.feature_alignment,
        month=None,
    )
    from datetime import datetime

    args.month = datetime.now().strftime("%b-%y")
    build_workbook(args)
    return request.output_path


def load_build_summary(summary_path: Path = BUILD_SUMMARY_PATH) -> dict:
    if not summary_path.exists():
        return {}
    return json.loads(summary_path.read_text(encoding="utf-8-sig"))


def collect_build_warnings(summary: dict) -> list[str]:
    warnings: list[str] = []
    for run in summary.get("feature_alignment", {}).get("runs", []):
        category = run.get("display_category") or run.get("category") or "Unknown category"
        source = run.get("source")
        if source and source != "llm":
            warnings.append(f"Feature alignment for {category} used {source}.")
        for warning in run.get("warnings", []):
            warnings.append(f"{category}: {warning}")
    return warnings


def default_output_path() -> Path:
    return DEFAULT_OUTPUT_PATH


def root_path() -> Path:
    return ROOT
