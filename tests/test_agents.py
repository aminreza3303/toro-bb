"""Contract tests for the deterministic multi-agent analysis graph."""

from __future__ import annotations

import copy
import unittest

from torob_business.agents import AgentRuntime, agent_manifest, build_source_comparison, run_agent_analysis
from torob_business.data import load_demo
from torob_business.database import CatalogDatabase


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load_demo()
        cls.database = CatalogDatabase(":memory:")
        cls.database.sync_snapshot(cls.snapshot)

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    def test_exact_sku_analysis_is_traceable_and_preserves_unknowns(self):
        item = self.database.get_product("ssd-verbatim-vi550-1tb")
        analysis = run_agent_analysis(self.snapshot, item)

        self.assertEqual(analysis["status"], "completed")
        self.assertEqual(analysis["execution_mode"], "deterministic-local")
        self.assertEqual(analysis["agent_count"], 5)
        self.assertEqual(
            [step["agent_id"] for step in analysis["trace"]],
            ["sku-guardian", "provenance-auditor", "source-comparator", "decision-context", "synthesis"],
        )
        self.assertEqual(analysis["artifacts"]["sku-guardian"]["exact_marketplace_records"], [
            "price-digikala-ssd-verbatim-vi550-1tb-40653",
        ])
        self.assertEqual(analysis["artifacts"]["synthesis"]["exact_match_count"], 1)
        self.assertIn("قیمت", analysis["artifacts"]["synthesis"]["unknown_fields"])
        self.assertEqual(analysis["quality_gates"], {
            "no_price_invention": True,
            "exact_sku_only": True,
            "provenance_audited": True,
        })

    def test_manifest_exposes_skills_and_dependency_graph(self):
        manifest = agent_manifest()
        self.assertEqual(manifest["runtime"]["orchestration"], "dependency-aware DAG")
        self.assertIsNone(manifest["runtime"]["model_provider"])
        self.assertEqual(
            manifest["runtime"]["execution_plan"]["layers"],
            [["sku-guardian"], ["provenance-auditor", "decision-context"], ["source-comparator"], ["synthesis"]],
        )
        self.assertEqual(manifest["runtime"]["execution_plan"]["max_parallelism"], 2)
        agents = {agent["id"]: agent for agent in manifest["agents"]}
        self.assertEqual(agents["source-comparator"]["depends_on"], ["sku-guardian", "provenance-auditor"])
        self.assertIn("exact-sku-guard", [skill["id"] for skill in agents["sku-guardian"]["skills"]])
        self.assertIn("quality-gates", [skill["id"] for skill in agents["synthesis"]["skills"]])
        self.assertTrue(agents["source-comparator"]["retry_safe"])

    def test_analysis_exposes_stable_plan_and_trace_attempts(self):
        item = self.database.get_product("ssd-verbatim-vi550-1tb")
        analysis = run_agent_analysis(self.snapshot, item)
        self.assertEqual(analysis["execution_plan"]["failure_mode"], "fail-closed")
        self.assertEqual([step["attempts"] for step in analysis["trace"]], [1, 1, 1, 1, 1])

    def test_runtime_rejects_invalid_execution_policy(self):
        with self.assertRaisesRegex(ValueError, "max_parallelism"):
            AgentRuntime(max_parallelism=0)
        with self.assertRaisesRegex(ValueError, "max_attempts"):
            AgentRuntime(max_attempts=0)

    def test_non_exact_marketplace_row_is_blocked_from_agent_comparison(self):
        item = copy.deepcopy(self.database.get_product("ssd-verbatim-vi550-1tb"))
        variant = copy.deepcopy(item["prices"][1])
        variant.update({"price_id": "price-digikala-wrong-model", "match_status": "model_mismatch"})
        item["prices"].append(variant)

        analysis = run_agent_analysis(self.snapshot, item)
        sku = analysis["artifacts"]["sku-guardian"]
        self.assertIn("price-digikala-wrong-model", sku["blocked_marketplace_records"])
        self.assertNotIn("price-digikala-wrong-model", sku["exact_marketplace_records"])
        self.assertEqual(build_source_comparison([variant])["sources"], [])
        self.assertFalse(analysis["quality_gates"]["exact_sku_only"])

    def test_runtime_rejects_dependency_cycles(self):
        class FakeAgent:
            def __init__(self, agent_id, dependencies):
                self.id = agent_id
                self.role = agent_id
                self.dependencies = dependencies
                self.skills = ()

            def run(self, context):
                return {}

        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            AgentRuntime((FakeAgent("a", ("b",)), FakeAgent("b", ("a",))))

        with self.assertRaisesRegex(ValueError, "agent ids must be unique"):
            AgentRuntime((FakeAgent("same", ()), FakeAgent("same", ())))


if __name__ == "__main__":
    unittest.main()
