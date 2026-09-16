"""HTTP contract tests for the in-memory local demo server."""

from __future__ import annotations

import http.client
import json
import threading
import unittest

from torob_business.server import create_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, path, body=json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response.status, json.loads(raw.decode("utf-8"))

    def raw_request(self, method, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path)
        response = connection.getresponse()
        status, content_type, raw = response.status, response.getheader("Content-Type"), response.read()
        connection.close()
        return status, content_type, raw

    def test_active_dataset_search_and_provenance(self):
        status, active = self.request("GET", "/api/datasets/active")
        self.assertEqual(status, 200)
        self.assertEqual(active["metadata"]["id"], "demo-v1")
        self.assertGreater(active["counts"]["accepted_offers"], 0)
        status, found = self.request("GET", "/api/catalog/search?q=%D8%AE%D9%88%D8%AF%DA%A9%D8%A7%D8%B1")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(found["candidates"]), 1)
        status, provenance = self.request("GET", "/api/offers/offer-card-01/provenance")
        self.assertEqual(status, 200)
        self.assertEqual(provenance["offer"]["id"], "offer-card-01")
        self.assertEqual(provenance["raw"]["id"], provenance["offer"]["raw_record_id"])

    def test_catalog_storefront_lists_synthetic_items_and_comparable_prices(self):
        status, listing = self.request("GET", "/api/catalog/items")
        self.assertEqual(status, 200)
        self.assertEqual(listing["snapshot_id"], "demo-v1")
        self.assertEqual(listing["data_kind"], "synthetic")
        self.assertEqual(len(listing["items"]), 5)
        pen = next(item for item in listing["items"] if item["catalog_item_id"] == "pen-blue-07")
        self.assertEqual(pen["accepted_offer_count"], 3)
        self.assertEqual(pen["lowest_package_price_irr"], 60_000)
        self.assertEqual(pen["lowest_comparable_base_unit_price_irr"], 10_000)

    def test_catalog_storefront_filters_and_detail_excludes_rejected_offers(self):
        status, filtered = self.request("GET", "/api/catalog/items?category=%D8%AA%D8%AC%D9%87%DB%8C%D8%B2%D8%A7%D8%AA%20IT&q=M100")
        self.assertEqual(status, 200)
        self.assertEqual([item["catalog_item_id"] for item in filtered["items"]], ["mouse-usb-m100"])
        status, detail = self.request("GET", "/api/catalog/items/pen-blue-07")
        self.assertEqual(status, 200)
        self.assertEqual(detail["item"]["id"], "pen-blue-07")
        self.assertEqual({offer["offer_id"] for offer in detail["offers"]}, {"offer-grid-01", "offer-grid-03", "offer-card-01"})
        self.assertTrue(all(offer["vendor_name"] and offer["provenance_ids"]["raw_record_id"] for offer in detail["offers"]))
        status, error = self.request("GET", "/api/catalog/items/not-a-sku")
        self.assertEqual(status, 404)
        self.assertEqual(error["error"]["code"], "CATALOG_ITEM_NOT_FOUND")

    def test_rfq_requires_two_lines_and_evaluates_after_matching(self):
        status, error = self.request("POST", "/api/rfqs", {"lines": [{"id": "one", "query_text": "خودکار آبی", "qty_base": 1}]})
        self.assertEqual(status, 422)
        self.assertEqual(error["error"]["code"], "INVALID_RFQ")
        status, error = self.request("POST", "/api/rfqs", {"lines": [{"id": [], "qty_base": 1}, {"id": "two", "qty_base": 1}]})
        self.assertEqual(status, 422)
        self.assertEqual(error["error"]["code"], "INVALID_RFQ")
        payload = {
            "lines": [
                {"id": "pen", "query_text": "خودکار آبی ۰٫۷", "qty_base": 13},
                {"id": "mouse", "query_text": "ماوس باسیم M100", "qty_base": 2},
            ],
            "preference": "lowest_cost",
        }
        status, rfq = self.request("POST", "/api/rfqs", payload)
        self.assertEqual(status, 201)
        self.assertEqual(rfq["status"], "ready")
        status, run = self.request("POST", f"/api/rfqs/{rfq['rfq_id']}/evaluate", {"preference": "fastest_delivery"})
        self.assertEqual(status, 201)
        self.assertTrue(run["search_exhaustive"])
        status, result = self.request("GET", f"/api/runs/{run['run_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(result["run_id"], run["run_id"])
        self.assertEqual(result["preference"], "fastest_delivery")

    def test_ambiguous_selection_must_be_candidate(self):
        payload = {"lines": [
            {"id": "pen", "query_text": "خودکار", "qty_base": 1},
            {"id": "mouse", "query_text": "ماوس باسیم M100", "qty_base": 1},
        ]}
        status, rfq = self.request("POST", "/api/rfqs", payload)
        self.assertEqual(status, 201)
        self.assertEqual(rfq["status"], "needs_match")
        status, error = self.request("PUT", f"/api/rfqs/{rfq['rfq_id']}/matches/pen", {"catalog_item_id": "not-a-sku"})
        self.assertEqual(status, 422)
        self.assertEqual(error["error"]["code"], "INCOMPATIBLE_CATALOG_ITEM")
        candidate = rfq["matches"][0]["candidate_catalog_ids"][0]
        status, matches = self.request("PUT", f"/api/rfqs/{rfq['rfq_id']}/matches/pen", {"catalog_item_id": candidate})
        self.assertEqual(status, 200)
        self.assertEqual(matches["status"], "ready")

    def test_unknown_routes_are_json_404(self):
        status, error = self.request("GET", "/api/nope")
        self.assertEqual(status, 404)
        self.assertEqual(error["error"]["code"], "NOT_FOUND")

    def test_serves_allowlisted_font_without_exposing_other_web_paths(self):
        status, content_type, font = self.raw_request("GET", "/fonts/Vazirmatn.ttf")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "font/ttf")
        self.assertGreater(len(font), 100_000)
        status, error = self.request("GET", "/fonts/../styles.css")
        self.assertEqual(status, 404)
        self.assertEqual(error["error"]["code"], "NOT_FOUND")

    def test_serves_allowlisted_brand_logo_as_png(self):
        status, content_type, image = self.raw_request("GET", "/brand/torob-business-logo.png")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/png")
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        status, content_type, image = self.raw_request("GET", "/brand/torob-business-symbol.png")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/png")
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        status, content_type, image = self.raw_request("GET", "/catalog/ballpen.svg")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/svg+xml")
        self.assertIn(b"<svg", image[:500])
        for icon_name in ("shopping-cart", "discount-tag", "pricelist", "warehouse"):
            status, content_type, image = self.raw_request("GET", f"/landing-icons/{icon_name}.png")
            self.assertEqual(status, 200)
            self.assertEqual(content_type, "image/png")
            self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        status, error = self.request("GET", "/brand/other.png")
        self.assertEqual(status, 404)
        self.assertEqual(error["error"]["code"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
