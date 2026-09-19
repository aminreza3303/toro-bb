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
        self.assertEqual(len(listing["items"]), 40)
        pen = next(item for item in listing["items"] if item["catalog_item_id"] == "pen-blue-07")
        self.assertEqual(pen["accepted_offer_count"], 3)
        self.assertEqual(pen["lowest_package_price_irr"], 60_000)
        self.assertEqual(pen["lowest_comparable_base_unit_price_irr"], 10_000)
        chair = next(item for item in listing["items"] if item["catalog_item_id"] == "chair-k713")
        self.assertEqual(chair["priced_supplier_count"], 1)
        self.assertEqual(chair["lowest_package_price_irr"], 45_900_000)
        printer = next(item for item in listing["items"] if item["catalog_item_id"] == "printer-hp-laser-107a")
        self.assertEqual(printer["priced_supplier_count"], 4)
        self.assertEqual(printer["lowest_package_price_irr"], 178_000_000)
        monitor = next(item for item in listing["items"] if item["catalog_item_id"] == "monitor-lg-u411-24")
        self.assertEqual(monitor["lowest_package_price_irr"], 254_900_000)
        ssd = next(item for item in listing["items"] if item["catalog_item_id"] == "ssd-verbatim-vi550-1tb")
        self.assertFalse(ssd["rfq_capable"])
        printer = next(item for item in listing["items"] if item["catalog_item_id"] == "printer-hp-laser-107a")
        self.assertTrue(printer["rfq_capable"])
        self.assertEqual(printer["rankable_offer_count"], 4)

    def test_catalog_storefront_filters_and_detail_excludes_rejected_offers(self):
        status, filtered = self.request("GET", "/api/catalog/items?category=%D9%85%D8%A7%D9%88%D8%B3&q=M100")
        self.assertEqual(status, 200)
        self.assertEqual([item["catalog_item_id"] for item in filtered["items"]], ["mouse-usb-m100"])
        status, detail = self.request("GET", "/api/catalog/items/pen-blue-07")
        self.assertEqual(status, 200)
        self.assertEqual(detail["item"]["id"], "pen-blue-07")
        self.assertEqual({offer["offer_id"] for offer in detail["offers"]}, {"offer-grid-01", "offer-grid-03", "offer-card-01"})
        self.assertTrue(all(offer["vendor_name"] and offer["provenance_ids"]["raw_record_id"] for offer in detail["offers"]))
        self.assertIn("prices", detail)
        self.assertNotIn("digikala", {price["supplier_id"] for price in detail["prices"]})
        status, chair = self.request("GET", "/api/catalog/items/chair-k713")
        self.assertEqual(status, 200)
        torob = next(price for price in chair["prices"] if price["supplier_id"] == "v-torob")
        self.assertEqual(torob["price_irr"], 45_900_000)
        self.assertIn("torob.com/search", torob["source_url"])
        status, provenance = self.request("GET", f"/api/offers/{torob['offer_id']}/provenance")
        self.assertEqual(status, 200)
        self.assertEqual(provenance["raw"]["raw_price_text"], "از ۴٬۵۹۰٬۰۰۰ تومان")
        status, printer = self.request("GET", "/api/catalog/items/printer-hp-laser-107a")
        self.assertEqual(status, 200)
        self.assertEqual(printer["item"]["name"], "پرینتر لیزری اچ‌پی مدل Laser 107a")
        self.assertEqual({price["supplier_id"] for price in printer["prices"]}, {"digikala", "v-budget", "v-print", "v-it", "v-fast"})
        cheapest = next(price for price in printer["prices"] if price["supplier_id"] == "v-budget")
        self.assertEqual(cheapest["price_irr"], 178_000_000)
        status, provenance = self.request("GET", f"/api/offers/{cheapest['offer_id']}/provenance")
        self.assertEqual(status, 200)
        self.assertEqual(provenance["raw"]["source_label"], "synthetic_fixture")
        status, overlap = self.request("GET", "/api/catalog/items/ssd-verbatim-vi550-1tb")
        self.assertEqual(status, 200)
        self.assertEqual({group["supplier_id"] for group in overlap["source_comparison"]["sources"]}, {"digikala", "v-torob"})
        digikala = next(price for price in overlap["prices"] if price["supplier_id"] == "digikala")
        self.assertEqual(digikala["match_status"], "exact")
        self.assertEqual(digikala["raw_price_text"], "ناموجود")
        self.assertIsNone(digikala["stock_packages"])
        self.assertEqual(overlap["source_comparison"]["overlap"], True)
        status, provenance = self.request("GET", f"/api/offers/{digikala['offer_id']}/provenance")
        self.assertEqual(status, 200)
        self.assertEqual(provenance["raw"]["field_status"]["price_irr"], "unavailable")
        status, error = self.request("GET", "/api/catalog/items/not-a-sku")
        self.assertEqual(status, 404)
        self.assertEqual(error["error"]["code"], "CATALOG_ITEM_NOT_FOUND")

    def test_agent_manifest_and_product_analysis_are_exposed(self):
        status, manifest = self.request("GET", "/api/agents/manifest")
        self.assertEqual(status, 200)
        self.assertEqual(manifest["runtime"]["mode"], "deterministic-local")
        self.assertEqual(manifest["runtime"]["execution_plan"]["max_parallelism"], 2)
        self.assertEqual(manifest["runtime"]["execution_plan"]["failure_mode"], "fail-closed")
        self.assertEqual(len(manifest["agents"]), 5)
        self.assertIn("exact-sku-guard", [skill["id"] for skill in manifest["agents"][0]["skills"]])
        status, detail = self.request("GET", "/api/catalog/items/ssd-verbatim-vi550-1tb")
        self.assertEqual(status, 200)
        self.assertEqual(detail["agent_analysis"]["status"], "completed")
        self.assertTrue(detail["agent_analysis"]["quality_gates"]["exact_sku_only"])
        status, analysis = self.request("GET", "/api/agents/catalog/items/ssd-verbatim-vi550-1tb")
        self.assertEqual(status, 200)
        self.assertEqual(analysis["analysis"]["run_id"], detail["agent_analysis"]["run_id"])
        self.assertEqual(analysis["analysis"]["execution_plan"]["layers"][1], ["provenance-auditor", "decision-context"])

    def test_supplier_endpoint_is_separate_and_includes_digikala(self):
        status, response = self.request("GET", "/api/suppliers")
        self.assertEqual(status, 200)
        digikala = next(supplier for supplier in response["suppliers"] if supplier["id"] == "digikala")
        self.assertEqual(digikala["name"], "دیجی کالا")
        self.assertEqual(digikala["kind"], "marketplace")
        self.assertEqual(digikala["price_count"], 0)
        torob = next(supplier for supplier in response["suppliers"] if supplier["id"] == "v-torob")
        self.assertEqual(torob["name"], "ترب")
        self.assertEqual(torob["price_count"], 34)

    def test_decision_layer_explains_variant_risk_before_price(self):
        status, response = self.request("GET", "/api/catalog/decision?q=SSD")
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "ready")
        self.assertEqual(response["context"]["id"], "computer-storage-selection")
        self.assertTrue(response["context"]["questions"])
        self.assertGreaterEqual(len(response["options"]), 3)
        status, detail = self.request("GET", "/api/catalog/items/ssd-adlink-s20-1tb")
        self.assertEqual(status, 200)
        decision = detail["item"]["decision"]
        self.assertEqual(decision["fitment_status"], "needs_check")
        self.assertTrue(decision["claims"])
        self.assertTrue(decision["supplier_evidence"])
        self.assertTrue(decision["comparison"]["differences"])
        status, context = self.request("GET", "/api/catalog/decision/computer-storage-selection")
        self.assertEqual(status, 200)
        self.assertEqual(context["context"]["id"], "computer-storage-selection")
        self.assertEqual(len(context["options"]), 3)
        status, answer = self.request(
            "POST",
            "/api/catalog/decision/computer-storage-selection/answers",
            {"answers": {"storage_priority": "speed"}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(answer["status"], "answered")
        self.assertEqual(answer["selected_option_label"], "سرعت و دوام")

    def test_decision_answer_rejects_unknown_option(self):
        status, answer = self.request(
            "POST",
            "/api/catalog/decision/computer-storage-selection/answers",
            {"answers": {"storage_priority": "not-an-option"}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(answer["status"], "needs_answer")
        status, answer = self.request(
            "POST",
            "/api/catalog/decision/computer-storage-selection/answers",
            {"answers": {"storage_priority": []}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(answer["status"], "needs_answer")

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
                {"id": "mouse", "query_text": "ماوس باسیم M100", "qty_base": 2,
                 "decision_context_id": "computer-peripheral-selection", "decision_answers": {"peripheral_connection": "wired"}},
            ],
            "preference": "lowest_cost",
        }
        status, rfq = self.request("POST", "/api/rfqs", payload)
        self.assertEqual(status, 201)
        self.assertEqual(rfq["status"], "ready")
        self.assertEqual(self.server.state.rfqs[rfq["rfq_id"]]["rfq"]["lines"][1]["decision_context_id"], "computer-peripheral-selection")
        self.assertEqual(self.server.state.rfqs[rfq["rfq_id"]]["rfq"]["lines"][1]["decision_answers"]["peripheral_connection"], "wired")
        status, run = self.request("POST", f"/api/rfqs/{rfq['rfq_id']}/evaluate", {"preference": "fastest_delivery"})
        self.assertEqual(status, 201)
        self.assertTrue(run["search_exhaustive"])
        status, result = self.request("GET", f"/api/runs/{run['run_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(result["run_id"], run["run_id"])
        self.assertEqual(result["preference"], "fastest_delivery")

    def test_demo_market_capture_can_rank_and_incomplete_capture_is_blocked_early(self):
        printer_payload = {
            "lines": [
                {"id": "printer", "catalog_item_id": "printer-hp-laser-107a", "qty_base": 1},
                {"id": "pen", "catalog_item_id": "pen-blue-07", "qty_base": 1},
            ],
            "preference": "lowest_cost",
        }
        status, rfq = self.request("POST", "/api/rfqs", printer_payload)
        self.assertEqual(status, 201)
        self.assertEqual(rfq["status"], "ready")
        status, started = self.request("POST", f"/api/rfqs/{rfq['rfq_id']}/evaluate", {"preference": "lowest_cost"})
        self.assertEqual(status, 201)
        status, result = self.request("GET", f"/api/runs/{started['run_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "ok")
        printer = next(
            assignment for combination in result["combinations"]
            for assignment in combination["assignments"]
            if assignment["catalog_item_id"] == "printer-hp-laser-107a"
        )
        self.assertTrue(printer["offer_id"].startswith("price-synthetic-printer"))
        self.assertEqual(printer["provenance"]["source_label"], "synthetic_fixture")

        blocked_payload = {
            "lines": [
                {"id": "ssd", "catalog_item_id": "ssd-verbatim-vi550-1tb", "qty_base": 1},
                {"id": "pen", "catalog_item_id": "pen-blue-07", "qty_base": 1},
            ],
        }
        status, blocked = self.request("POST", "/api/rfqs", blocked_payload)
        self.assertEqual(status, 201)
        self.assertEqual(blocked["status"], "needs_match")
        ssd_match = next(match for match in blocked["matches"] if match["line_id"] == "ssd")
        self.assertEqual(ssd_match["method"], "no_rankable_offers")

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
        status, content_type, image = self.raw_request("GET", "/brand/torob-business-logo-transparent.png")
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
