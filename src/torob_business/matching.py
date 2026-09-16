"""Conservative catalog search for a multi-line purchasing query."""

from __future__ import annotations

import re
import unicodedata


_CHAR_MAP = str.maketrans(
    {
        **dict(zip("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")),
        "ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "‌": " ", "٫": ".",
    }
)


def normalize_query(value: str) -> str:
    """Normalize spelling enough for search without inventing product attributes."""
    value = unicodedata.normalize("NFKC", value).translate(_CHAR_MAP).casefold()
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return " ".join(re.findall(r"[\w]+", value, flags=re.UNICODE))


def search_catalog(snapshot: dict, query: str) -> list[dict]:
    """Return exact then partial SKU candidates and their usable offer counts.

    Partial matches are discovery hints only. They never auto-resolve an RFQ line.
    """
    needle = normalize_query(query)
    if not needle:
        return []
    usable_counts: dict[str, int] = {}
    for offer in snapshot.get("offers", []):
        if offer.get("normalization_status") == "accepted":
            sku = offer.get("catalog_item_id")
            if sku:
                usable_counts[sku] = usable_counts.get(sku, 0) + 1
    found = []
    for item in snapshot.get("catalog", []):
        terms = {normalize_query(item["name"])}
        terms.update(normalize_query(a) for a in item.get("aliases", []))
        terms.discard("")
        if needle in terms:
            kind = "exact"
        elif any(needle in term.split() or needle in term for term in terms):
            kind = "partial"
        else:
            continue
        found.append(
            {
                "catalog_item_id": item["id"],
                "name": item["name"],
                "category": item["category"],
                "base_unit": item["base_unit"],
                "match_kind": kind,
                "offer_count": usable_counts.get(item["id"], 0),
            }
        )
    return sorted(found, key=lambda row: (row["match_kind"] != "exact", row["catalog_item_id"]))


def resolve_rfq(snapshot: dict, rfq: dict) -> dict:
    """Resolve only explicit IDs or a single exact alias; surface all ambiguity."""
    catalog_by_id = {item["id"]: item for item in snapshot.get("catalog", [])}
    lines = rfq.get("lines", [])
    if not isinstance(lines, list) or not lines:
        raise ValueError("RFQ needs at least one line")
    resolved = []
    matches = []
    for line in lines:
        line_id = line.get("id")
        qty = line.get("qty_base")
        if not isinstance(line_id, str) or not line_id:
            raise ValueError("Each RFQ line needs an id")
        if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            raise ValueError(f"RFQ line {line_id} needs a positive integer qty_base")
        selected = line.get("catalog_item_id")
        if selected is not None:
            if selected not in catalog_by_id:
                raise ValueError(f"Unknown catalog_item_id: {selected}")
            requested_specs = line.get("requested_specs") or {}
            if not isinstance(requested_specs, dict):
                raise ValueError(f"RFQ line {line_id} requested_specs must be an object")
            item_specs = catalog_by_id[selected].get("specs", {})
            if any(item_specs.get(key) != value for key, value in requested_specs.items()):
                raise ValueError(f"RFQ line {line_id} has specs incompatible with {selected}")
            query = line.get("query_text", "")
            if normalize_query(query):
                search_matches = search_catalog(snapshot, query)
                exact_ids = {match["catalog_item_id"] for match in search_matches if match["match_kind"] == "exact"}
                compatible_ids = exact_ids or {match["catalog_item_id"] for match in search_matches}
                if selected not in compatible_ids:
                    raise ValueError(f"RFQ line {line_id} query is incompatible with {selected}")
            status = "confirmed"
            candidates = [selected]
            method = "explicit_selection"
        else:
            candidates_data = search_catalog(snapshot, line.get("query_text", ""))
            candidates = [c["catalog_item_id"] for c in candidates_data]
            exact = [c for c in candidates_data if c["match_kind"] == "exact"]
            if len(exact) == 1:
                selected = exact[0]["catalog_item_id"]
                status = "confirmed"
                method = "unique_exact_alias"
            elif candidates:
                status = "ambiguous"
                method = "manual_selection_required"
            else:
                status = "unmatched"
                method = "no_candidate"
        matches.append(
            {
                "line_id": line_id,
                "status": status,
                "candidate_catalog_ids": candidates,
                "selected_catalog_id": selected,
                "method": method,
            }
        )
        if selected is not None:
            resolved.append({"id": line_id, "catalog_item_id": selected, "qty_base": qty})
    output = dict(rfq)
    output["lines"] = resolved
    return {
        "status": "ready" if all(m["status"] == "confirmed" for m in matches) else "needs_match",
        "rfq": output,
        "matches": matches,
    }
