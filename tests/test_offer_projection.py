"""Demo bridge tests for complete market captures and RFQ safety."""

from __future__ import annotations

import unittest

from torob_business.data import load_demo
from torob_business.matching import resolve_rfq
from torob_business.offer_projection import rankable_catalog_ids, rankable_offers
from torob_business.ranking import evaluate


class OfferProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load_demo()

    def test_only_complete_market_capture_enters_demo_ranker(self):
        projected = {offer["id"]: offer for offer in rankable_offers(self.snapshot)}
        printer_ids = {offer_id for offer_id in projected if offer_id.startswith("price-synthetic-printer")}
        self.assertEqual(len(printer_ids), 4)
        self.assertNotIn("price-digikala-printer-hp-laser-107a-21519", projected)
        self.assertNotIn("price-torob-ssd-verbatim-vi550-1tb", projected)
        self.assertIn("printer-hp-laser-107a", rankable_catalog_ids(self.snapshot))
        self.assertNotIn("ssd-verbatim-vi550-1tb", rankable_catalog_ids(self.snapshot))

    def test_complete_market_capture_can_rank_with_existing_demo_offer(self):
        resolution = resolve_rfq(self.snapshot, {
            "lines": [
                {"id": "printer", "catalog_item_id": "printer-hp-laser-107a", "qty_base": 1},
                {"id": "pen", "catalog_item_id": "pen-blue-07", "qty_base": 1},
            ],
            "preference": "lowest_cost",
        })
        self.assertEqual(resolution["status"], "ready")
        result = evaluate(self.snapshot, resolution["rfq"])
        self.assertEqual(result["status"], "ok")
        printer_assignment = next(
            assignment for assignment in result["combinations"][0]["assignments"]
            if assignment["catalog_item_id"] == "printer-hp-laser-107a"
        )
        self.assertTrue(printer_assignment["offer_id"].startswith("price-synthetic-printer"))
        self.assertEqual(printer_assignment["provenance"]["source_label"], "synthetic_fixture")

    def test_incomplete_market_capture_is_not_resolved_into_an_rfq(self):
        resolution = resolve_rfq(self.snapshot, {
            "lines": [
                {"id": "ssd", "catalog_item_id": "ssd-verbatim-vi550-1tb", "qty_base": 1},
                {"id": "pen", "catalog_item_id": "pen-blue-07", "qty_base": 1},
            ],
            "preference": "lowest_cost",
        })
        self.assertEqual(resolution["status"], "needs_match")
        ssd = next(match for match in resolution["matches"] if match["line_id"] == "ssd")
        self.assertEqual(ssd["method"], "no_rankable_offers")
        self.assertEqual(ssd["candidate_catalog_ids"], [])


if __name__ == "__main__":
    unittest.main()
