"""Loopback-only HTTP server for the local Torob Business demo.

The server deliberately keeps RFQs and runs in memory.  It is a thin API
layer over the matching and ranking modules; commercial decisions stay in
those deterministic domain functions.
"""

from __future__ import annotations

import argparse
import copy
import json
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .data import load_demo
from .matching import normalize_query, resolve_rfq, search_catalog
from .ranking import evaluate


WEB_ROOT = Path(__file__).resolve().parents[2] / "web"
_STATIC_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "fonts/Vazirmatn.ttf": "font/ttf",
    "brand/torob-business-logo.png": "image/png",
    "brand/torob-business-symbol.png": "image/png",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


class DemoState:
    def __init__(self, snapshot: dict[str, Any] | None = None):
        self.snapshot = snapshot or load_demo()
        self.rfqs: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}


def _metadata(snapshot: dict[str, Any]) -> dict[str, Any]:
    metadata = {key: snapshot.get(key) for key in ("id", "version", "captured_at", "kind", "rules_version", "content_hash")}
    offers = snapshot.get("offers", [])
    return {
        "metadata": metadata,
        "catalog": snapshot.get("catalog", []),
        "vendors": snapshot.get("vendors", []),
        "counts": {
            "catalog_items": len(snapshot.get("catalog", [])),
            "vendors": len(snapshot.get("vendors", [])),
            "offers": len(offers),
            "accepted_offers": sum(offer.get("normalization_status") == "accepted" for offer in offers),
            "rejected_offers": sum(offer.get("normalization_status") != "accepted" for offer in offers),
        },
    }


def _accepted_offers(snapshot: dict[str, Any], catalog_item_id: str) -> list[dict[str, Any]]:
    """Return accepted offers for one SKU in a stable, display-safe order."""
    return sorted(
        (
            offer for offer in snapshot.get("offers", [])
            if offer.get("catalog_item_id") == catalog_item_id
            and offer.get("normalization_status") == "accepted"
        ),
        key=lambda offer: str(offer.get("id", "")),
    )


def _lowest_prices(offers: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    """Return lowest package and exactly calculable base-unit prices in IRR."""
    package_prices: list[int] = []
    base_unit_prices: list[int] = []
    for offer in offers:
        price, package_size = offer.get("package_price_irr"), offer.get("package_size_base")
        if type(price) is not int or price <= 0:
            continue
        package_prices.append(price)
        # IRR is an integer-only amount. Do not round a package-derived price.
        if type(package_size) is int and package_size > 0 and price % package_size == 0:
            base_unit_prices.append(price // package_size)
    return (min(package_prices) if package_prices else None, min(base_unit_prices) if base_unit_prices else None)


def _catalog_listing(snapshot: dict[str, Any], query: str | None, category: str | None) -> list[dict[str, Any]]:
    """Build synthetic storefront cards without implying live commercial data."""
    query_key = normalize_query(query or "")
    category_key = normalize_query(category or "")
    cards: list[dict[str, Any]] = []
    for item in snapshot.get("catalog", []):
        item_category = item.get("category", "")
        terms = [item.get("name", ""), *item.get("aliases", [])]
        if category_key and normalize_query(item_category) != category_key:
            continue
        if query_key and not any(query_key in normalize_query(term) for term in terms):
            continue
        offers = _accepted_offers(snapshot, item["id"])
        lowest_package_price, lowest_base_unit_price = _lowest_prices(offers)
        cards.append({
            "catalog_item_id": item["id"],
            "category": item_category,
            "name": item.get("name"),
            "base_unit": item.get("base_unit"),
            "accepted_offer_count": len(offers),
            "lowest_comparable_base_unit_price_irr": lowest_base_unit_price,
            "lowest_package_price_irr": lowest_package_price,
        })
    return cards


def _catalog_item_detail(snapshot: dict[str, Any], catalog_item_id: str) -> dict[str, Any]:
    item = next((entry for entry in snapshot.get("catalog", []) if entry.get("id") == catalog_item_id), None)
    if item is None:
        raise ApiError(404, "CATALOG_ITEM_NOT_FOUND", f"Catalog item {catalog_item_id} was not found")
    vendors = {vendor.get("id"): vendor for vendor in snapshot.get("vendors", [])}
    offers = []
    for offer in _accepted_offers(snapshot, catalog_item_id):
        vendor = vendors.get(offer.get("vendor_id"), {})
        offers.append({
            "offer_id": offer.get("id"),
            "vendor_id": offer.get("vendor_id"),
            "vendor_name": vendor.get("name"),
            "package_size_base": offer.get("package_size_base"),
            "package_price_irr": offer.get("package_price_irr"),
            "min_packages": offer.get("min_packages"),
            "package_step": offer.get("package_step"),
            "stock_packages": offer.get("stock_packages"),
            "lead_days": offer.get("lead_days"),
            "invoice_status": offer.get("invoice_status"),
            "tax_status": offer.get("tax_status"),
            "valid_at": offer.get("valid_at"),
            "provenance_ids": {"snapshot_id": snapshot.get("id"), "raw_record_id": offer.get("raw_record_id")},
        })
    return {"snapshot_id": snapshot.get("id"), "data_kind": snapshot.get("kind"), "item": item, "offers": offers}


def _validate_rfq_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError(422, "INVALID_RFQ", "RFQ body must be a JSON object")
    lines = value.get("lines")
    if not isinstance(lines, list) or len(lines) < 2:
        raise ApiError(422, "INVALID_RFQ", "RFQ needs at least two lines")
    if any(not isinstance(line, dict) or not isinstance(line.get("id"), str) or not line["id"] for line in lines):
        raise ApiError(422, "INVALID_RFQ", "RFQ line ids must be unique and nonempty")
    if len({line["id"] for line in lines}) != len(lines):
        raise ApiError(422, "INVALID_RFQ", "RFQ line ids must be unique and nonempty")
    rfq = copy.deepcopy(value)
    rfq.setdefault("preference", "lowest_cost")
    rfq.setdefault("budget_irr", None)
    rfq.setdefault("max_lead_days", None)
    rfq.setdefault("requires_declared_invoice", False)
    return rfq


class DemoRequestHandler(BaseHTTPRequestHandler):
    server: "DemoHTTPServer"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the demo quiet when used from its command-line entry point.
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, error: ApiError) -> None:
        self._json(error.status, {"error": {"code": error.code, "message": error.message}})

    def _body(self) -> dict[str, Any]:
        length = self.headers.get("Content-Length")
        try:
            size = int(length) if length is not None else 0
        except ValueError as exc:
            raise ApiError(422, "INVALID_JSON", "Content-Length must be an integer") from exc
        if size < 1 or size > 1_000_000:
            raise ApiError(422, "INVALID_JSON", "JSON body must be between 1 and 1000000 bytes")
        try:
            decoded = json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(422, "INVALID_JSON", "Request body must be valid JSON") from exc
        if not isinstance(decoded, dict):
            raise ApiError(422, "INVALID_JSON", "Request body must be a JSON object")
        return decoded

    def _rfq(self, rfq_id: str) -> dict[str, Any]:
        try:
            return self.server.state.rfqs[rfq_id]
        except KeyError as exc:
            raise ApiError(404, "RFQ_NOT_FOUND", f"RFQ {rfq_id} was not found") from exc

    def _resolve(self, rfq: dict[str, Any]) -> dict[str, Any]:
        try:
            return resolve_rfq(self.server.state.snapshot, rfq)
        except ValueError as exc:
            raise ApiError(422, "INVALID_RFQ", str(exc)) from exc

    def _serve_static(self, path: str) -> None:
        filename = "index.html" if path == "/" else path.removeprefix("/")
        content_type = _STATIC_TYPES.get(filename)
        # Only an exact, small allowlist can be read. Nested paths are safe
        # when they appear in that map; all other paths remain inaccessible.
        if content_type is None:
            raise ApiError(404, "NOT_FOUND", "Route was not found")
        target = WEB_ROOT / filename
        try:
            content = target.read_bytes()
        except FileNotFoundError as exc:
            raise ApiError(404, "STATIC_NOT_FOUND", f"Static file {filename} was not found") from exc
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _dispatch_get(self, path: str, query: dict[str, list[str]]) -> None:
        state = self.server.state
        if path == "/api/datasets/active":
            self._json(200, _metadata(state.snapshot))
        elif path == "/api/catalog/items":
            query_value = query.get("q", [None])[0]
            category_value = query.get("category", [None])[0]
            self._json(200, {
                "snapshot_id": state.snapshot["id"],
                "data_kind": state.snapshot.get("kind"),
                "items": _catalog_listing(state.snapshot, query_value, category_value),
            })
        elif path.startswith("/api/catalog/items/"):
            catalog_item_id = path.removeprefix("/api/catalog/items/")
            if not catalog_item_id or "/" in catalog_item_id:
                raise ApiError(404, "CATALOG_ITEM_NOT_FOUND", "Catalog item was not found")
            self._json(200, _catalog_item_detail(state.snapshot, catalog_item_id))
        elif path == "/api/catalog/search":
            value = query.get("q", [""])[0]
            if not isinstance(value, str) or not value.strip():
                raise ApiError(422, "INVALID_QUERY", "q must be a nonempty query")
            snapshot_id = query.get("snapshot_id", [state.snapshot["id"]])[0]
            if snapshot_id != state.snapshot["id"]:
                raise ApiError(409, "SNAPSHOT_MISMATCH", "Only the active snapshot is available")
            self._json(200, {"candidates": search_catalog(state.snapshot, value)})
        elif path.startswith("/api/rfqs/") and path.endswith("/matches"):
            rfq_id = path[len("/api/rfqs/"):-len("/matches")].strip("/")
            record = self._rfq(rfq_id)
            self._json(200, {"rfq_id": rfq_id, "status": record["resolved"]["status"], "matches": record["resolved"]["matches"]})
        elif path.startswith("/api/runs/"):
            run_id = path.removeprefix("/api/runs/")
            if not run_id or "/" in run_id or run_id not in state.runs:
                raise ApiError(404, "RUN_NOT_FOUND", f"Run {run_id} was not found")
            self._json(200, state.runs[run_id])
        elif path.startswith("/api/offers/") and path.endswith("/provenance"):
            offer_id = path[len("/api/offers/"):-len("/provenance")].strip("/")
            offer = next((item for item in state.snapshot["offers"] if item.get("id") == offer_id), None)
            if offer is None:
                raise ApiError(404, "OFFER_NOT_FOUND", f"Offer {offer_id} was not found")
            raw = next((item for item in state.snapshot["raw_offers"] if item.get("id") == offer.get("raw_record_id")), None)
            vendor = next((item for item in state.snapshot["vendors"] if item.get("id") == offer.get("vendor_id")), None)
            item = next((entry for entry in state.snapshot["catalog"] if entry.get("id") == offer.get("catalog_item_id")), None)
            self._json(200, {"offer": offer, "raw": raw, "vendor": vendor, "catalog_item": item})
        elif path.startswith("/api/"):
            raise ApiError(404, "NOT_FOUND", "Route was not found")
        else:
            self._serve_static(path)

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        try:
            self._dispatch_get(parts.path, parse_qs(parts.query, keep_blank_values=True))
        except ApiError as error:
            self._error(error)

    def do_POST(self) -> None:
        parts = urlsplit(self.path)
        try:
            body = self._body()
            if parts.path == "/api/rfqs":
                rfq = _validate_rfq_payload(body)
                resolved = self._resolve(rfq)
                rfq_id = f"rfq-{uuid.uuid4().hex}"
                self.server.state.rfqs[rfq_id] = {"rfq": rfq, "resolved": resolved}
                self._json(201, {"rfq_id": rfq_id, "snapshot_id": self.server.state.snapshot["id"], "status": resolved["status"], "matches": resolved["matches"]})
                return
            if parts.path.startswith("/api/rfqs/") and parts.path.endswith("/evaluate"):
                rfq_id = parts.path[len("/api/rfqs/"):-len("/evaluate")].strip("/")
                record = self._rfq(rfq_id)
                if record["resolved"]["status"] != "ready":
                    raise ApiError(409, "RFQ_NEEDS_MATCH", "All RFQ lines need a confirmed catalog item")
                preference = body.get("preference", record["rfq"].get("preference", "lowest_cost"))
                if preference not in {"lowest_cost", "fastest_delivery"}:
                    raise ApiError(422, "INVALID_PREFERENCE", "preference must be lowest_cost or fastest_delivery")
                resolved_rfq = copy.deepcopy(record["resolved"]["rfq"])
                resolved_rfq["preference"] = preference
                try:
                    result = evaluate(self.server.state.snapshot, resolved_rfq)
                except ValueError as exc:
                    raise ApiError(422, "INVALID_RFQ", str(exc)) from exc
                run_id = f"run-{uuid.uuid4().hex}"
                response = {"run_id": run_id, **result}
                self.server.state.runs[run_id] = response
                self._json(201, {"run_id": run_id, "status": result["status"], "search_exhaustive": result["search_exhaustive"]})
                return
            raise ApiError(404, "NOT_FOUND", "Route was not found")
        except ApiError as error:
            self._error(error)

    def do_PUT(self) -> None:
        parts = urlsplit(self.path)
        try:
            body = self._body()
            prefix, marker = "/api/rfqs/", "/matches/"
            if not (parts.path.startswith(prefix) and marker in parts.path):
                raise ApiError(404, "NOT_FOUND", "Route was not found")
            rfq_id, line_id = parts.path[len(prefix):].split(marker, 1)
            if not rfq_id or not line_id or "/" in line_id:
                raise ApiError(404, "NOT_FOUND", "Route was not found")
            selected = body.get("catalog_item_id")
            if not isinstance(selected, str) or not selected:
                raise ApiError(422, "INVALID_CATALOG_ITEM", "catalog_item_id must be a nonempty string")
            record = self._rfq(rfq_id)
            match = next((item for item in record["resolved"]["matches"] if item["line_id"] == line_id), None)
            if match is None:
                raise ApiError(404, "LINE_NOT_FOUND", f"Line {line_id} was not found")
            if match["status"] != "ambiguous":
                raise ApiError(409, "MATCH_NOT_AMBIGUOUS", "Only ambiguous lines accept a manual selection")
            if selected not in match["candidate_catalog_ids"]:
                raise ApiError(422, "INCOMPATIBLE_CATALOG_ITEM", "catalog_item_id is not a compatible candidate for this line")
            updated = copy.deepcopy(record["rfq"])
            line = next(item for item in updated["lines"] if item["id"] == line_id)
            line["catalog_item_id"] = selected
            resolved = self._resolve(updated)
            record.update({"rfq": updated, "resolved": resolved})
            self._json(200, {"rfq_id": rfq_id, "status": resolved["status"], "matches": resolved["matches"]})
        except ApiError as error:
            self._error(error)

    def do_DELETE(self) -> None:
        self._error(ApiError(404, "NOT_FOUND", "Route was not found"))


class DemoHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: DemoState):
        super().__init__(address, DemoRequestHandler)
        self.state = state


def create_server(host: str = "127.0.0.1", port: int = 8000, *, snapshot: dict[str, Any] | None = None) -> DemoHTTPServer:
    """Create a testable loopback demo server without starting its event loop."""
    return DemoHTTPServer((host, port), DemoState(snapshot))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Torob Business demo API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = create_server(args.host, args.port)
    print(f"Torob Business demo available at http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
