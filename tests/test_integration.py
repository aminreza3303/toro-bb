"""A complete raw fixture → RFQ search → sourcing decision smoke test."""

import json
import unittest
from pathlib import Path

from torob_business.data import load_demo
from torob_business.matching import resolve_rfq
from torob_business.ranking import evaluate


class EndToEndDemoTests(unittest.TestCase):
    def test_example_rfq_changes_winner_with_intent_and_keeps_provenance(self):
        snapshot = load_demo()
        example = Path(__file__).resolve().parents[1] / "examples" / "rfq_demo.json"
        rfq = json.loads(example.read_text(encoding="utf-8"))
        resolved = resolve_rfq(snapshot, rfq)
        self.assertEqual(resolved["status"], "ready")

        lowest = evaluate(snapshot, resolved["rfq"])
        self.assertEqual(lowest["status"], "ok")
        self.assertEqual(lowest["combinations"][0]["total_irr"], 865_000)
        self.assertEqual(lowest["combinations"][0]["offer_ids"], ["offer-card-01", "offer-card-03"])
        for assignment in lowest["combinations"][0]["assignments"]:
            self.assertEqual(assignment["provenance"]["snapshot_id"], "demo-v1")
            self.assertIsNotNone(assignment["provenance"]["raw_record_id"])
            self.assertIsNotNone(assignment["provenance"]["payload_hash"])

        fastest_rfq = {**resolved["rfq"], "preference": "fastest_delivery"}
        fastest = evaluate(snapshot, fastest_rfq)
        self.assertEqual(fastest["combinations"][0]["total_irr"], 1_150_000)
        self.assertEqual(fastest["combinations"][0]["max_lead_days"], 1)
        self.assertEqual(fastest["combinations"][0]["offer_ids"], ["offer-grid-03", "offer-grid-04"])
        self.assertEqual(lowest["input_hash"], evaluate(snapshot, resolved["rfq"])["input_hash"])


if __name__ == "__main__":
    unittest.main()
