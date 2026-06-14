from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LLM_CONFIG_PATH = ROOT / "config" / "local_llm.json"
REQUIRED_MODEL = "gemma4:e4b"


FEATURE_ALIGNMENT_SYSTEM_PROMPT = """You are a narrow product-comparison structuring engine.

Your only task is to convert product feature text into a compact comparison grid for Excel.

Scope:
- You compare products in the same broad category.
- You align comparable features on the same row.
- You return strict JSON only.
- You do not write prose, markdown, comments, or explanations.

Critical behavior:
- Do not invent missing values.
- If a product does not state a comparable feature, use an empty string for that product.
- Never fill a row with an unrelated feature just to avoid blanks.
- Every non-empty cell must be explicitly supported by the supplied text for that product and that row label.
- Before returning JSON, verify each non-empty value against the row label. If the support is weak or unrelated, replace it with an empty string.
- Prefer concrete specs over marketing wording.
- Keep each cell short enough for Excel.
- Use at most the requested number of rows.
- Order rows from most useful for comparison to least useful.
- Use comparable row labels, not product-specific labels.

Examples of comparable rows:
- Mouse category: DPI / sensitivity, sensor, buttons, connectivity, lighting, weight, cable, warranty.
- Headset category: driver size, connection, microphone, controls, weight, comfort, lighting, warranty.
- Mousepad category: dimensions, material, surface, base/grip, waterproofing, thickness, warranty.
- Combo category: included items, connection, lighting, layout, headset/mouse specs, warranty.

Return schema:
{
  "rows": [
    {
      "label": "short comparable feature label",
      "values": {
        "product_id_here": "value stated or inferred directly from supplied text",
        "another_product_id": ""
      }
    }
  ],
  "warnings": [
    "short warning if source text was sparse or ambiguous"
  ]
}

Rules:
- Include every product_id from the input in every row's values object.
- Do not include product ids that were not provided.
- Do not exceed max_rows.
- If source text only contains marketing blurbs, extract concrete comparable facts from those blurbs.
- For a warranty row, only include values that explicitly mention warranty or a warranty duration.
- For a DPI/sensitivity row, only include values that explicitly mention DPI/sensitivity or a clear DPI number/range.
- For a sensor row, only include values that explicitly mention sensor/tracking/optical/laser.
- For a connection row, only include values that explicitly mention wired/wireless/Bluetooth/USB/aux/3.5mm/Lightspeed/Hyperspeed.
- If no good comparable features exist, return rows as an empty list and explain briefly in warnings.
"""


@dataclass
class LLMConfig:
    enabled: bool
    provider: str
    base_url: str
    model: str
    temperature: float
    num_ctx: int
    timeout_seconds: int
    max_feature_rows: int


@dataclass
class ProductFeatureInput:
    product_id: str
    name: str
    brand: str
    category: str
    overview: str
    description: str
    specifications: list[str]


@dataclass
class FeatureRow:
    label: str
    values: dict[str, str]


@dataclass
class FeatureAlignment:
    rows: list[FeatureRow]
    warnings: list[str]
    source: str


def load_llm_config(path: Path | None = None) -> LLMConfig:
    config_path = path or DEFAULT_LLM_CONFIG_PATH
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if data.get("model") != REQUIRED_MODEL:
        data["model"] = REQUIRED_MODEL
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return LLMConfig(
        enabled=bool(data.get("enabled", True)),
        provider=str(data.get("provider", "ollama")),
        base_url=str(data.get("base_url", "http://localhost:11434")).rstrip("/"),
        model=REQUIRED_MODEL,
        temperature=float(data.get("temperature", 0.0)),
        num_ctx=int(data.get("num_ctx", 8192)),
        timeout_seconds=int(data.get("timeout_seconds", 120)),
        max_feature_rows=int(data.get("max_feature_rows", 5)),
    )


def build_user_prompt(products: list[ProductFeatureInput], max_rows: int) -> str:
    payload = {
        "max_rows": max_rows,
        "products": [
            {
                "product_id": product.product_id,
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "overview": product.overview,
                "description": product.description,
                "specifications": product.specifications,
            }
            for product in products
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def validate_alignment(
    raw: dict[str, Any],
    product_ids: list[str],
    max_rows: int,
    product_aliases: dict[str, str] | None = None,
) -> FeatureAlignment:
    rows = raw.get("rows", [])
    warnings = raw.get("warnings", [])
    if not isinstance(rows, list):
        raise ValueError("LLM response field 'rows' must be a list")
    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    product_id_set = set(product_ids)
    product_aliases = product_aliases or {}
    parsed_rows: list[FeatureRow] = []
    for row in rows[:max_rows]:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", "")).strip()
        values = row.get("values", {})
        if not label or not isinstance(values, dict):
            continue
        normalized_values = {product_id: normalize_cell_value(values.get(product_id, "")) for product_id in product_ids}
        extra_ids = set()
        for value_key, value in values.items():
            if value_key in product_id_set:
                continue
            alias_id = product_aliases.get(str(value_key).casefold())
            if not alias_id and len(product_ids) == 1:
                alias_id = product_ids[0]
            if alias_id:
                normalized_values[alias_id] = normalized_values[alias_id] or normalize_cell_value(value)
            else:
                extra_ids.add(value_key)
        if extra_ids:
            warnings.append(f"Ignored unexpected product ids: {', '.join(sorted(extra_ids))}")
        parsed_rows.append(FeatureRow(label=label, values=normalized_values))

    return FeatureAlignment(rows=parsed_rows, warnings=dedupe_warnings(warnings), source="llm")


def dedupe_warnings(warnings: list[Any]) -> list[str]:
    unique = []
    seen = set()
    for warning in warnings:
        text = str(warning)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def normalize_cell_value(value: Any) -> str:
    text = str(value or "").strip()
    if text.casefold() in {"n/a", "na", "not stated", "not specified", "none", "unknown", "null"}:
        return ""
    return text


def ollama_chat(config: LLMConfig, user_prompt: str) -> str:
    response = requests.post(
        f"{config.base_url}/api/chat",
        json={
            "model": config.model,
            "messages": [
                {"role": "system", "content": FEATURE_ALIGNMENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": config.temperature,
                "num_ctx": config.num_ctx,
            },
        },
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("message", {}).get("content", "")


def fallback_alignment(products: list[ProductFeatureInput], max_rows: int, reason: str) -> FeatureAlignment:
    labels = ["Feature 1", "Feature 2", "Feature 3", "Feature 4", "Feature 5"][:max_rows]
    rows = []
    for index, label in enumerate(labels):
        values = {}
        for product in products:
            source = product.specifications or split_feature_text(product.overview) or split_feature_text(product.description)
            values[product.product_id] = source[index] if index < len(source) else ""
        rows.append(FeatureRow(label=label, values=values))
    return FeatureAlignment(rows=rows, warnings=[f"Used fallback alignment: {reason}"], source="fallback")


def split_feature_text(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"(?<=[.;])\s+|\n+|(?:\s{2,})", value)
    return [part.strip(" -") for part in parts if part.strip(" -")]


def align_features_with_local_llm(
    products: list[ProductFeatureInput],
    *,
    config_path: Path | None = None,
    allow_fallback: bool = True,
) -> FeatureAlignment:
    config = load_llm_config(config_path)
    max_rows = config.max_feature_rows
    product_ids = [product.product_id for product in products]
    if not config.enabled:
        return fallback_alignment(products, max_rows, "local LLM disabled in config")
    if config.provider != "ollama":
        if allow_fallback:
            return fallback_alignment(products, max_rows, f"unsupported provider: {config.provider}")
        raise ValueError(f"Unsupported provider: {config.provider}")

    user_prompt = build_user_prompt(products, max_rows)
    product_aliases = {product.name.casefold(): product.product_id for product in products}
    try:
        content = ollama_chat(config, user_prompt)
        raw = extract_json_object(content)
        return validate_alignment(raw, product_ids, max_rows, product_aliases)
    except Exception as exc:
        if allow_fallback:
            return fallback_alignment(products, max_rows, str(exc))
        raise
