"""Golden scenarios for the deterministic sourcing decision."""

import copy
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from torob_business.ranking import evaluate  # noqa: E402


def snapshot(*, offers, vendors=None, catalog=None):
    vendors = vendors or [{"id": "v1", "name": "Vendor 1", "shipping_irr": 20000, "minimum_order_irr": 0, "synthetic": True}]
    catalog = catalog or [{"id": "sku", "category": "office", "name": "Pen", "aliases": [], "base_unit": "unit"}]
    return {"id": "demo-v1", "kind": "synthetic", "catalog": catalog, "vendors": vendors,
            "raw_offers": [{"id": offer["raw_record_id"], "source_label": "synthetic_fixture", "generated_at": "2026-09-16"} for offer in offers],
            "offers": offers}


def offer(id="offer-01", **changes):
    result = {"id": id, "raw_record_id": f"raw-{id}", "vendor_id": "v1", "catalog_item_id": "sku",
              "package_size_base": 10, "package_price_irr": 100000, "min_packages": 1,
              "package_step": 1, "stock_packages": 10, "lead_days": 2,
              "invoice_status": "declared_yes", "tax_status": "included",
              "normalization_status": "accepted", "rejection_reason": None, "normalization_steps": []}
    result.update(changes)
    return result


def rfq(qty=13, **changes):
    result = {"lines": [{"id": "line-1", "catalog_item_id": "sku", "qty_base": qty}],
              "preference": "lowest_cost", "budget_irr": None, "max_lead_days": None,
              "requires_declared_invoice": False}
    result.update(changes)
    return result


class RankingGoldenTests(unittest.TestCase):
    def test_pack_rounds_up_to_two_packages_and_shipping_once(self):
        data = snapshot(offers=[offer(stock_packages=2)])
        result = evaluate(data, rfq())
        self.assertEqual(result["status"], "ok")
        basket = result["combinations"][0]
        self.assertEqual(basket["assignments"][0]["purchased_packages"], 2)
        self.assertEqual(basket["assignments"][0]["covered_qty_base"], 20)
        self.assertEqual(basket["assignments"][0]["overbuy_qty_base"], 7)
        self.assertEqual(basket["assignments"][0]["line_total_irr"], 200000)
        self.assertEqual(basket["shipping_total_irr"], 20000)
        self.assertEqual(basket["total_irr"], 220000)
        self.assertEqual(basket["assignments"][0]["provenance"]["raw_record_id"], "raw-offer-01")

    def test_intent_changes_winner_and_reason_comparison(self):
        data = snapshot(offers=[offer("A", package_price_irr=100000, lead_days=4),
                                offer("B", package_price_irr=110000, lead_days=1)])
        cheapest = evaluate(data, rfq(budget_irr=250000, max_lead_days=5))
        fastest = evaluate(data, rfq(preference="fastest_delivery", budget_irr=250000, max_lead_days=5))
        self.assertEqual([basket["offer_ids"] for basket in cheapest["combinations"]], [["A"], ["B"]])
        self.assertEqual([basket["offer_ids"] for basket in fastest["combinations"]], [["B"], ["A"]])
        self.assertEqual(cheapest["combinations"][0]["reason"]["difference"], 20000)
        self.assertEqual(fastest["combinations"][0]["reason"]["difference"], 3)

    def test_equal_baskets_tie_by_offer_id_and_repeat_stable(self):
        data = snapshot(offers=[offer("offer-02"), offer("offer-01")])
        result = evaluate(data, rfq())
        self.assertEqual([basket["offer_ids"] for basket in result["combinations"]], [["offer-01"], ["offer-02"]])
        self.assertEqual(result, evaluate(copy.deepcopy(data), copy.deepcopy(rfq())))
        self.assertEqual(result["input_hash"], evaluate(snapshot(offers=list(reversed(data["offers"]))), rfq())["input_hash"])

    def test_unknown_lead_time_excluded_with_and_without_cap(self):
        data = snapshot(offers=[offer(lead_days=None)])
        for constraint in (None, 3):
            with self.subTest(max_lead_days=constraint):
                result = evaluate(data, rfq(max_lead_days=constraint))
                self.assertEqual(result["status"], "no_full_coverage")
                self.assertEqual(result["combinations"], [])
                self.assertIn("UNKNOWN_LEAD_TIME", result["excluded_reasons"][0]["reason_codes"])

    def test_no_full_coverage_for_missing_sku_and_no_ranked_partial_basket(self):
        data = snapshot(offers=[offer()])
        request = rfq(lines=[{"id": "present", "catalog_item_id": "sku", "qty_base": 1},
                             {"id": "missing", "catalog_item_id": "other", "qty_base": 1}])
        result = evaluate(data, request)
        self.assertEqual(result["status"], "no_full_coverage")
        self.assertEqual(result["combinations"], [])
        self.assertEqual(result["uncovered_lines"][0]["line_ids"], ["missing"])

    def test_search_cap_returns_no_partial_ranking(self):
        data = snapshot(offers=[offer(f"offer-{number:02d}") for number in range(4)])
        result = evaluate(data, rfq(), max_combinations=3)
        self.assertEqual(result["status"], "search_limit")
        self.assertFalse(result["search_exhaustive"])
        self.assertEqual(result["enumerated_combinations"], 0)
        self.assertEqual(result["combinations"], [])
        self.assertIn("SEARCH_LIMIT", result["excluded_reasons"][-1]["reason_codes"])

    def test_vendor_minimum_budget_invoice_and_shipping_once(self):
        data = snapshot(offers=[offer("first", catalog_item_id="sku", package_size_base=1, package_price_irr=100000),
                                offer("second", catalog_item_id="other", package_size_base=1, package_price_irr=30000)],
                        vendors=[{"id": "v1", "name": "Vendor", "shipping_irr": 20000,
                                  "minimum_order_irr": 120000, "synthetic": True}],
                        catalog=[{"id": "sku"}, {"id": "other"}])
        request = rfq(lines=[{"id": "one", "catalog_item_id": "sku", "qty_base": 1},
                             {"id": "two", "catalog_item_id": "other", "qty_base": 1}],
                      requires_declared_invoice=True, budget_irr=150000)
        result = evaluate(data, request)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["combinations"][0]["total_irr"], 150000)
        self.assertEqual(result["combinations"][0]["shipping_total_irr"], 20000)
        data["offers"][1]["invoice_status"] = "unknown"
        result = evaluate(data, request)
        self.assertEqual(result["status"], "no_full_coverage")
        self.assertIn("INVOICE_NOT_DECLARED", result["excluded_reasons"][0]["reason_codes"])

    def test_duplicate_sku_lines_aggregate_stock(self):
        data = snapshot(offers=[offer(stock_packages=2)])
        request = rfq(lines=[{"id": "a", "catalog_item_id": "sku", "qty_base": 13},
                             {"id": "b", "catalog_item_id": "sku", "qty_base": 8}])
        result = evaluate(data, request)
        self.assertEqual(result["status"], "no_full_coverage")
        self.assertIn("INSUFFICIENT_STOCK", result["excluded_reasons"][0]["reason_codes"])

    def test_package_step_and_vendor_minimum_are_hard_constraints(self):
        data = snapshot(offers=[offer(min_packages=1, package_step=2, stock_packages=3)],
                        vendors=[{"id": "v1", "name": "Vendor", "shipping_irr": 5000,
                                  "minimum_order_irr": 400000, "synthetic": True}])
        rejected = evaluate(data, rfq(qty=13))
        self.assertEqual(rejected["status"], "no_full_coverage")
        self.assertIn("BELOW_VENDOR_MINIMUM_ORDER", rejected["excluded_reasons"][0]["reason_codes"])
        data["vendors"][0]["minimum_order_irr"] = 300000
        accepted = evaluate(data, rfq(qty=13))
        assignment = accepted["combinations"][0]["assignments"][0]
        self.assertEqual(assignment["purchased_packages"], 3)
        self.assertEqual(accepted["combinations"][0]["total_irr"], 305000)


if __name__ == "__main__":
    unittest.main()
