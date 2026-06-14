from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
DEFAULT_TIMEOUT = 45
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES_PATH = ROOT / "config" / "parser_rules.json"


@dataclass
class CategoryProduct:
    name: str
    sku: str
    final_price: str
    old_price: str
    promo: str
    product_url: str
    image_url: str
    source_product_id: str
    page_number: int
    page_url: str


@dataclass
class ProductDetail:
    product_url: str
    title: str
    image_url: str
    overview: str
    description: str
    specifications: list[str]


@dataclass
class PageScrape:
    page_number: int
    page_url: str
    status_code: int
    products_on_page: int
    new_products: int
    skipped_reason: str = ""


@dataclass
class CategoryScrapeResult:
    source_url: str
    pages: list[PageScrape]
    products: list[CategoryProduct]
    brand_counts: dict[str, int]
    category_counts: dict[str, int]
    brand_category_counts: dict[str, dict[str, int]]
    validation: dict[str, object]


@dataclass
class ParserRules:
    brands: list[dict[str, object]]
    own_brands: list[str]
    category_rules: list[dict[str, object]]
    default_category: str


def load_parser_rules(path: Path | None = None) -> ParserRules:
    rules_path = path or DEFAULT_RULES_PATH
    data = json.loads(rules_path.read_text(encoding="utf-8-sig"))
    return ParserRules(
        brands=list(data.get("brands", [])),
        own_brands=[str(brand) for brand in data.get("own_brands", [])],
        category_rules=list(data.get("category_rules", [])),
        default_category=str(data.get("default_category", "Uncategorized")),
    )


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def normalize_price(value: str | None) -> str:
    value = clean_text(value)
    if not value:
        return ""
    try:
        amount = float(value)
    except ValueError:
        return value
    if amount.is_integer():
        return f"R{int(amount):,}".replace(",", " ")
    return f"R{amount:,.2f}".replace(",", " ")


def category_page_url(base_url: str, page_number: int) -> str:
    """Return a Magento category URL for a specific page using only the p= query.

    Lesson learned: do not collect arbitrary category links for pagination.
    Magento filter links often contain parameters such as _mof_data or colour
    and may 403 or move the scrape into a filtered result set. For category
    paging, keep the original query intact and only add/replace p=.
    """

    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)
    if page_number <= 1:
        query.pop("p", None)
    else:
        query["p"] = [str(page_number)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def fetch_html(session: requests.Session, url: str) -> tuple[int, str]:
    response = session.get(url, timeout=DEFAULT_TIMEOUT)
    if response.status_code == 403:
        return response.status_code, ""
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.status_code, response.text


def extract_category_products(html: str, page_number: int, page_url: str) -> list[CategoryProduct]:
    soup = BeautifulSoup(html, "lxml")
    products: list[CategoryProduct] = []
    for item in soup.select("li.item.product.product-item"):
        link = item.select_one("a.product-item-link")
        if not link:
            continue
        final = item.select_one('[data-price-type="finalPrice"]')
        old = item.select_one('[data-price-type="oldPrice"]')
        form = item.select_one("form[data-product-sku]")
        image = item.select_one("img.product-image-photo")
        price_box = item.select_one("[data-product-id]")
        old_price = normalize_price(old.get("data-price-amount") if old else "")
        final_price = normalize_price(final.get("data-price-amount") if final else "")
        products.append(
            CategoryProduct(
                name=clean_text(link.get_text(" ", strip=True)),
                sku=form.get("data-product-sku", "") if form else "",
                final_price=final_price,
                old_price=old_price,
                promo="Yes" if old_price else "No",
                product_url=link.get("href", ""),
                image_url=image.get("src", "") if image else "",
                source_product_id=price_box.get("data-product-id", "") if price_box else "",
                page_number=page_number,
                page_url=page_url,
            )
        )
    return products


def discover_visible_page_numbers(html: str) -> set[int]:
    """Read visible toolbar page numbers without following filter links."""

    soup = BeautifulSoup(html, "lxml")
    pages = {1}
    for anchor in soup.select(".pages a[href], .toolbar a[href]"):
        query = parse_qs(urlparse(anchor.get("href", "")).query)
        if "p" not in query:
            continue
        try:
            pages.add(int(query["p"][0]))
        except (TypeError, ValueError):
            continue
    return pages


def scrape_category_pages(
    source_url: str,
    *,
    max_pages: int = 20,
    stop_after_empty_pages: int = 2,
    session: requests.Session | None = None,
    parser_rules: ParserRules | None = None,
) -> CategoryScrapeResult:
    """Scrape all products from a Magento category using safe page traversal.

    Strategy:
    1. Fetch page 1.
    2. Read visible pagination numbers from the toolbar.
    3. Probe sequential `p=` pages because toolbar links can be incomplete.
    4. Stop after repeated empty or duplicate pages.
    5. Dedupe by product URL.
    """

    session = session or make_session()
    parser_rules = parser_rules or load_parser_rules()
    first_status, first_html = fetch_html(session, category_page_url(source_url, 1))
    if not first_html:
        return CategoryScrapeResult(source_url, [PageScrape(1, source_url, first_status, 0, 0, "No HTML returned")], [], {}, {}, {})

    candidate_pages = discover_visible_page_numbers(first_html)
    candidate_pages.update(range(1, max_pages + 1))

    products: list[CategoryProduct] = []
    pages: list[PageScrape] = []
    seen_product_urls: set[str] = set()
    empty_streak = 0

    for page_number in sorted(candidate_pages):
        if page_number > max_pages:
            continue
        page_url = category_page_url(source_url, page_number)
        status_code, html = fetch_html(session, page_url)
        if not html:
            pages.append(PageScrape(page_number, page_url, status_code, 0, 0, "No HTML returned"))
            empty_streak += 1
            if empty_streak >= stop_after_empty_pages:
                break
            continue

        page_products = extract_category_products(html, page_number, page_url)
        new_count = 0
        for product in page_products:
            key = product.product_url or product.name.casefold()
            if not key or key in seen_product_urls:
                continue
            seen_product_urls.add(key)
            products.append(product)
            new_count += 1

        pages.append(PageScrape(page_number, page_url, status_code, len(page_products), new_count))
        if page_number > 1 and new_count == 0:
            empty_streak += 1
        else:
            empty_streak = 0
        if empty_streak >= stop_after_empty_pages:
            break

    return build_category_result(source_url, pages, products, parser_rules)


def scrape_product_detail(product_url: str, *, session: requests.Session | None = None) -> ProductDetail:
    session = session or make_session()
    _, html = fetch_html(session, product_url)
    soup = BeautifulSoup(html, "lxml")
    title_node = soup.select_one("h1.page-title span")
    overview_node = soup.select_one(".product.attribute.overview")
    description_node = soup.select_one(".product.attribute.description")
    og_image = soup.select_one('meta[property="og:image"]')
    image_url = og_image.get("content", "") if og_image else ""
    specs = []
    for node in soup.select(".additional-attributes-wrapper tr, .product.attribute.overview li"):
        text = clean_text(node.get_text(" ", strip=True))
        if text:
            specs.append(text)
    return ProductDetail(
        product_url=product_url,
        title=clean_text(title_node.get_text(" ", strip=True) if title_node else ""),
        image_url=image_url,
        overview=clean_text(overview_node.get_text(" ", strip=True) if overview_node else ""),
        description=clean_text(description_node.get_text(" ", strip=True) if description_node else ""),
        specifications=specs,
    )


def infer_brand(product_name: str, parser_rules: ParserRules | None = None, known_brands: Iterable[str] | None = None) -> str:
    parser_rules = parser_rules or load_parser_rules()
    lower = product_name.casefold()
    if known_brands:
        brand_rules = [{"name": brand, "patterns": [brand]} for brand in known_brands]
    else:
        brand_rules = parser_rules.brands
    for brand_rule in brand_rules:
        brand_name = str(brand_rule.get("name", ""))
        patterns = brand_rule.get("patterns", [])
        if isinstance(patterns, str):
            patterns = [patterns]
        for pattern in patterns:
            normalized = str(pattern).casefold()
            if lower.startswith(normalized) or re.search(r"\b" + re.escape(normalized) + r"\b", lower):
                return brand_name
    return product_name.split()[0] if product_name else "Unknown"


def infer_product_category(product_name: str, parser_rules: ParserRules | None = None) -> str:
    parser_rules = parser_rules or load_parser_rules()
    lower = product_name.casefold()
    for rule in parser_rules.category_rules:
        match_all = [str(token).casefold() for token in rule.get("match_all", [])]
        match_any = [str(token).casefold() for token in rule.get("match_any", [])]
        match_any_also = [str(token).casefold() for token in rule.get("match_any_also", [])]
        if match_all and not all(token in lower for token in match_all):
            continue
        if match_any and not any(token in lower for token in match_any):
            continue
        if match_any_also and not any(token in lower for token in match_any_also):
            continue
        return str(rule.get("category", parser_rules.default_category))
    return parser_rules.default_category


def build_category_result(
    source_url: str,
    pages: list[PageScrape],
    products: list[CategoryProduct],
    parser_rules: ParserRules | None = None,
) -> CategoryScrapeResult:
    parser_rules = parser_rules or load_parser_rules()
    brand_counts = Counter(infer_brand(product.name, parser_rules) for product in products)
    category_counts = Counter(infer_product_category(product.name, parser_rules) for product in products)
    brand_category_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for product in products:
        brand_category_counts[infer_brand(product.name, parser_rules)][infer_product_category(product.name, parser_rules)] += 1
    product_count = len(products)
    brand_total = sum(brand_counts.values())
    category_total = sum(category_counts.values())
    uncategorized_count = category_counts.get(parser_rules.default_category, 0)
    unknown_brand_count = brand_counts.get("Unknown", 0)
    validation = {
        "product_count": product_count,
        "brand_total": brand_total,
        "category_total": category_total,
        "unknown_brand_count": unknown_brand_count,
        "uncategorized_count": uncategorized_count,
        "all_products_have_brand": brand_total == product_count and unknown_brand_count == 0,
        "all_products_have_category": category_total == product_count and uncategorized_count == 0,
        "is_valid": brand_total == product_count and category_total == product_count and unknown_brand_count == 0 and uncategorized_count == 0,
    }
    return CategoryScrapeResult(
        source_url=source_url,
        pages=pages,
        products=products,
        brand_counts=dict(brand_counts.most_common()),
        category_counts=dict(category_counts.most_common()),
        brand_category_counts={brand: dict(counts.most_common()) for brand, counts in sorted(brand_category_counts.items())},
        validation=validation,
    )


def result_to_dict(result: CategoryScrapeResult) -> dict:
    return asdict(result)


def read_links(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
