"""Load local offer snapshots and normalize their deliberately messy records.

The importer is intentionally strict. It accepts only explicit, supported
price, package and catalog evidence; unknown values stay ``None`` and the
record is quarantined with a reason code. No live vendor data is fetched.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from .matching import exact_sku_match


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_HARAKAT = re.compile(r"[\u064b-\u065f\u0670]")
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?|[^\W\d_]+")
_PRICE = re.compile(r"^((?:[0-9]{1,3}(?:[,٬ ][0-9]{3})+)|(?:[0-9]+))\s*(ریال|تومان)$")
_INTEGER = re.compile(r"^[0-9]+$")


def _plain(value: Any) -> str:
    if value is None:
        return ""
    return (unicodedata.normalize("NFKC", str(value)).translate(_DIGITS)
            .replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
            .replace("\u066b", ".").strip())


def _tokens(value: Any) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(_HARAKAT.sub("", _plain(value).casefold())))


def _price_irr(value: Any, steps: list[str]) -> tuple[int | None, str | None]:
    raw = _plain(value)
    if not raw:
        return None, "UNKNOWN_PRICE"
    match = _PRICE.fullmatch(raw)
    if match is None:
        if not ("ریال" in raw or "تومان" in raw):
            return None, "UNKNOWN_CURRENCY"
        return None, "INVALID_PRICE"
    number_text, currency = match.groups()
    amount = int(re.sub(r"[,٬ ]", "", number_text))
    if amount <= 0:
        return None, "INVALID_PRICE"
    if number_text != re.sub(r"[,٬ ]", "", number_text):
        steps.append("price:thousands_separators_removed")
    if _plain(value) != str(value).strip():
        steps.append("digits:persian_arabic_to_ascii")
    if currency == "تومان":
        steps.append("currency:toman_to_irr_x10")
        amount *= 10
    else:
        steps.append("currency:irr")
    return amount, None


def _number(value: Any, *, suffix: str | None = None) -> int | None:
    raw = _plain(value)
    if suffix and raw.endswith(suffix):
        raw = raw[: -len(suffix)].strip()
    return int(raw) if _INTEGER.fullmatch(raw) else None


def _package_size(value: Any, base_unit: str, steps: list[str]) -> int | None:
    token_string = " ".join(_tokens(value))
    if base_unit == "عدد":
        if token_string in {"عدد", "تکی", "یک عدد"}:
            size = 1
        else:
            match = re.fullmatch(r"(?:بسته|پک) ([0-9]+) (?:عدد|عددی|تایی)", token_string)
            size = int(match.group(1)) if match else None
    elif base_unit == "بسته ۵۰۰ برگی":
        if token_string in {"بسته 500 برگی", "یک بسته 500 برگی"}:
            size = 1
        else:
            match = re.fullmatch(r"کارتن ([0-9]+) بسته(?: 500 برگی)?", token_string)
            size = int(match.group(1)) if match else None
    else:
        return None
    if size is None or size <= 0:
        return None
    steps.append(f"package:{size}x{base_unit}")
    return size


def _catalog_id(title: Any, catalog: list[dict[str, Any]], steps: list[str]) -> tuple[str | None, str | None]:
    title_tokens = _tokens(title)
    matches: list[tuple[int, str, str]] = []
    alias_owners: dict[tuple[str, ...], set[str]] = {}
    for item in catalog:
        for alias in [item["name"], *item.get("aliases", [])]:
            alias_tokens = _tokens(alias)
            if not alias_tokens:
                continue
            alias_owners.setdefault(alias_tokens, set()).add(item["id"])
            length = len(alias_tokens)
            if any(title_tokens[index : index + length] == alias_tokens for index in range(len(title_tokens) - length + 1)):
                matches.append((length, item["id"], alias))
    if not matches:
        return None, "UNKNOWN_SKU"
    specific_ids = {item_id for _, item_id, alias in matches if len(alias_owners[_tokens(alias)]) == 1}
    if len(specific_ids) > 1:
        return None, "AMBIGUOUS_SKU"
    if specific_ids:
        matches = [match for match in matches if match[1] in specific_ids]
    longest = max(length for length, _, _ in matches)
    winners = {item_id for length, item_id, _ in matches if length == longest}
    if len(winners) != 1:
        return None, "AMBIGUOUS_SKU"
    chosen = next(iter(winners))
    selected_item = next(item for item in catalog if item["id"] == chosen)
    for other in catalog:
        if other["id"] == chosen or other.get("category") != selected_item.get("category"):
            continue
        for spec_key, selected_value in selected_item.get("specs", {}).items():
            other_value = other.get("specs", {}).get(spec_key)
            if other_value is None or other_value == selected_value:
                continue
            for marker in other.get("spec_markers", {}).get(spec_key, []):
                marker_tokens = _tokens(marker)
                if marker_tokens and any(
                    title_tokens[index : index + len(marker_tokens)] == marker_tokens
                    for index in range(len(title_tokens) - len(marker_tokens) + 1)
                ):
                    return None, "CONFLICTING_SPEC"
    alias = next(alias for length, item_id, alias in matches if item_id == chosen and length == longest)
    steps.append(f"catalog:alias:{alias}")
    return chosen, None


def _terms(record: dict[str, Any]) -> dict[str, Any]:
    if record["source_format"] == "listing_rows":
        return record["raw_terms"]
    terms = record["raw_terms"]
    return {
        "min_packages": terms.get("minimum_packs"),
        "package_step": terms.get("order_step"),
        "stock_packages": terms.get("stock"),
        "lead_days": terms.get("delivery"),
        "invoice": terms.get("invoice"),
        "tax": terms.get("tax"),
    }


def _normalize(record: dict[str, Any], catalog: list[dict[str, Any]], vendors: dict[str, dict[str, Any]]) -> dict[str, Any]:
    steps: list[str] = []
    reasons: list[str] = []
    vendor_id = record["vendor_id"]
    item_id, item_error = _catalog_id(record["raw_title"], catalog, steps)
    if item_error:
        reasons.append(item_error)
    item = next((entry for entry in catalog if entry["id"] == item_id), None)
    package_size = _package_size(record["raw_unit_text"], item["base_unit"], steps) if item else None
    if item and package_size is None:
        reasons.append("UNKNOWN_UNIT")
    price, price_error = _price_irr(record["raw_price_text"], steps)
    if price_error:
        reasons.append(price_error)

    terms = _terms(record)
    min_packages = _number(terms.get("min_packages"))
    package_step = _number(terms.get("package_step"))
    stock_packages = _number(terms.get("stock_packages"), suffix="بسته")
    lead_days = _number(terms.get("lead_days"), suffix="روز")
    if min_packages is None or min_packages < 0:
        reasons.append("UNKNOWN_MIN_PACKAGES")
    if package_step is None or package_step <= 0:
        reasons.append("UNKNOWN_PACKAGE_STEP")
    if stock_packages is None or stock_packages < 0:
        reasons.append("UNKNOWN_STOCK")
    if lead_days is None or lead_days < 0:
        reasons.append("UNKNOWN_LEAD_TIME")

    invoice_text = " ".join(_tokens(terms.get("invoice")))
    invoice_status = {"yes": "declared_yes", "بله": "declared_yes", "no": "declared_no", "خیر": "declared_no"}.get(invoice_text, "unknown")
    tax_text = " ".join(_tokens(terms.get("tax")))
    tax_status = "included" if tax_text in {"included", "شامل مالیات"} else "unknown"
    if tax_status == "unknown":
        reasons.append("UNKNOWN_TAX")

    vendor = vendors.get(vendor_id)
    if vendor is None:
        reasons.append("UNKNOWN_VENDOR")
    else:
        shipping = vendor.get("shipping_irr")
        minimum_order = vendor.get("minimum_order_irr")
        if shipping is None:
            reasons.append("UNKNOWN_SHIPPING")
        elif type(shipping) is not int or shipping < 0:
            reasons.append("INVALID_SHIPPING")
        if minimum_order is None:
            reasons.append("UNKNOWN_MINIMUM_ORDER")
        elif type(minimum_order) is not int or minimum_order < 0:
            reasons.append("INVALID_MINIMUM_ORDER")

    return {
        "id": f"offer-{record['source_record_id']}",
        "raw_record_id": record["id"],
        "vendor_id": vendor_id,
        "catalog_item_id": item_id,
        "package_size_base": package_size,
        "package_price_irr": price,
        "min_packages": min_packages,
        "package_step": package_step,
        "stock_packages": stock_packages,
        "lead_days": lead_days,
        "invoice_status": invoice_status,
        "tax_status": tax_status,
        "source_label": record["source_label"],
        "source_url": record.get("source_url"),
        "raw_title": record["raw_title"],
        "raw_price_text": record["raw_price_text"],
        "price_status": "observed" if price is not None else "unknown",
        "stock_status": "observed" if stock_packages is not None else "not_reported",
        "availability_status": "observed" if stock_packages is not None else "unknown",
        "match_status": "not_evaluated",
        "field_status": {
            "price_irr": "observed" if price is not None else "unknown",
            "raw_price_text": "observed",
            "stock_packages": "observed" if stock_packages is not None else "not_reported",
            "package_size_base": "observed" if package_size is not None else "unknown",
            "lead_days": "observed" if lead_days is not None else "not_reported",
            "source_url": "observed" if record.get("source_url") else "not_reported",
            "captured_at": "observed",
        },
        "valid_at": record["generated_at"],
        "normalization_status": "rejected" if reasons else "accepted",
        "rejection_reason": reasons[0] if reasons else None,
        "rejection_reasons": reasons,
        "normalization_steps": steps,
    }


def _raw_records(document: dict[str, Any], snapshot_id: str) -> list[dict[str, Any]]:
    fmt = document["format"]
    records = document.get("records") if fmt == "listing_rows" else document.get("cards")
    if fmt not in {"listing_rows", "vendor_cards"} or not isinstance(records, list):
        raise ValueError(f"unsupported or malformed source document: {document.get('id')}")
    output = []
    for entry in records:
        if not isinstance(entry, dict):
            raise ValueError("source record must be an object")
        if fmt == "listing_rows":
            source_record_id = entry["listing_id"]
            vendor_id = entry["merchant"]
            title = entry["headline"]
            price = entry.get("display_price")
            unit = entry.get("packaging")
            terms = entry.get("terms", {})
        else:
            source_record_id = entry["ref"]
            vendor_id = entry["seller_ref"]
            title = entry["product_name"]
            price = entry.get("price_label")
            unit = entry.get("quantity_label")
            terms = entry.get("fulfilment", {})
        if not isinstance(terms, dict):
            raise ValueError(f"terms must be an object: {source_record_id}")
        payload = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        output.append({
            "id": f"raw-{source_record_id}",
            "snapshot_id": snapshot_id,
            "source_label": document["source_label"],
            "source_document_id": document["id"],
            "source_format": fmt,
            "source_record_id": source_record_id,
            "vendor_id": vendor_id,
            "generated_at": document["generated_at"],
            "title": title,
            "price_text": price,
            "package_text": unit,
            "raw_title": title,
            "raw_price_text": price,
            "raw_unit_text": unit,
            "raw_terms": terms,
            "raw_payload": entry,
            "source_url": document.get("source_url") or entry.get("source_url"),
            "payload_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        })
    return output


def _normalize_market_price(
    price: dict[str, Any],
    catalog: list[dict[str, Any]],
    vendors: dict[str, dict[str, Any]],
    snapshot_id: str,
    default_source_label: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Keep auditable marketplace rows and quarantine non-exact SKU matches."""
    normalized = dict(price)
    product_id = normalized.get("product_id")
    supplier_id = normalized.get("supplier_id")
    item = next((entry for entry in catalog if entry.get("id") == product_id), None)
    supplier = vendors.get(supplier_id)
    is_digikala = supplier_id == "digikala" or normalized.get("source_label") == "digikala_business_capture"
    if not product_id or item is None or not supplier_id or supplier is None:
        normalized["match_status"] = "rejected_invalid_reference"
        normalized["rejection_reason"] = "UNKNOWN_PRODUCT_OR_SUPPLIER"
        return None, normalized
    if is_digikala and (
        normalized.get("match_status") != "exact"
        or not exact_sku_match(item, normalized.get("raw_title", ""))
    ):
        normalized["match_status"] = "rejected_model_mismatch"
        normalized["rejection_reason"] = "SKU_MISMATCH"
        return None, normalized

    normalized.setdefault("source_snapshot_id", snapshot_id)
    normalized.setdefault("source_label", default_source_label)
    normalized.setdefault("valid_at", normalized.get("captured_at"))
    normalized.setdefault("source_record_id", normalized.get("id"))
    normalized.setdefault("raw_title", None)
    normalized.setdefault("raw_price_text", None)
    normalized.setdefault("price_status", "observed" if normalized.get("price_irr") is not None else "unknown")
    if normalized.get("price_irr") == 0:
        normalized["price_irr"] = None
        normalized["price_status"] = "unavailable"
    normalized.setdefault("stock_status", "not_reported")
    normalized.setdefault("availability_status", "observed" if normalized.get("is_available", True) else "unavailable")
    normalized.setdefault("field_status", {
        "price_irr": normalized.get("price_status", "unknown"),
        "raw_price_text": "observed" if normalized.get("raw_price_text") is not None else "not_reported",
        "stock_packages": normalized.get("stock_status", "not_reported"),
        "package_size_base": "observed" if normalized.get("package_size_base") is not None else "not_reported",
        "lead_days": "observed" if normalized.get("lead_days") is not None else "not_reported",
        "source_url": "observed" if normalized.get("source_url") else "not_reported",
        "captured_at": "observed" if normalized.get("valid_at") else "not_reported",
    })
    return normalized, None


def load_dataset(path: str | Path) -> dict[str, Any]:
    """Read and normalize a versioned local snapshot, preserving every raw row."""
    with Path(path).open(encoding="utf-8") as handle:
        source = json.load(handle)
    if source.get("kind") != "synthetic":
        raise ValueError("this importer currently accepts only explicit synthetic snapshots")
    snapshot_id = source["id"]
    market_catalog = source.get("market_catalog") or {}
    catalog = [*source["catalog"], *market_catalog.get("products", [])]
    vendors = [*source["vendors"], *market_catalog.get("vendors", [])]
    documents = source["source_documents"]
    if len({item["id"] for item in catalog}) != len(catalog):
        raise ValueError("duplicate catalog IDs")
    if len({vendor["id"] for vendor in vendors}) != len(vendors):
        raise ValueError("duplicate vendor IDs")
    raw_offers = [record for document in documents for record in _raw_records(document, snapshot_id)]
    if len({record["id"] for record in raw_offers}) != len(raw_offers):
        raise ValueError("duplicate raw record IDs")
    vendor_index = {vendor["id"]: vendor for vendor in vendors}
    offers = [_normalize(record, catalog, vendor_index) for record in raw_offers]
    result = {key: source[key] for key in ("id", "version", "captured_at", "kind", "rules_version")}
    canonical_payload = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result["content_hash"] = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    market_prices: list[dict[str, Any]] = []
    rejected_market_prices: list[dict[str, Any]] = []
    for market_price in market_catalog.get("prices", []):
        normalized_market, rejected_market = _normalize_market_price(
            market_price,
            catalog,
            vendor_index,
            snapshot_id,
            market_catalog.get("source_label", "market_capture"),
        )
        if normalized_market is not None:
            market_prices.append(normalized_market)
        if rejected_market is not None:
            rejected_market_prices.append(rejected_market)
    result.update({
        "category_tree": source.get("category_tree", []),
        "catalog": catalog,
        "vendors": vendors,
        "raw_offers": raw_offers,
        "offers": offers,
        "market_prices": market_prices,
        "rejected_market_prices": rejected_market_prices,
        "decision_layer": source.get("decision_layer", {}),
    })
    return result


def load_demo() -> dict[str, Any]:
    """Load the bundled fixture regardless of the process working directory."""
    return load_dataset(Path(__file__).resolve().parents[2] / "data" / "demo_raw.json")
