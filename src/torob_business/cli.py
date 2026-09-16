"""Offline demo for raw offers → normalization → RFQ matching → ranking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from torob_business.data import load_dataset, load_demo
from torob_business.matching import resolve_rfq, search_catalog
from torob_business.ranking import evaluate


def _demo_rfq(snapshot: dict) -> dict:
    catalog = {item["id"]: item for item in snapshot["catalog"]}
    try:
        pen = catalog["pen-blue-07"]["name"]
        mouse = catalog["mouse-usb-m100"]["name"]
    except KeyError as exc:
        raise ValueError("Custom fixtures need --rfq with their own catalog IDs or queries") from exc
    return {
        "lines": [
            {"id": "line-pen", "query_text": pen, "qty_base": 13},
            {"id": "line-mouse", "query_text": mouse, "qty_base": 2},
        ],
        "preference": "lowest_cost",
        "budget_irr": None,
        "max_lead_days": None,
        "requires_declared_invoice": False,
    }


def _print_summary(snapshot: dict, matches: list[dict], result: dict, *, trace: bool) -> None:
    accepted = sum(o["normalization_status"] == "accepted" for o in snapshot["offers"])
    print(f"Dataset {snapshot['id']} ({snapshot['kind']}): {len(snapshot['raw_offers'])} raw, {accepted} normalized, {len(snapshot['offers']) - accepted} quarantined")
    for match in matches:
        print(f"Match {match['line_id']}: {match['status']} → {match['selected_catalog_id']}")
    print(f"Evaluation: {result['status']}; preference={result['preference']}; exhaustive={result['search_exhaustive']}")
    if result["status"] != "ok":
        for line_id in result.get("uncovered_lines", []):
            print(f"Uncovered: {line_id}")
        for reason in result.get("excluded_reasons", [])[:8]:
            print(f"Excluded: {reason}")
        return
    offers = {offer["id"]: offer for offer in snapshot["offers"]}
    raw = {record["id"]: record for record in snapshot["raw_offers"]}
    for combo in result["combinations"][:3]:
        print(f"#{combo['rank']}: {combo['total_irr']:,} IRR; {combo['max_lead_days']} days; {combo['vendor_count']} vendor(s)")
        reason = combo["reason"]
        if reason.get("criterion") == "total_irr":
            detail = f"total cost {reason['value']:,} IRR"
        else:
            detail = f"delivery in {reason['value']} days"
        if "difference" in reason:
            detail += f"; difference from comparison {reason['difference']:,} {reason['difference_unit']}"
        if reason.get("tie_break"):
            detail += f"; tie broken by {reason['tie_break']}"
        print(f"  Reason: {detail}")
        for item in combo["assignments"]:
            print(
                f"  {item['offer_id']}: {item['purchased_packages']} package(s), "
                f"covers {item['covered_qty_base']} for {item['line_total_irr']:,} IRR"
            )
            if trace:
                norm = offers[item["offer_id"]]
                source = raw[norm["raw_record_id"]]
                print(f"    Raw: {source['title']} | {source['price_text']} | {source['package_text']}")
                print(f"    Transform: {', '.join(norm['normalization_steps'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Raw fixture JSON (default: bundled demo)")
    parser.add_argument("--rfq", type=Path, help="RFQ JSON (default: bundled two-item example)")
    parser.add_argument("--preference", choices=["lowest_cost", "fastest_delivery"])
    parser.add_argument("--search", help="Show catalog candidates for a query and exit")
    parser.add_argument("--max-combinations", type=int, default=10000)
    parser.add_argument("--trace", action="store_true", help="Show raw source and normalization for ranked offers")
    parser.add_argument("--json", action="store_true", help="Print structured result JSON")
    args = parser.parse_args(argv)

    try:
        snapshot = load_dataset(args.fixture) if args.fixture else load_demo()
        if args.search:
            print(json.dumps(search_catalog(snapshot, args.search), ensure_ascii=False, indent=2))
            return 0
        rfq = json.loads(args.rfq.read_text(encoding="utf-8")) if args.rfq else _demo_rfq(snapshot)
        if args.preference:
            rfq["preference"] = args.preference
        resolution = resolve_rfq(snapshot, rfq)
        if resolution["status"] != "ready":
            print(json.dumps(resolution["matches"], ensure_ascii=False, indent=2))
            return 2
        result = evaluate(snapshot, resolution["rfq"], max_combinations=args.max_combinations)
        if args.json:
            print(json.dumps({"matches": resolution["matches"], "result": result}, ensure_ascii=False, indent=2))
        else:
            _print_summary(snapshot, resolution["matches"], result, trace=args.trace)
        return 0 if result["status"] in {"ok", "no_full_coverage"} else 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
