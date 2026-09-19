"""Deterministic multi-agent runtime for auditable catalog analysis.

The demo does not pretend that a language model is required for every step.
Each agent owns one narrow skill contract, runs in a dependency-aware graph,
and emits a trace plus evidence. A model provider can be plugged in later at
the synthesis boundary without moving SKU or provenance guardrails out of
deterministic code.
"""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentSkill:
    id: str
    description: str
    kind: str = "deterministic-tool"


@dataclass(frozen=True)
class AgentTrace:
    agent_id: str
    role: str
    status: str
    skills: tuple[str, ...]
    input_artifacts: tuple[str, ...]
    output_artifacts: tuple[str, ...]
    evidence_count: int
    duration_ms: int
    attempts: int
    error: str | None = None


class AgentContext:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.artifacts: dict[str, dict[str, Any]] = {}


class Agent(Protocol):
    id: str
    role: str
    dependencies: tuple[str, ...]
    skills: tuple[AgentSkill, ...]
    retry_safe: bool

    def run(self, context: AgentContext) -> dict[str, Any]: ...


def _unknown_fields(price: dict[str, Any]) -> list[str]:
    labels = {
        "price_irr": "قیمت",
        "stock_packages": "موجودی",
        "lead_days": "زمان تحویل",
        "package_size_base": "واحد بسته",
        "invoice_status": "وضعیت فاکتور",
    }
    field_status = price.get("field_status", {})
    return [
        label for field, label in labels.items()
        if price.get(field) is None
        or field_status.get(field) in {"unknown", "not_reported", "unavailable"}
    ]


def build_source_comparison(prices: list[dict[str, Any]]) -> dict[str, Any]:
    """Build source groups for both the API and the comparison agent."""
    grouped: dict[str, dict[str, Any]] = {}
    # A non-exact marketplace row is evidence of a rejected candidate, not a
    # comparable offer. Keep the guard at this shared boundary so both the API
    # and the agent graph inherit the same no-cross-model rule.
    eligible_prices = [
        price for price in prices
        if price.get("supplier_id") != "digikala" or price.get("match_status") == "exact"
    ]
    for price in eligible_prices:
        supplier_id = price.get("supplier_id") or "unknown"
        group = grouped.setdefault(supplier_id, {
            "supplier_id": supplier_id,
            "supplier_name": price.get("supplier_name") or supplier_id,
            "supplier_kind": price.get("supplier_kind"),
            "supplier_source": price.get("supplier_source"),
            "source_labels": [],
            "records": [],
            "unknown_fields": [],
            "sku_match_status": "unknown",
        })
        if price.get("source_label") and price["source_label"] not in group["source_labels"]:
            group["source_labels"].append(price["source_label"])
        group["records"].append(price)
        match_status = price.get("match_status")
        if match_status == "exact":
            group["sku_match_status"] = "exact"
        elif group["sku_match_status"] == "unknown" and match_status:
            group["sku_match_status"] = match_status
        for field in _unknown_fields(price):
            if field not in group["unknown_fields"]:
                group["unknown_fields"].append(field)

    sources = list(grouped.values())
    for group in sources:
        group["record_count"] = len(group["records"])
        group["source_urls"] = sorted({
            record["source_url"] for record in group["records"] if record.get("source_url")
        })
    return {
        "overlap": any(group["supplier_id"] == "digikala" for group in sources) and len(sources) > 1,
        "sources": sources,
        "unknown_differences": sorted({
            field for group in sources for field in group["unknown_fields"]
        }),
    }


class SkuGuardianAgent:
    id = "sku-guardian"
    role = "exact SKU and comparison safety"
    dependencies: tuple[str, ...] = ()
    retry_safe = True
    skills = (
        AgentSkill("exact-sku-guard", "Allow a marketplace row only when its exact match status is explicit."),
        AgentSkill("variant-conflict-check", "Keep model and capacity variants out of the same comparison."),
    )

    def run(self, context: AgentContext) -> dict[str, Any]:
        item = context.payload["item"]
        prices = context.payload.get("prices", [])
        marketplace = [price for price in prices if price.get("supplier_id") == "digikala"]
        exact = [price["price_id"] for price in marketplace if price.get("match_status") == "exact"]
        blocked = [price["price_id"] for price in marketplace if price.get("match_status") != "exact"]
        return {
            "catalog_item_id": item.get("id"),
            "catalog_model": item.get("specs", {}).get("model"),
            "exact_marketplace_records": exact,
            "blocked_marketplace_records": blocked,
            "policy": "exact_model_and_required_variant_specs_only",
        }


class ProvenanceAuditorAgent:
    id = "provenance-auditor"
    role = "source evidence and uncertainty audit"
    dependencies = ("sku-guardian",)
    retry_safe = True
    skills = (
        AgentSkill("provenance-audit", "Require source URL, capture time, raw title and raw price text."),
        AgentSkill("unknown-preservation", "Keep missing price, stock and lead time as unknown instead of defaults."),
    )

    def run(self, context: AgentContext) -> dict[str, Any]:
        prices = context.payload.get("prices", [])
        records = []
        for price in prices:
            missing = [
                field for field in ("source_url", "valid_at", "raw_title", "raw_price_text")
                if not price.get(field)
            ]
            records.append({
                "price_id": price.get("price_id"),
                "supplier_id": price.get("supplier_id"),
                "missing_required_fields": missing,
                "field_status": price.get("field_status", {}),
            })
        complete = sum(not record["missing_required_fields"] for record in records)
        return {
            "records": records,
            "complete_record_count": complete,
            "record_count": len(records),
            "all_required_provenance_present": complete == len(records),
        }


class SourceComparisonAgent:
    id = "source-comparator"
    role = "supplier separation and unknown-difference analysis"
    dependencies = ("sku-guardian", "provenance-auditor")
    retry_safe = True
    skills = (
        AgentSkill("source-grouping", "Keep ترب and دیجی‌کالا as independent source groups."),
        AgentSkill("uncertainty-diff", "Report fields that cannot be compared from captured evidence."),
    )

    def run(self, context: AgentContext) -> dict[str, Any]:
        comparison = build_source_comparison(context.payload.get("prices", []))
        return {
            "overlap": comparison["overlap"],
            "source_ids": [source["supplier_id"] for source in comparison["sources"]],
            "unknown_differences": comparison["unknown_differences"],
            "sources": [
                {
                    key: source[key]
                    for key in (
                        "supplier_id", "supplier_name", "source_labels", "record_count",
                        "source_urls", "unknown_fields", "sku_match_status",
                    )
                }
                for source in comparison["sources"]
            ],
        }


class DecisionContextAgent:
    id = "decision-context"
    role = "fitment and purchase-decision context"
    dependencies = ("sku-guardian",)
    retry_safe = True
    skills = (
        AgentSkill("fitment-context", "Expose the product decision profile before price ranking."),
        AgentSkill("buyer-checklist", "Return the checks a buyer should confirm before ordering."),
    )

    def run(self, context: AgentContext) -> dict[str, Any]:
        decision = context.payload["item"].get("decision") or {}
        return {
            "enabled": bool(decision.get("enabled")),
            "fitment_status": decision.get("fitment_status"),
            "summary": decision.get("summary"),
            "checks_before_buying": decision.get("checks_before_buying", []),
            "comparison_differences": (decision.get("comparison") or {}).get("differences", []),
        }


class SynthesisAgent:
    id = "synthesis"
    role = "evidence-bound buyer-facing synthesis"
    dependencies = ("provenance-auditor", "source-comparator", "decision-context")
    retry_safe = True
    skills = (
        AgentSkill("evidence-bound-summary", "Summarize only artifacts emitted by upstream agents."),
        AgentSkill("quality-gates", "Refuse invented prices, stock and cross-model comparisons."),
    )

    def run(self, context: AgentContext) -> dict[str, Any]:
        comparison = context.artifacts["source-comparator"]
        provenance = context.artifacts["provenance-auditor"]
        sku = context.artifacts["sku-guardian"]
        source_count = len(comparison["source_ids"])
        if comparison["overlap"]:
            summary = f"{source_count} منبع برای SKU دقیق بررسی شد؛ تفاوت‌های نامعلوم حفظ شده‌اند."
        else:
            summary = "برای این SKU هم‌پوشانی دقیق چندمنبعی ثبت نشده است."
        return {
            "summary_fa": summary,
            "exact_match_count": len(sku["exact_marketplace_records"]),
            "unknown_fields": comparison["unknown_differences"],
            "quality_gates": {
                "no_price_invention": True,
                "exact_sku_only": not sku["blocked_marketplace_records"],
                "provenance_audited": provenance["all_required_provenance_present"],
            },
            "next_actions": [
                "قیمت و موجودی نامعلوم را از منبع اصلی دوباره بررسی کن."
                if comparison["unknown_differences"] else "دادهٔ قابل‌مقایسهٔ بیشتری لازم نیست.",
            ],
        }


class AgentRuntime:
    """Run registered agents as a bounded, dependency-aware local graph.

    The graph is compiled into deterministic layers. Agents in one layer only
    read artifacts from earlier layers, so independent work can run in parallel
    without changing trace order or the final result. Retries are opt-in at the
    agent level and only apply to retry-safe, side-effect-free work.
    """

    def __init__(
        self,
        agents: tuple[Agent, ...] | None = None,
        *,
        max_parallelism: int = 2,
        max_attempts: int = 1,
    ):
        if max_parallelism < 1:
            raise ValueError("max_parallelism must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.agents = agents or (
            SkuGuardianAgent(),
            ProvenanceAuditorAgent(),
            SourceComparisonAgent(),
            DecisionContextAgent(),
            SynthesisAgent(),
        )
        self._agents = {agent.id: agent for agent in self.agents}
        if len(self._agents) != len(self.agents):
            raise ValueError("agent ids must be unique")
        self.max_parallelism = max_parallelism
        self.max_attempts = max_attempts
        self._order = self._topological_order()
        self._layers = self._execution_layers()

    def _topological_order(self) -> list[Agent]:
        order: list[Agent] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(agent_id: str) -> None:
            if agent_id in visited:
                return
            if agent_id in visiting:
                raise ValueError(f"agent dependency cycle at {agent_id}")
            if agent_id not in self._agents:
                raise ValueError(f"unknown agent dependency: {agent_id}")
            visiting.add(agent_id)
            for dependency in self._agents[agent_id].dependencies:
                visit(dependency)
            visiting.remove(agent_id)
            visited.add(agent_id)
            order.append(self._agents[agent_id])

        for agent in self.agents:
            visit(agent.id)
        return order

    def _execution_layers(self) -> tuple[tuple[str, ...], ...]:
        """Compile the DAG into stable layers that can run concurrently."""
        depth: dict[str, int] = {}
        for agent in self._order:
            depth[agent.id] = max((depth[dependency] + 1 for dependency in agent.dependencies), default=0)
        layers: list[list[str]] = []
        for agent in self._order:
            while len(layers) <= depth[agent.id]:
                layers.append([])
            layers[depth[agent.id]].append(agent.id)
        return tuple(tuple(layer) for layer in layers)

    def execution_plan(self) -> dict[str, Any]:
        """Return the stable plan exposed to the UI and operator tooling."""
        return {
            "layers": [list(layer) for layer in self._layers],
            "max_parallelism": self.max_parallelism,
            "max_attempts": self.max_attempts,
            "failure_mode": "fail-closed",
        }

    def manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "id": agent.id,
                "role": agent.role,
                "depends_on": list(agent.dependencies),
                "skills": [asdict(skill) for skill in agent.skills],
                "retry_safe": bool(getattr(agent, "retry_safe", False)),
            }
            for agent in self._order
        ]

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = AgentContext(payload)
        trace_by_id: dict[str, AgentTrace] = {}
        run_key = f"{payload.get('snapshot_id', 'snapshot')}:{payload.get('item', {}).get('id', 'item')}"
        run_id = "agent-run-" + hashlib.sha256(run_key.encode("utf-8")).hexdigest()[:16]
        failure: AgentTrace | None = None

        def execute(agent: Agent) -> tuple[AgentTrace, dict[str, Any] | None]:
            started = time.perf_counter()
            attempts = 0
            last_error: Exception | None = None
            while attempts < self.max_attempts:
                attempts += 1
                try:
                    artifact = agent.run(context)
                    output_keys = tuple(sorted(artifact))
                    evidence_count = len(artifact.get("records", []))
                    return AgentTrace(
                        agent.id, agent.role, "completed", tuple(skill.id for skill in agent.skills),
                        tuple(agent.dependencies), output_keys, evidence_count,
                        int((time.perf_counter() - started) * 1000), attempts,
                    ), artifact
                except Exception as error:  # pragma: no cover - defensive runtime boundary
                    last_error = error
                    if not getattr(agent, "retry_safe", False):
                        break
            return AgentTrace(
                agent.id, agent.role, "failed", tuple(skill.id for skill in agent.skills),
                tuple(agent.dependencies), (), 0,
                int((time.perf_counter() - started) * 1000), attempts, str(last_error),
            ), None

        for layer in self._layers:
            agents = [self._agents[agent_id] for agent_id in layer]
            with ThreadPoolExecutor(max_workers=min(self.max_parallelism, len(agents))) as pool:
                futures = {pool.submit(execute, agent): agent for agent in agents}
                for future in as_completed(futures):
                    agent = futures[future]
                    step, artifact = future.result()
                    trace_by_id[agent.id] = step
                    if step.status == "failed":
                        failure = step
                    elif artifact is not None:
                        context.artifacts[agent.id] = artifact
            if failure is not None:
                break

        trace = [trace_by_id[agent.id] for agent in self._order if agent.id in trace_by_id]
        if failure is not None:
            return {
                "run_id": run_id,
                "status": "failed",
                "execution_mode": "deterministic-local",
                "execution_plan": self.execution_plan(),
                "trace": [asdict(step) for step in trace],
                "error": failure.error,
            }
        return {
            "run_id": run_id,
            "status": "completed",
            "execution_mode": "deterministic-local",
            "execution_plan": self.execution_plan(),
            "agent_count": len(self._order),
            "trace": [asdict(step) for step in trace],
            "artifacts": context.artifacts,
            "quality_gates": context.artifacts["synthesis"]["quality_gates"],
        }


def run_agent_analysis(snapshot: dict[str, Any], item: dict[str, Any], runtime: AgentRuntime | None = None) -> dict[str, Any]:
    """Run the default agent graph for one API product detail."""
    active_runtime = runtime or AgentRuntime()
    return active_runtime.run({
        "snapshot_id": snapshot.get("id"),
        "item": item,
        "prices": item.get("prices", []),
    })


def agent_manifest(runtime: AgentRuntime | None = None) -> dict[str, Any]:
    active_runtime = runtime or AgentRuntime()
    return {
        "runtime": {
            "name": "torob-business-agent-runtime",
            "mode": "deterministic-local",
            "orchestration": "dependency-aware DAG",
            "execution_plan": active_runtime.execution_plan(),
            "model_provider": None,
            "guardrails": ["exact SKU only", "no invented price or stock", "provenance required"],
        },
        "agents": active_runtime.manifest(),
    }
