"""Project complete marketplace captures into the deterministic demo ranker.

Marketplace captures can be useful for provenance/comparison while still being
unfit for basket ranking. This module promotes only rows that already contain
every commercial term required by the ranker. It never fills missing values.
"""

from __future__ import annotations

from typing import Any


def _integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _complete_market_offer(price: dict[str, Any], vendors: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if price.get("price_status") == "unavailable" or price.get("is_available") is False:
        return None
    product_id = price.get("product_id")
    supplier_id = price.get("supplier_id")
    vendor = vendors.get(supplier_id)
    if not product_id or not supplier_id or vendor is None:
        return None
    if supplier_id == "digikala" and price.get("match_status") != "exact":
        return None
    required = {
        "price_irr": price.get("price_irr"),
        "package_size_base": price.get("package_size_base"),
        "min_packages": price.get("min_packages"),
        "package_step": price.get("package_step"),
        "stock_packages": price.get("stock_packages"),
        "lead_days": price.get("lead_days"),
        "shipping_irr": vendor.get("shipping_irr"),
        "minimum_order_irr": vendor.get("minimum_order_irr"),
    }
    if not _integer(required["price_irr"], 1):
        return None
    if not _integer(required["package_size_base"], 1):
        return None
    if not _integer(required["min_packages"], 1):
        return None
    if not _integer(required["package_step"], 1):
        return None
    if not _integer(required["stock_packages"]):
        return None
    if not _integer(required["lead_days"]):
        return None
    if not _integer(required["shipping_irr"]):
        return None
    if not _integer(required["minimum_order_irr"]):
        return None
    if price.get("tax_status") not in {"included", "tax_included", "declared_included", "verified_included"}:
        return None
    return {
        "id": price["id"],
        "raw_record_id": price.get("source_record_id") or price["id"],
        "vendor_id": supplier_id,
        "catalog_item_id": product_id,
        "package_size_base": price["package_size_base"],
        "package_price_irr": price["price_irr"],
        "min_packages": price["min_packages"],
        "package_step": price["package_step"],
        "stock_packages": price["stock_packages"],
        "lead_days": price["lead_days"],
        "invoice_status": price.get("invoice_status", "unknown"),
        "tax_status": price["tax_status"],
        "normalization_status": "accepted",
        "rejection_reason": None,
        "normalization_steps": ["market_price_projection:complete_terms"],
        "source_snapshot_id": price.get("source_snapshot_id"),
        "source_record_id": price.get("source_record_id"),
        "source_url": price.get("source_url"),
        "source_label": price.get("source_label"),
        "raw_title": price.get("raw_title"),
        "raw_price_text": price.get("raw_price_text"),
    }


def rankable_offers(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Return accepted legacy offers plus fully specified market captures."""
    offers = [
        offer for offer in snapshot.get("offers", [])
        if offer.get("normalization_status") == "accepted" and offer.get("catalog_item_id")
    ]
    existing_ids = {offer.get("id") for offer in offers}
    vendors = {vendor.get("id"): vendor for vendor in snapshot.get("vendors", [])}
    for price in snapshot.get("market_prices", []):
        projected = _complete_market_offer(price, vendors)
        if projected is not None and projected["id"] not in existing_ids:
            offers.append(projected)
    return offers


def rankable_catalog_ids(snapshot: dict[str, Any]) -> set[str]:
    return {offer["catalog_item_id"] for offer in rankable_offers(snapshot)}


def rankable_offer_counts(snapshot: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for offer in rankable_offers(snapshot):
        sku = offer["catalog_item_id"]
        counts[sku] = counts.get(sku, 0) + 1
    return counts
