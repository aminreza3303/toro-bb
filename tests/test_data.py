"""Acceptance checks for the auditable synthetic import path."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from torob_business.data import load_dataset, load_demo


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load_demo()
        cls.offers = {offer["id"]: offer for offer in cls.snapshot["offers"]}

    def test_fixture_scope_and_two_raw_document_shapes(self):
        data = self.snapshot
        self.assertEqual(data["id"], "demo-v1")
        self.assertEqual(data["kind"], "synthetic")
        self.assertEqual({item["category"] for item in data["catalog"]},
                         {"نوشت‌افزار", "دفتر و کاغذ و مقوا", "ماوس", "صندلی اداری", "مانیتور", "کیبورد", "هارد و SSD", "پرینتر"})
        self.assertTrue(all(item.get("category_path") for item in data["catalog"]))
        self.assertEqual({item["category_path"][0] for item in data["catalog"]},
                         {"کتاب، لوازم تحریر و هنر", "لپ‌تاپ، کامپیوتر، اداری", "مبلمان و دکوراسیون اداری"})
        self.assertGreaterEqual(len(data["vendors"]), 5)
        self.assertLessEqual(len(data["vendors"]), 10)
        self.assertTrue(all(vendor["synthetic"] for vendor in data["vendors"] if vendor["id"] not in {"v-torob", "digikala"}))
        self.assertFalse(next(vendor for vendor in data["vendors"] if vendor["id"] == "v-torob")["synthetic"])
        self.assertFalse(next(vendor for vendor in data["vendors"] if vendor["id"] == "digikala")["synthetic"])
        self.assertEqual(len(data["market_prices"]), 43)
        self.assertGreaterEqual(len(data["decision_layer"]["contexts"]), 5)
        self.assertGreaterEqual(len(data["decision_layer"]["profiles"]), 12)
        self.assertTrue(any(profile["fitment_status"] == "needs_check" for profile in data["decision_layer"]["profiles"]))
        self.assertEqual({row["source_format"] for row in data["raw_offers"]}, {"listing_rows", "vendor_cards"})
        self.assertEqual(len(data["raw_offers"]), len(data["offers"]))

    def test_digikala_rows_keep_raw_provenance_and_unknown_values(self):
        rows = [row for row in self.snapshot["market_prices"] if row["supplier_id"] == "digikala"]
        self.assertEqual(len(rows), 5)
        self.assertEqual({row["match_status"] for row in rows}, {"exact"})
        self.assertEqual({row["price_irr"] for row in rows}, {None})
        self.assertEqual({row["raw_price_text"] for row in rows}, {"ناموجود"})
        self.assertTrue(all(row["source_url"].startswith("https://b2b.digikala.com/api/v1/products") for row in rows))
        self.assertTrue(all(row["captured_at"] and row["valid_at"] for row in rows))
        self.assertTrue(all(row["field_status"]["stock_packages"] == "not_reported" for row in rows))

    def test_marketplace_model_mismatch_is_quarantined(self):
        source_path = Path(__file__).resolve().parents[1] / "data" / "demo_raw.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        row = next(row for row in source["market_catalog"]["prices"] if row["supplier_id"] == "digikala")
        row["raw_title"] = "هارد اکسترنال وسترن دیجیتال مدل Elements ظرفیت 4 ترابایت"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variant.json"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            variant = load_dataset(path)
        self.assertNotIn(row["id"], {price["id"] for price in variant["market_prices"]})
        rejected = next(price for price in variant["rejected_market_prices"] if price["id"] == row["id"])
        self.assertEqual(rejected["rejection_reason"], "SKU_MISMATCH")

    def test_provenance_survives_normalization(self):
        data = self.snapshot
        raw_by_id = {row["id"]: row for row in data["raw_offers"]}
        for offer in data["offers"]:
            raw = raw_by_id[offer["raw_record_id"]]
            self.assertEqual(raw["source_label"], "synthetic_fixture")
            self.assertEqual(raw["snapshot_id"], data["id"])
            self.assertTrue(raw["source_document_id"])
            self.assertTrue(raw["generated_at"])
            self.assertEqual(len(raw["payload_hash"]), 64)
            self.assertEqual(raw["title"], raw["raw_title"])
            self.assertEqual(raw["price_text"], raw["raw_price_text"])
            self.assertEqual(raw["package_text"], raw["raw_unit_text"])
            self.assertEqual(offer["valid_at"], raw["generated_at"])
            self.assertTrue(offer["normalization_steps"] or offer["normalization_status"] == "rejected")

    def test_digits_currency_alias_and_package_conversion(self):
        pen = self.offers["offer-grid-01"]
        self.assertEqual((pen["catalog_item_id"], pen["package_size_base"], pen["package_price_irr"]),
                         ("pen-blue-07", 10, 100000))
        self.assertIn("digits:persian_arabic_to_ascii", pen["normalization_steps"])
        fast_pen = self.offers["offer-grid-03"]
        self.assertEqual(fast_pen["package_price_irr"], 130000)
        self.assertIn("currency:toman_to_irr_x10", fast_pen["normalization_steps"])
        paper_carton = self.offers["offer-grid-05"]
        self.assertEqual((paper_carton["catalog_item_id"], paper_carton["package_size_base"], paper_carton["package_price_irr"]),
                         ("paper-a4-80", 5, 24000000))
        self.assertEqual(self.offers["offer-card-04"]["package_size_base"], 1)
        self.assertEqual(self.offers["offer-card-06"]["catalog_item_id"], "pen-black-07")

    def test_ambiguous_and_invalid_rows_are_quarantined_without_defaults(self):
        expected = {
            "offer-grid-06": ("AMBIGUOUS_SKU", "catalog_item_id"),
            "offer-grid-07": ("UNKNOWN_UNIT", "package_size_base"),
            "offer-grid-08": ("UNKNOWN_CURRENCY", "package_price_irr"),
            "offer-grid-09": ("INVALID_PRICE", "package_price_irr"),
            "offer-grid-10": ("UNKNOWN_SKU", "catalog_item_id"),
            "offer-card-07": ("UNKNOWN_LEAD_TIME", "lead_days"),
            "offer-card-08": ("UNKNOWN_CURRENCY", "package_price_irr"),
            "offer-card-09": ("UNKNOWN_STOCK", "stock_packages"),
            "offer-card-10": ("UNKNOWN_SHIPPING", None),
        }
        for offer_id, (reason, missing_field) in expected.items():
            with self.subTest(offer_id=offer_id):
                offer = self.offers[offer_id]
                self.assertEqual(offer["normalization_status"], "rejected")
                self.assertEqual(offer["rejection_reason"], reason)
                self.assertIn(reason, offer["rejection_reasons"])
                if missing_field:
                    self.assertIsNone(offer[missing_field])
        self.assertTrue(all(offer["tax_status"] == "included" for offer in self.snapshot["offers"]
                            if offer["normalization_status"] == "accepted"))

    def test_loader_is_repeatable_and_independent_of_working_directory(self):
        original = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                second = load_demo()
        finally:
            os.chdir(original)
        self.assertEqual(self.snapshot, second)
        self.assertEqual(self.snapshot, load_dataset(
            os.path.join(os.path.dirname(__file__), "..", "data", "demo_raw.json")))

    def test_conflicting_specific_aliases_do_not_pick_the_longest_silently(self):
        source_path = Path(__file__).resolve().parents[1] / "data" / "demo_raw.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source["source_documents"][0]["records"][0]["headline"] = (
            "خودکار آبی 0.7 و خودکار 0.7 مشکی"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variant.json"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            variant = load_dataset(path)
        offer = next(row for row in variant["offers"] if row["id"] == "offer-grid-01")
        self.assertEqual(offer["normalization_status"], "rejected")
        self.assertEqual(offer["rejection_reason"], "AMBIGUOUS_SKU")
        self.assertIsNone(offer["catalog_item_id"])

    def test_conflicting_attribute_marker_is_quarantined(self):
        source_path = Path(__file__).resolve().parents[1] / "data" / "demo_raw.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source["source_documents"][0]["records"][1]["headline"] = "ماوس USB مدل M100 بی سیم"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variant.json"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            variant = load_dataset(path)
        offer = next(row for row in variant["offers"] if row["id"] == "offer-grid-02")
        self.assertEqual(offer["normalization_status"], "rejected")
        self.assertEqual(offer["rejection_reason"], "CONFLICTING_SPEC")
        self.assertIsNone(offer["catalog_item_id"])


if __name__ == "__main__":
    unittest.main()
