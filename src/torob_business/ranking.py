"""Deterministic, side-effect-free ranking of a small sourcing snapshot.

The result only ranks complete, eligible baskets. All money is integer IRR;
unknown commercial terms fail closed instead of being treated as zero.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import defaultdict
from typing import Any


ALGORITHM_VERSION = "ranking-v1"
_INCLUDED_TAX = {"included", "tax_included", "declared_included", "verified_included"}
_INVOICE_YES = {"declared_yes", "verified_yes"}


def _integer(value: Any, *, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _records(value: Any) -> list[dict]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _canonical(value: Any) -> Any:
    """Remove incidental list order from records identified by a unique id."""
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        items = [_canonical(item) for item in value]
        if all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in items):
            items.sort(key=lambda item: item["id"])
        return items
    return value


def _input_hash(snapshot: dict, rfq: dict) -> str:
    payload = {"algorithm_version": ALGORITHM_VERSION, "snapshot": snapshot, "rfq": rfq}
    encoded = json.dumps(_canonical(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_rfq(rfq: dict, max_combinations: int) -> None:
    if not _integer(max_combinations, minimum=1):
        raise ValueError("max_combinations must be a positive integer")
    if rfq.get("preference") not in {"lowest_cost", "fastest_delivery"}:
        raise ValueError("preference must be lowest_cost or fastest_delivery")
    lines = rfq.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError("RFQ must contain at least one line")
    ids: set[str] = set()
    for line in lines:
        if not isinstance(line, dict) or not isinstance(line.get("id"), str) or not line["id"]:
            raise ValueError("each RFQ line needs a nonempty id")
        if line["id"] in ids:
            raise ValueError("RFQ line ids must be unique")
        ids.add(line["id"])
        if not isinstance(line.get("catalog_item_id"), str) or not line["catalog_item_id"]:
            raise ValueError("each RFQ line needs a catalog_item_id")
        if not _integer(line.get("qty_base"), minimum=1):
            raise ValueError("each RFQ quantity must be a positive integer")
    for field in ("budget_irr", "max_lead_days"):
        if rfq.get(field) is not None and not _integer(rfq[field]):
            raise ValueError(f"{field} must be a nonnegative integer or null")
    if type(rfq.get("requires_declared_invoice", False)) is not bool:
        raise ValueError("requires_declared_invoice must be a boolean")


def _provenance(offer: dict, raw_by_id: dict[str, dict], snapshot: dict) -> dict:
    raw = raw_by_id.get(offer.get("raw_record_id"), {})
    return {
        "snapshot_id": snapshot.get("id"),
        "raw_record_id": offer.get("raw_record_id"),
        "source_label": raw.get("source_label"),
        "source_record_id": raw.get("source_record_id"),
        "source_url": raw.get("source_url"),
        "generated_at": raw.get("generated_at"),
        "observed_at": raw.get("observed_at"),
        "payload_hash": raw.get("payload_hash"),
        "normalization_steps": offer.get("normalization_steps", []),
    }


def _candidate(offer: dict, group: dict, vendor: dict | None, invoice_required: bool) -> tuple[dict | None, list[str]]:
    reasons: list[str] = []
    if not isinstance(offer.get("id"), str) or not offer["id"]:
        reasons.append("UNKNOWN_OFFER_ID")
    if not isinstance(offer.get("vendor_id"), str) or not offer["vendor_id"]:
        reasons.append("UNKNOWN_VENDOR")
    if offer.get("normalization_status") != "accepted":
        reasons.append(offer.get("rejection_reason") or "OFFER_REJECTED")
    if vendor is None:
        reasons.append("UNKNOWN_VENDOR")
    elif not _integer(vendor.get("shipping_irr")):
        reasons.append("UNKNOWN_SHIPPING")
    if vendor is not None and not _integer(vendor.get("minimum_order_irr")):
        reasons.append("UNKNOWN_MINIMUM_ORDER")
    package_size = offer.get("package_size_base")
    price = offer.get("package_price_irr")
    minimum = offer.get("min_packages")
    step = offer.get("package_step")
    stock = offer.get("stock_packages")
    lead = offer.get("lead_days")
    if not _integer(package_size, minimum=1):
        reasons.append("UNKNOWN_PACKAGE_SIZE")
    if not _integer(price, minimum=1):
        reasons.append("UNKNOWN_PRICE")
    if not _integer(minimum):
        reasons.append("UNKNOWN_MIN_PACKAGES")
    if not _integer(step, minimum=1):
        reasons.append("UNKNOWN_PACKAGE_STEP")
    if not _integer(stock):
        reasons.append("UNKNOWN_STOCK")
    if not _integer(lead):
        reasons.append("UNKNOWN_LEAD_TIME")
    if offer.get("tax_status") not in _INCLUDED_TAX:
        reasons.append("UNKNOWN_TAX")
    if invoice_required and offer.get("invoice_status") not in _INVOICE_YES:
        reasons.append("INVOICE_NOT_DECLARED")
    if reasons:
        return None, sorted(set(reasons))

    # ceil(q/p), then round up to the next valid package step after minimum.
    needed = (group["requested_qty_base"] + package_size - 1) // package_size
    packages = minimum + step * max(0, (max(0, needed - minimum) + step - 1) // step)
    if packages > stock:
        return None, ["INSUFFICIENT_STOCK"]
    covered = packages * package_size
    return {
        "line_ids": group["line_ids"],
        "catalog_item_id": group["catalog_item_id"],
        "offer_id": offer["id"],
        "raw_record_id": offer.get("raw_record_id"),
        "vendor_id": offer["vendor_id"],
        "requested_qty_base": group["requested_qty_base"],
        "purchased_packages": packages,
        "covered_qty_base": covered,
        "overbuy_qty_base": covered - group["requested_qty_base"],
        "package_price_irr": price,
        "line_total_irr": packages * price,
        "lead_days": lead,
        "invoice_status": offer.get("invoice_status"),
        "tax_status": offer.get("tax_status"),
    }, []


def _sort_key(combination: dict, preference: str) -> tuple:
    tail = (combination["vendor_count"], tuple(combination["offer_ids"]))
    if preference == "lowest_cost":
        return (combination["total_irr"], combination["max_lead_days"], *tail)
    return (combination["max_lead_days"], combination["total_irr"], *tail)


def _reason(combination: dict, comparator: dict | None, preference: str) -> dict:
    metric = "total_irr" if preference == "lowest_cost" else "max_lead_days"
    result = {"criterion": metric, "value": combination[metric], "offer_ids": combination["offer_ids"]}
    if comparator is not None:
        result["compared_to_offer_ids"] = comparator["offer_ids"]
        result["difference"] = abs(combination[metric] - comparator[metric])
        result["difference_unit"] = "IRR" if metric == "total_irr" else "days"
        if result["difference"] == 0:
            result["tie_break"] = "max_lead_days,total_irr,vendor_count,offer_ids" if preference == "lowest_cost" else "total_irr,vendor_count,offer_ids"
    return result


def evaluate(snapshot: dict, rfq: dict, max_combinations: int = 10000) -> dict:
    """Evaluate every complete basket up to the search cap.

    Invalid RFQs raise ValueError; unavailable/unknown offer terms become
    structured domain exclusions. No input object is modified.
    """
    if not isinstance(snapshot, dict) or not isinstance(rfq, dict):
        raise ValueError("snapshot and rfq must be dictionaries")
    _validate_rfq(rfq, max_combinations)
    snapshot_id = snapshot.get("id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("snapshot needs a nonempty id")

    result = {
        "status": "ok",
        "snapshot_id": snapshot_id,
        "data_kind": snapshot.get("kind"),
        "algorithm_version": ALGORITHM_VERSION,
        "input_hash": _input_hash(snapshot, rfq),
        "preference": rfq["preference"],
        "search_exhaustive": True,
        "enumerated_combinations": 0,
        "combinations": [],
        "excluded_reasons": [],
        "uncovered_lines": [],
    }
    catalog_ids = {item["id"] for item in _records(snapshot.get("catalog")) if isinstance(item, dict) and "id" in item}
    vendors = {item["id"]: item for item in _records(snapshot.get("vendors")) if isinstance(item, dict) and "id" in item}
    raw_by_id = {item["id"]: item for item in _records(snapshot.get("raw_offers")) if isinstance(item, dict) and "id" in item}
    offers = sorted(
        (item for item in _records(snapshot.get("offers")) if isinstance(item, dict)),
        key=lambda item: str(item.get("id", "")),
    )

    groups_by_sku: dict[str, dict] = {}
    for line in rfq["lines"]:
        sku = line["catalog_item_id"]
        group = groups_by_sku.setdefault(sku, {"catalog_item_id": sku, "line_ids": [], "requested_qty_base": 0})
        group["line_ids"].append(line["id"])
        group["requested_qty_base"] += line["qty_base"]
    groups = sorted(groups_by_sku.values(), key=lambda group: group["catalog_item_id"])
    for group in groups:
        group["line_ids"].sort()

    choices: list[list[dict]] = []
    for group in groups:
        sku = group["catalog_item_id"]
        candidates: list[dict] = []
        matching_offers = [offer for offer in offers if offer.get("catalog_item_id") == sku]
        if sku not in catalog_ids:
            result["uncovered_lines"].append({"line_ids": group["line_ids"], "catalog_item_id": sku, "reason_codes": ["UNKNOWN_CATALOG_ITEM"]})
            choices.append([])
            continue
        for offer in matching_offers:
            vendor = vendors.get(offer.get("vendor_id"))
            candidate, reasons = _candidate(offer, group, vendor, rfq.get("requires_declared_invoice", False))
            if reasons:
                result["excluded_reasons"].append({
                    "line_ids": group["line_ids"], "catalog_item_id": sku,
                    "offer_ids": [offer.get("id")], "reason_codes": reasons,
                    "provenance": _provenance(offer, raw_by_id, snapshot),
                })
            else:
                candidate["provenance"] = _provenance(offer, raw_by_id, snapshot)
                candidates.append(candidate)
        if not candidates:
            if sku not in catalog_ids:
                codes = ["UNKNOWN_CATALOG_ITEM"]
            elif not matching_offers:
                codes = ["NO_OFFERS"]
            else:
                codes = sorted({code for entry in result["excluded_reasons"] if entry["catalog_item_id"] == sku for code in entry["reason_codes"]})
            result["uncovered_lines"].append({"line_ids": group["line_ids"], "catalog_item_id": sku, "reason_codes": codes})
        choices.append(candidates)

    if result["uncovered_lines"]:
        result["status"] = "no_full_coverage"
        return result

    combination_count = math.prod(len(group_choices) for group_choices in choices)
    if combination_count > max_combinations:
        result["status"] = "search_limit"
        result["search_exhaustive"] = False
        result["excluded_reasons"].append({"reason_codes": ["SEARCH_LIMIT"], "possible_combinations": combination_count, "max_combinations": max_combinations})
        return result

    for assignments_tuple in itertools.product(*choices):
        result["enumerated_combinations"] += 1
        assignments = list(assignments_tuple)
        offer_ids = sorted(assignment["offer_id"] for assignment in assignments)
        subtotals: dict[str, int] = defaultdict(int)
        for assignment in assignments:
            subtotals[assignment["vendor_id"]] += assignment["line_total_irr"]
        codes: list[str] = []
        for vendor_id, subtotal in subtotals.items():
            if subtotal < vendors[vendor_id]["minimum_order_irr"]:
                codes.append("BELOW_VENDOR_MINIMUM_ORDER")
        shipping = sum(vendors[vendor_id]["shipping_irr"] for vendor_id in subtotals)
        total = sum(subtotals.values()) + shipping
        lead = max(assignment["lead_days"] for assignment in assignments)
        if rfq.get("max_lead_days") is not None and lead > rfq["max_lead_days"]:
            codes.append("EXCEEDS_MAX_LEAD_DAYS")
        if rfq.get("budget_irr") is not None and total > rfq["budget_irr"]:
            codes.append("EXCEEDS_BUDGET")
        if codes:
            result["excluded_reasons"].append({"offer_ids": offer_ids, "reason_codes": sorted(set(codes)), "total_irr": total, "max_lead_days": lead})
            continue
        result["combinations"].append({
            "rank": 0,
            "offer_ids": offer_ids,
            "assignments": assignments,
            "vendor_subtotals": dict(sorted(subtotals.items())),
            "shipping_total_irr": shipping,
            "total_irr": total,
            "max_lead_days": lead,
            "vendor_count": len(subtotals),
            "reason_codes": [],
            "reason": {},
        })

    if not result["combinations"]:
        result["status"] = "no_full_coverage"
        return result
    result["combinations"].sort(key=lambda combination: _sort_key(combination, rfq["preference"]))
    for index, combination in enumerate(result["combinations"]):
        combination["rank"] = index + 1
        comparator = result["combinations"][1] if index == 0 and len(result["combinations"]) > 1 else result["combinations"][0] if index else None
        combination["reason"] = _reason(combination, comparator, rfq["preference"])
        combination["reason_codes"] = ["LOWEST_COST" if rfq["preference"] == "lowest_cost" else "FASTEST_DELIVERY"]
        if comparator is not None and combination["reason"]["difference"] == 0:
            combination["reason_codes"].append("TIE_BREAK")
    return result
