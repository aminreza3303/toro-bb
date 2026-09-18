"""SQLite catalog storage for products, suppliers, and per-supplier prices.

The source snapshot remains the auditable import format.  This module turns the
normalized snapshot into three relational views used by the storefront:
``products``, ``suppliers`` and ``product_prices``.  The Digikala supplier is
always present with the exact display name ``دیجی کالا``; a missing price is
represented as NULL instead of an invented value.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .matching import normalize_query


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    category_path_json TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    base_unit TEXT NOT NULL,
    specs_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_contexts (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    keywords_json TEXT NOT NULL,
    questions_json TEXT NOT NULL,
    checks_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_profiles (
    product_id TEXT PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    context_id TEXT NOT NULL REFERENCES decision_contexts(id) ON DELETE CASCADE,
    variant_group TEXT NOT NULL,
    fitment_status TEXT NOT NULL,
    summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_claims (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    label TEXT NOT NULL,
    value_text TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_ref TEXT,
    observed_at TEXT,
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS supplier_evidence (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    supplier_id TEXT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    signal TEXT NOT NULL,
    label TEXT NOT NULL,
    value_text TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_ref TEXT,
    observed_at TEXT,
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS product_prices (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    supplier_id TEXT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    price_irr INTEGER,
    package_size_base INTEGER,
    min_packages INTEGER,
    package_step INTEGER,
    stock_packages INTEGER,
    lead_days INTEGER,
    invoice_status TEXT NOT NULL,
    tax_status TEXT NOT NULL,
    source_snapshot_id TEXT,
    source_record_id TEXT,
    valid_at TEXT,
    source_url TEXT,
    source_label TEXT,
    raw_title TEXT,
    raw_price_text TEXT,
    field_status_json TEXT NOT NULL DEFAULT '{}',
    price_status TEXT NOT NULL DEFAULT 'unknown',
    stock_status TEXT NOT NULL DEFAULT 'unknown',
    availability_status TEXT NOT NULL DEFAULT 'unknown',
    match_status TEXT NOT NULL DEFAULT 'unknown',
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
    UNIQUE(product_id, supplier_id, source_record_id)
);

CREATE INDEX IF NOT EXISTS idx_product_prices_product ON product_prices(product_id);
CREATE INDEX IF NOT EXISTS idx_product_prices_supplier ON product_prices(supplier_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
"""


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


_CLAIM_LABELS = {
    "brand": "برند",
    "model": "مدل",
    "capacity": "ظرفیت",
    "interface": "رابط",
    "connection": "اتصال",
    "size_inches": "اندازهٔ نمایشگر",
    "condition": "وضعیت کالا",
    "type": "نوع کالا",
    "backrest": "پشتی",
    "color": "رنگ",
    "tip_mm": "ضخامت نوک",
    "size": "اندازه",
    "weight_gsm": "گرماژ",
    "sheets_per_ream": "تعداد برگ",
}


def _claim_value(value: Any) -> str:
    if isinstance(value, bool):
        return "بله" if value else "خیر"
    if isinstance(value, (list, tuple)):
        return "، ".join(str(item) for item in value)
    return str(value)


class CatalogDatabase:
    """Small relational catalog store backed by SQLite."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Add provenance columns to an existing local demo database."""
        columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(product_prices)").fetchall()
        }
        additions = {
            "source_label": "TEXT",
            "raw_title": "TEXT",
            "raw_price_text": "TEXT",
            "field_status_json": "TEXT NOT NULL DEFAULT '{}'",
            "price_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "stock_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "availability_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "match_status": "TEXT NOT NULL DEFAULT 'unknown'",
        }
        with self.connection:
            for name, definition in additions.items():
                if name not in columns:
                    self.connection.execute(f"ALTER TABLE product_prices ADD COLUMN {name} {definition}")

    def close(self) -> None:
        self.connection.close()

    def sync_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Replace the relational projection with one normalized snapshot."""
        conn = self.connection
        with conn:
            conn.execute("DELETE FROM supplier_evidence")
            conn.execute("DELETE FROM product_claims")
            conn.execute("DELETE FROM decision_profiles")
            conn.execute("DELETE FROM decision_contexts")
            conn.execute("DELETE FROM product_prices")
            conn.execute("DELETE FROM products")
            conn.execute("DELETE FROM suppliers")
            suppliers_by_id = {
                vendor["id"]: (
                    vendor["id"],
                    vendor["name"],
                    vendor.get("kind", "supplier"),
                    vendor.get("source", "snapshot"),
                )
                for vendor in snapshot.get("vendors", [])
            }
            suppliers_by_id.setdefault("digikala", ("digikala", "دیجی کالا", "marketplace", "digikala_business"))
            conn.executemany(
                "INSERT INTO suppliers(id, name, kind, source) VALUES (?, ?, ?, ?)",
                list(suppliers_by_id.values()),
            )
            conn.executemany(
                """INSERT INTO products
                   (id, name, category, category_path_json, aliases_json, base_unit, specs_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        item["id"],
                        item["name"],
                        item.get("category", "کالا"),
                        _json(item.get("category_path") or [item.get("category", "کالا")]),
                        _json(item.get("aliases", [])),
                        item.get("base_unit", "عدد"),
                        _json(item.get("specs", {})),
                    )
                    for item in snapshot.get("catalog", [])
                ],
            )
            decision_layer = snapshot.get("decision_layer") or {}
            contexts = decision_layer.get("contexts", [])
            profiles = decision_layer.get("profiles", [])
            profile_by_product = {profile.get("product_id"): profile for profile in profiles}
            conn.executemany(
                """INSERT INTO decision_contexts
                   (id, domain, title, summary, keywords_json, questions_json, checks_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        context["id"],
                        context.get("domain", "general"),
                        context.get("title", "راهنمای انتخاب"),
                        context.get("summary", ""),
                        _json(context.get("keywords", [])),
                        _json(context.get("questions", [])),
                        _json(context.get("checks_before_buying", [])),
                    )
                    for context in contexts
                ],
            )
            conn.executemany(
                """INSERT INTO decision_profiles
                   (product_id, context_id, variant_group, fitment_status, summary)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        profile["product_id"],
                        profile["context_id"],
                        profile.get("variant_group", profile["product_id"]),
                        profile.get("fitment_status", "unknown"),
                        profile.get("summary", ""),
                    )
                    for profile in profiles
                    if profile.get("product_id") and profile.get("context_id")
                ],
            )
            items_by_id = {item["id"]: item for item in snapshot.get("catalog", [])}
            claim_rows = []
            for product_id, profile in profile_by_product.items():
                item = items_by_id.get(product_id, {})
                configured_claims = profile.get("claims", [])
                if configured_claims:
                    claims = configured_claims
                else:
                    claims = [
                        {
                            "field": field,
                            "label": _CLAIM_LABELS.get(field, field),
                            "value": value,
                            "status": "confirmed",
                            "evidence_type": "catalog_spec",
                            "evidence_ref": f"catalog:{product_id}.specs.{field}",
                        }
                        for field, value in item.get("specs", {}).items()
                    ]
                for index, claim in enumerate(claims, start=1):
                    if claim.get("field") is None or claim.get("value") is None:
                        continue
                    claim_rows.append(
                        (
                            claim.get("id", f"claim-{product_id}-{claim['field']}-{index}"),
                            product_id,
                            claim["field"],
                            claim.get("label", _CLAIM_LABELS.get(claim["field"], claim["field"])),
                            _claim_value(claim["value"]),
                            claim.get("status", "unknown"),
                            claim.get("evidence_type", "catalog_spec"),
                            claim.get("evidence_ref"),
                            claim.get("observed_at", snapshot.get("captured_at")),
                            claim.get("source_url"),
                        )
                    )
            conn.executemany(
                """INSERT INTO product_claims
                   (id, product_id, field, label, value_text, status,
                    evidence_type, evidence_ref, observed_at, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                claim_rows,
            )
            conn.executemany(
                """INSERT INTO product_prices
                   (id, product_id, supplier_id, price_irr, package_size_base,
                   min_packages, package_step, stock_packages, lead_days,
                   invoice_status, tax_status, source_snapshot_id,
                   source_record_id, valid_at, source_url, source_label,
                   raw_title, raw_price_text, field_status_json, price_status,
                   stock_status, availability_status, match_status, is_available)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        offer["id"],
                        offer["catalog_item_id"],
                        offer["vendor_id"],
                        offer.get("package_price_irr"),
                        offer.get("package_size_base"),
                        offer.get("min_packages"),
                        offer.get("package_step"),
                        offer.get("stock_packages"),
                        offer.get("lead_days"),
                        offer.get("invoice_status", "unknown"),
                        offer.get("tax_status", "unknown"),
                        snapshot.get("id"),
                        offer.get("raw_record_id"),
                        offer.get("valid_at"),
                        offer.get("source_url"),
                        offer.get("source_label"),
                        offer.get("raw_title"),
                        offer.get("raw_price_text"),
                        _json(offer.get("field_status", {})),
                        offer.get("price_status", "unknown"),
                        offer.get("stock_status", "unknown"),
                        offer.get("availability_status", "unknown"),
                        offer.get("match_status", "unknown"),
                        1,
                    )
                    for offer in snapshot.get("offers", [])
                    if offer.get("normalization_status") == "accepted"
                    and offer.get("catalog_item_id")
                ],
            )
            evidence_rows = []
            supplier_by_id = {vendor["id"]: vendor for vendor in snapshot.get("vendors", [])}
            for price in [
                offer for offer in snapshot.get("offers", [])
                if offer.get("normalization_status") == "accepted" and offer.get("catalog_item_id")
            ] + [
                price for price in snapshot.get("market_prices", [])
                if price.get("product_id") and price.get("supplier_id")
            ]:
                product_id = price.get("catalog_item_id") or price.get("product_id")
                supplier_id = price.get("vendor_id") or price.get("supplier_id")
                supplier = supplier_by_id.get(supplier_id, {})
                evidence_rows.append(
                    (
                        f"supplier-evidence-{price['id']}",
                        product_id,
                        supplier_id,
                        "price_source",
                        "منشأ قیمت",
                        f"قیمت ثبت‌شده در {supplier.get('name', supplier_id)}",
                        "observed",
                        price.get("id"),
                        price.get("valid_at", snapshot.get("captured_at")),
                        price.get("source_url"),
                    )
                )
            conn.executemany(
                """INSERT INTO supplier_evidence
                   (id, product_id, supplier_id, signal, label, value_text,
                    status, evidence_ref, observed_at, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                evidence_rows,
            )
            conn.executemany(
                """INSERT INTO product_prices
                   (id, product_id, supplier_id, price_irr, package_size_base,
                   min_packages, package_step, stock_packages, lead_days,
                   invoice_status, tax_status, source_snapshot_id,
                   source_record_id, valid_at, source_url, source_label,
                   raw_title, raw_price_text, field_status_json, price_status,
                   stock_status, availability_status, match_status, is_available)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        price["id"],
                        price["product_id"],
                        price["supplier_id"],
                        price.get("price_irr"),
                        price.get("package_size_base", 1),
                        price.get("min_packages"),
                        price.get("package_step"),
                        price.get("stock_packages"),
                        price.get("lead_days"),
                        price.get("invoice_status", "unknown"),
                        price.get("tax_status", "unknown"),
                        price.get("source_snapshot_id", snapshot.get("id")),
                        price.get("source_record_id"),
                        price.get("valid_at", snapshot.get("captured_at")),
                        price.get("source_url"),
                        price.get("source_label"),
                        price.get("raw_title"),
                        price.get("raw_price_text"),
                        _json(price.get("field_status", {})),
                        price.get("price_status", "unknown"),
                        price.get("stock_status", "unknown"),
                        price.get("availability_status", "unknown"),
                        price.get("match_status", "unknown"),
                        1 if price.get("is_available", True) else 0,
                    )
                    for price in snapshot.get("market_prices", [])
                    if price.get("product_id") and price.get("supplier_id")
                ],
            )

    @staticmethod
    def _product(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "category_path": _loads(row["category_path_json"], [row["category"]]),
            "aliases": _loads(row["aliases_json"], []),
            "base_unit": row["base_unit"],
            "specs": _loads(row["specs_json"], {}),
        }

    def _decision_for_product(self, product_id: str) -> dict[str, Any] | None:
        profile = self.connection.execute(
            """SELECT dp.product_id, dp.context_id, dp.variant_group,
                      dp.fitment_status, dp.summary, dc.domain, dc.title,
                      dc.summary AS context_summary, dc.questions_json,
                      dc.checks_json
               FROM decision_profiles dp
               JOIN decision_contexts dc ON dc.id = dp.context_id
               WHERE dp.product_id = ?""",
            (product_id,),
        ).fetchone()
        if profile is None:
            return None
        claims = self.connection.execute(
            """SELECT id, field, label, value_text, status, evidence_type,
                      evidence_ref, observed_at, source_url
               FROM product_claims WHERE product_id = ? ORDER BY id""",
            (product_id,),
        ).fetchall()
        evidence = self.connection.execute(
            """SELECT se.id, se.supplier_id, s.name AS supplier_name,
                      se.signal, se.label, se.value_text, se.status,
                      se.evidence_ref, se.observed_at, se.source_url
               FROM supplier_evidence se
               JOIN suppliers s ON s.id = se.supplier_id
               WHERE se.product_id = ? ORDER BY se.observed_at DESC, se.id""",
            (product_id,),
        ).fetchall()
        group_rows = self.connection.execute(
            """SELECT dp.product_id, p.name
               FROM decision_profiles dp
               JOIN products p ON p.id = dp.product_id
               WHERE dp.context_id = ? AND dp.variant_group = ?
               ORDER BY p.name""",
            (profile["context_id"], profile["variant_group"]),
        ).fetchall()
        group_ids = [row["product_id"] for row in group_rows]
        claim_rows = self.connection.execute(
            """SELECT pc.product_id, pc.field, pc.label, pc.value_text
               FROM product_claims pc
               WHERE pc.product_id IN ({})
               ORDER BY pc.field, pc.product_id""".format(",".join("?" for _ in group_ids)),
            group_ids,
        ).fetchall() if group_ids else []
        differences: dict[str, dict[str, Any]] = {}
        names = {row["product_id"]: row["name"] for row in group_rows}
        for row in claim_rows:
            entry = differences.setdefault(row["field"], {"field": row["field"], "label": row["label"], "values": []})
            entry["values"].append({"product_id": row["product_id"], "product_name": names[row["product_id"]], "value": row["value_text"]})
        comparable_differences = [entry for entry in differences.values() if len({value["value"] for value in entry["values"]}) > 1]
        return {
            "enabled": True,
            "domain": profile["domain"],
            "context_id": profile["context_id"],
            "title": profile["title"],
            "context_summary": profile["context_summary"],
            "variant_group": profile["variant_group"],
            "fitment_status": profile["fitment_status"],
            "summary": profile["summary"],
            "questions": _loads(profile["questions_json"], []),
            "checks_before_buying": _loads(profile["checks_json"], []),
            "claims": [dict(row) for row in claims],
            "supplier_evidence": [dict(row) for row in evidence],
            "comparison": {
                "group_id": profile["variant_group"],
                "title": profile["title"],
                "products": [{"product_id": row["product_id"], "name": row["name"]} for row in group_rows],
                "differences": comparable_differences[:6],
            },
        }

    def find_decision(self, query: str) -> dict[str, Any]:
        query_key = normalize_query(query or "")
        contexts = self.connection.execute(
            "SELECT * FROM decision_contexts ORDER BY id"
        ).fetchall()
        selected = None
        selected_score = 0
        for context in contexts:
            keywords = _loads(context["keywords_json"], [])
            score = sum(1 for keyword in keywords if normalize_query(keyword) and normalize_query(keyword) in query_key)
            if score > selected_score:
                selected, selected_score = context, score
        if selected is None:
            return {"query": query, "status": "no_context", "context": None, "options": []}
        profiles = self.connection.execute(
            "SELECT product_id, variant_group, fitment_status, summary FROM decision_profiles WHERE context_id = ? ORDER BY product_id",
            (selected["id"],),
        ).fetchall()
        options = []
        for profile in profiles:
            product = self.get_product(profile["product_id"])
            if product is None:
                continue
            terms = [product["name"], *product.get("aliases", []), product.get("category", "")]
            if query_key and selected_score == 0 and not any(query_key in normalize_query(term) for term in terms):
                continue
            priced = [price["price_irr"] for price in product.get("prices", []) if isinstance(price.get("price_irr"), int)]
            options.append({
                "product_id": product["id"],
                "name": product["name"],
                "category": product["category"],
                "variant_group": profile["variant_group"],
                "fitment_status": profile["fitment_status"],
                "summary": profile["summary"],
                "lowest_price_irr": min(priced) if priced else None,
            })
        return {
            "query": query,
            "status": "ready" if options else "no_options",
            "context": {
                "id": selected["id"],
                "domain": selected["domain"],
                "title": selected["title"],
                "summary": selected["summary"],
                "questions": _loads(selected["questions_json"], []),
                "checks_before_buying": _loads(selected["checks_json"], []),
            },
            "options": options,
        }

    def get_decision_context(self, context_id: str) -> dict[str, Any] | None:
        context = self.connection.execute(
            "SELECT * FROM decision_contexts WHERE id = ?", (context_id,)
        ).fetchone()
        if context is None:
            return None
        profiles = self.connection.execute(
            """SELECT dp.product_id, dp.variant_group, dp.fitment_status, dp.summary,
                      p.name, p.category
               FROM decision_profiles dp
               JOIN products p ON p.id = dp.product_id
               WHERE dp.context_id = ? ORDER BY p.name""",
            (context_id,),
        ).fetchall()
        options = []
        for profile in profiles:
            product = self.get_product(profile["product_id"])
            if product is None:
                continue
            prices = [price["price_irr"] for price in product.get("prices", []) if isinstance(price.get("price_irr"), int)]
            options.append({
                "product_id": profile["product_id"],
                "name": profile["name"],
                "category": profile["category"],
                "variant_group": profile["variant_group"],
                "fitment_status": profile["fitment_status"],
                "summary": profile["summary"],
                "lowest_price_irr": min(prices) if prices else None,
            })
        return {
            "context": {
                "id": context["id"],
                "domain": context["domain"],
                "title": context["title"],
                "summary": context["summary"],
                "questions": _loads(context["questions_json"], []),
                "checks_before_buying": _loads(context["checks_json"], []),
            },
            "options": options,
        }

    def answer_decision(self, context_id: str, answers: dict[str, Any]) -> dict[str, Any]:
        context = self.connection.execute("SELECT * FROM decision_contexts WHERE id = ?", (context_id,)).fetchone()
        if context is None:
            return {"context_id": context_id, "status": "unknown_context", "answers": {}}
        questions = _loads(context["questions_json"], [])
        allowed = {question["id"]: {option["id"] for option in question.get("options", [])} for question in questions}
        clean = {
            key: value for key, value in (answers or {}).items()
            if key in allowed and isinstance(value, str) and value in allowed[key]
        }
        selected_labels = {
            question["id"]: {
                option["id"]: option.get("label", option["id"])
                for option in question.get("options", [])
            }
            for question in questions
        }
        selected_option_label = next(
            (
                selected_labels.get(question_id, {}).get(option_id)
                for question_id, option_id in clean.items()
            ),
            None,
        )
        return {
            "context_id": context_id,
            "status": "answered" if clean else "needs_answer",
            "answers": clean,
            "selected_option_label": selected_option_label,
            "message": "انتخاب ثبت شد؛ گزینه‌ها را با همین ترجیح بخوان." if clean else "یک گزینهٔ معتبر انتخاب کن.",
        }

    @staticmethod
    def _price(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "price_id": row["price_id"],
            "offer_id": row["price_id"],
            "supplier_id": row["supplier_id"],
            "supplier_name": row["supplier_name"],
            "supplier_kind": row["supplier_kind"],
            "supplier_source": row["supplier_source"],
            "price_irr": row["price_irr"],
            "package_price_irr": row["price_irr"],
            "package_size_base": row["package_size_base"],
            "min_packages": row["min_packages"],
            "package_step": row["package_step"],
            "stock_packages": row["stock_packages"],
            "lead_days": row["lead_days"],
            "invoice_status": row["invoice_status"] or "unknown",
            "tax_status": row["tax_status"] or "unknown",
            "source_snapshot_id": row["source_snapshot_id"],
            "source_record_id": row["source_record_id"],
            "valid_at": row["valid_at"],
            "source_url": row["source_url"],
            "source_label": row["source_label"],
            "raw_title": row["raw_title"],
            "raw_price_text": row["raw_price_text"],
            "field_status": _loads(row["field_status_json"], {}),
            "price_status": row["price_status"] or "unknown",
            "stock_status": row["stock_status"] or "unknown",
            "availability_status": row["availability_status"] or "unknown",
            "match_status": row["match_status"] or "unknown",
            "is_available": bool(row["is_available"]) if row["is_available"] is not None else False,
        }

    def list_products(self, query: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT p.*, MIN(CASE WHEN pp.price_irr IS NOT NULL AND pp.is_available = 1
                                      THEN pp.price_irr END) AS lowest_price_irr,
                      COUNT(DISTINCT CASE WHEN pp.price_irr IS NOT NULL AND pp.is_available = 1
                                          THEN pp.supplier_id END) AS priced_supplier_count,
                      COUNT(DISTINCT pp.supplier_id) AS supplier_count
               FROM products p
               LEFT JOIN product_prices pp ON pp.product_id = p.id
               GROUP BY p.id
               ORDER BY p.name"""
        ).fetchall()
        query_key = normalize_query(query or "")
        category_key = normalize_query(category or "")
        cards = []
        for row in rows:
            product = self._product(row)
            path = [normalize_query(part) for part in product["category_path"]]
            terms = [product["name"], *product["aliases"]]
            if category_key and category_key not in path:
                continue
            if query_key and not any(query_key in normalize_query(term) for term in terms):
                continue
            card = dict(product)
            card.update({
                "catalog_item_id": product["id"],
                "accepted_offer_count": self._price_count(product["id"]),
                "priced_supplier_count": int(row["priced_supplier_count"] or 0),
                "supplier_count": int(row["supplier_count"] or 0),
                "lowest_package_price_irr": row["lowest_price_irr"],
                "lowest_comparable_base_unit_price_irr": self._lowest_base_unit_price(product["id"]),
            })
            decision = self._decision_for_product(product["id"])
            card.update({
                "decision_enabled": bool(decision),
                "decision_status": decision.get("fitment_status") if decision else None,
                "decision_summary": decision.get("summary") if decision else None,
            })
            cards.append(card)
        return cards

    def _price_count(self, product_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM product_prices WHERE product_id = ? AND is_available = 1 AND price_irr IS NOT NULL",
            (product_id,),
        ).fetchone()
        return int(row["count"])

    def _lowest_base_unit_price(self, product_id: str) -> int | None:
        rows = self.connection.execute(
            "SELECT price_irr, package_size_base FROM product_prices WHERE product_id = ? AND is_available = 1",
            (product_id,),
        ).fetchall()
        prices = [
            row["price_irr"] // row["package_size_base"]
            for row in rows
            if type(row["price_irr"]) is int
            and row["price_irr"] > 0
            and type(row["package_size_base"]) is int
            and row["package_size_base"] > 0
            and row["price_irr"] % row["package_size_base"] == 0
        ]
        return min(prices) if prices else None

    def list_suppliers(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT s.id, s.name, s.kind, s.source,
                      COUNT(DISTINCT pp.product_id) AS product_count,
                      COUNT(CASE WHEN pp.price_irr IS NOT NULL AND pp.is_available = 1 THEN pp.id END) AS price_count,
                      COUNT(pp.id) AS listing_count
               FROM suppliers s
                 LEFT JOIN product_prices pp
                 ON pp.supplier_id = s.id
               WHERE s.is_active = 1
               GROUP BY s.id
               ORDER BY CASE WHEN s.id = 'digikala' THEN 0 ELSE 1 END, s.name"""
        ).fetchall()
        return [dict(row) for row in rows]

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            return None
        product = self._product(row)
        decision = self._decision_for_product(product_id)
        if decision:
            product["decision"] = decision
        prices = self.connection.execute(
            """SELECT s.id AS supplier_id, s.name AS supplier_name,
                      s.kind AS supplier_kind, s.source AS supplier_source,
                      pp.id AS price_id, pp.price_irr, pp.package_size_base,
                      pp.min_packages, pp.package_step, pp.stock_packages,
                      pp.lead_days, pp.invoice_status, pp.tax_status,
                      pp.source_snapshot_id, pp.source_record_id, pp.valid_at,
                      pp.source_url, pp.source_label, pp.raw_title, pp.raw_price_text,
                      pp.field_status_json, pp.price_status, pp.stock_status,
                      pp.availability_status, pp.match_status,
                      pp.is_available
               FROM suppliers s
               LEFT JOIN product_prices pp
                 ON pp.supplier_id = s.id AND pp.product_id = ?
               WHERE s.is_active = 1 AND pp.id IS NOT NULL
               ORDER BY CASE WHEN pp.price_irr IS NULL THEN 1 ELSE 0 END,
                        pp.price_irr, s.name""",
            (product_id,),
        ).fetchall()
        product["prices"] = [self._price(price) for price in prices]
        product["supplier_count"] = len(prices)
        return product

    def counts(self) -> dict[str, int]:
        return {
            "products": int(self.connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]),
            "suppliers": int(self.connection.execute("SELECT COUNT(*) FROM suppliers WHERE is_active = 1").fetchone()[0]),
            "prices": int(self.connection.execute("SELECT COUNT(*) FROM product_prices WHERE is_available = 1").fetchone()[0]),
        }
