import unittest

from torob_business.matching import exact_sku_match, normalize_query, resolve_rfq, search_catalog


SNAPSHOT = {
    "catalog": [
        {"id": "pen-blue", "category": "office", "name": "خودکار آبی", "aliases": ["خودکار آبي", "blue pen"], "base_unit": "عدد"},
        {"id": "pen-black", "category": "office", "name": "خودکار مشکی", "aliases": ["black pen"], "base_unit": "عدد"},
    ],
    "offers": [
        {"catalog_item_id": "pen-blue", "normalization_status": "accepted"},
        {"catalog_item_id": "pen-blue", "normalization_status": "rejected"},
    ],
}


class MatchingTests(unittest.TestCase):
    def test_normalizes_arabic_letters(self):
        self.assertEqual(normalize_query("خودكار آبي"), normalize_query("خودکار آبی"))
        self.assertEqual(normalize_query("خودکار آبی ۰٫۷"), normalize_query("خودکار آبی 0.7"))

    def test_exact_alias_resolves(self):
        result = resolve_rfq(SNAPSHOT, {"lines": [{"id": "l1", "query_text": "خودكار آبي", "qty_base": 13}]})
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["rfq"]["lines"][0]["catalog_item_id"], "pen-blue")

    def test_partial_search_requires_selection(self):
        matches = search_catalog(SNAPSHOT, "خودکار")
        self.assertEqual(len(matches), 2)
        self.assertEqual({m["catalog_item_id"]: m["offer_count"] for m in matches}["pen-blue"], 1)
        result = resolve_rfq(SNAPSHOT, {"lines": [{"id": "l1", "query_text": "خودکار", "qty_base": 13}]})
        self.assertEqual(result["status"], "needs_match")
        self.assertEqual(result["matches"][0]["status"], "ambiguous")

    def test_unknown_query_is_unmatched(self):
        result = resolve_rfq(SNAPSHOT, {"lines": [{"id": "l1", "query_text": "کاغذ", "qty_base": 1}]})
        self.assertEqual(result["matches"][0]["status"], "unmatched")

    def test_explicit_sku_cannot_override_contradictory_query_or_specs(self):
        with self.assertRaisesRegex(ValueError, "query is incompatible"):
            resolve_rfq(SNAPSHOT, {"lines": [{
                "id": "l1", "query_text": "خودکار آبی", "catalog_item_id": "pen-black", "qty_base": 1,
            }]})
        with self.assertRaisesRegex(ValueError, "specs incompatible"):
            resolve_rfq(SNAPSHOT, {"lines": [{
                "id": "l1", "catalog_item_id": "pen-blue", "requested_specs": {"color": "black"}, "qty_base": 1,
            }]})

    def test_exact_market_sku_requires_capacity(self):
        item = {"specs": {"model": "S20", "capacity": "1TB"}}
        self.assertTrue(exact_sku_match(item, "اس اس دی ادلینک مدل S20 ظرفیت 1 ترابایت"))
        self.assertFalse(exact_sku_match(item, "اس اس دی ادلینک مدل S20 ظرفیت 512 گیگابایت"))
        self.assertFalse(exact_sku_match(item, "اس اس دی ادلینک مدل S30 ظرفیت 1 ترابایت"))


if __name__ == "__main__":
    unittest.main()
