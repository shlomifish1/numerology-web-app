from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
NUMEROLOGY_ROOT = SCRIPT_DIR.parent
if str(NUMEROLOGY_ROOT) not in sys.path:
    sys.path.insert(0, str(NUMEROLOGY_ROOT))

from calculators.registry import DEFAULT_CALCULATOR_ID, get_calculator
from book_calculations.run_internal_subject_map import run_subject_map

DEFINITION_PATH = SCRIPT_DIR / "sefer_hanumerologia_hashalem.definition.json"
REPORTS_DIR = SCRIPT_DIR / "reports"
JSON_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.closure_pass.json"
MD_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.closure_pass.md"

PROMOTION_METHODS: dict[str, str] = {
    # Label-matched aliases to existing methods.
    "personality_number": "birth_date_digit_sum_reduced",
    "civil_life_lesson": "birth_date_digit_sum_reduced",
    "life_lesson_number_civil": "birth_date_digit_sum_reduced",
    "outer_expression_calculation": "name_outer_behavior",
    "soul_expression_calculation": "name_soul_expression",
}

PROMOTION_NOTES: dict[str, str] = {
    "personality_number": "Promoted: formula steps explicitly describe civil birth-date digit sum + reduction.",
    "civil_life_lesson": "Promoted: direct alias of existing civil life-lesson entries using civil birth-date reduction.",
    "life_lesson_number_civil": "Promoted: direct alias of existing civil life-lesson entries using civil birth-date reduction.",
    "outer_expression_calculation": "Promoted: direct concept alias for outward-behavior method from name analysis.",
    "soul_expression_calculation": "Promoted: direct concept alias for soul-expression method from name analysis.",
}

FINAL_STATES = {
    "computable_with_trace",
    "computable_partial",
    "interpretation_only",
    "blocked_with_reason",
}

CORE_KEYS = [
    "destiny_path",
    "destiny_number",
    "expression_of_the_soul",
    "soul_expression_number",
    "behavior_number",
    "personality_number",
    "birth_number",
    "life_path_number",
    "civil_life_lesson",
    "life_lesson_number_civil",
]


def _load_definition() -> dict[str, Any]:
    return json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))


def _save_definition(payload: dict[str, Any]) -> None:
    DEFINITION_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _idx(calcs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(calc.get("calc_key")): calc for calc in calcs}


def _is_meaningful_table(table: Any) -> bool:
    if not isinstance(table, dict) or not table:
        return False
    return any(str(key).strip().lstrip("-").isdigit() for key in table.keys())


def _canonical_tables(calcs: list[dict[str, Any]]) -> dict[str, tuple[str, dict[str, Any]]]:
    best: dict[str, tuple[str, dict[str, Any]]] = {}
    for calc in calcs:
        method = str((calc.get("execution") or {}).get("method") or "").strip()
        if not method:
            continue
        table = calc.get("interpretations_by_value") or {}
        if not _is_meaningful_table(table):
            continue
        existing = best.get(method)
        if existing is None or len(table) > len(existing[1]):
            best[method] = (str(calc.get("calc_key")), table)
    return best


def _finalize_state(calc: dict[str, Any]) -> None:
    status = str(calc.get("status") or "").strip()
    blocked_reason = str(calc.get("blocked_reason") or "").strip()

    if status == "computable":
        calc["final_state"] = "computable_with_trace"
        calc["final_reason_bucket"] = ""
        return

    if blocked_reason == "interpretation_only":
        calc["final_state"] = "interpretation_only"
        calc["final_reason_bucket"] = "interpretation_only"
        return

    if not blocked_reason:
        formula_text = str(calc.get("formula_text") or "").strip()
        blocked_reason = "missing_formula" if not formula_text else "unsupported_executor_type"
        calc["blocked_reason"] = blocked_reason

    calc["final_state"] = "blocked_with_reason"
    calc["final_reason_bucket"] = blocked_reason


def _rank_unresolved(calcs: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for calc in calcs:
        if str(calc.get("final_state")) != "blocked_with_reason":
            continue
        key = str(calc.get("calc_key") or "")
        label = str(calc.get("label_he") or "")
        reason = str(calc.get("final_reason_bucket") or calc.get("blocked_reason") or "")
        deps = calc.get("input_dependencies") or []

        text = f"{key} {label}".lower()
        priority = 0
        if any(token in text for token in ("destiny", "soul", "life", "personality", "גורל", "נשמה", "שיעור חיים", "אישיות")):
            priority += 3
        if reason in {"unsupported_executor_type", "missing_input_mapping"}:
            priority += 2
        if isinstance(deps, list) and len(deps) <= 2:
            priority += 1

        scored.append(
            (
                priority,
                {
                    "calc_key": key,
                    "label_he": label,
                    "reason_bucket": reason,
                    "input_dependencies": deps,
                    "formula_text": str(calc.get("formula_text") or ""),
                },
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1]["calc_key"]))
    return [item[1] for item in scored[:limit]]


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    before = _load_definition()
    before_calcs = before.get("calculations", [])
    before_idx = _idx(before_calcs)

    after = copy.deepcopy(before)
    after["definition_version"] = "1.1.0"
    after["closure_pass"] = {
        "pass_id": "sefer_hanumerologia_hashalem_closure_wave_1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "single_book_closure",
    }
    calcs = after.get("calculations", [])
    calc_index = _idx(calcs)

    promoted: list[str] = []
    for calc_key, method in PROMOTION_METHODS.items():
        calc = calc_index.get(calc_key)
        if not calc:
            continue
        was_computable = str(calc.get("status") or "") == "computable"
        calc["status"] = "computable"
        calc["blocked_reason"] = None
        calc["execution"] = {"method": method}
        review = calc.get("needs_review")
        if not isinstance(review, dict):
            review = {}
        review["closure_wave"] = "promoted"
        review["closure_note"] = PROMOTION_NOTES.get(calc_key, "Promoted in closure wave")
        calc["needs_review"] = review
        if not was_computable:
            promoted.append(calc_key)

    canonical_tables = _canonical_tables(calcs)
    interpretation_updates: list[str] = []
    for calc in calcs:
        method = str((calc.get("execution") or {}).get("method") or "").strip()
        if not method:
            continue
        if str(calc.get("status") or "") != "computable":
            continue
        table = calc.get("interpretations_by_value") or {}
        if isinstance(table, dict) and table:
            continue
        source = canonical_tables.get(method)
        if not source:
            continue
        source_key, source_table = source
        calc["interpretations_by_value"] = copy.deepcopy(source_table)
        calc["interpretation_table_source_calc_key"] = source_key
        interpretation_updates.append(str(calc.get("calc_key")))

    for calc in calcs:
        _finalize_state(calc)
        if str(calc.get("final_state") or "") not in FINAL_STATES:
            calc["final_state"] = "blocked_with_reason"
            calc["final_reason_bucket"] = str(calc.get("blocked_reason") or "unsupported_executor_type")

    _save_definition(after)

    sample_payload = {
        "full_name": "\u05d3\u05e0\u05d9 \u05db\u05d4\u05df",
        "birth_date": "1990-05-17",
        "current_year": 2029,
        "letter": "\u05d0",
    }
    runtime_report = run_subject_map(sample_payload)
    runtime_calcs = runtime_report.get("calculations", [])
    runtime_by_key = {str(item.get("calc_key")): item for item in runtime_calcs}

    final_state_counts = Counter(str(calc.get("final_state") or "") for calc in calcs)
    blocked_counts = Counter(
        str(calc.get("final_reason_bucket") or calc.get("blocked_reason") or "unclassified")
        for calc in calcs
        if str(calc.get("final_state")) == "blocked_with_reason"
    )

    computed_with_interpretation = 0
    computed_without_interpretation = 0
    for item in runtime_calcs:
        if str(item.get("status")) != "computed":
            continue
        if str(item.get("interpretation") or "").strip():
            computed_with_interpretation += 1
        else:
            computed_without_interpretation += 1

    core_coverage: list[dict[str, Any]] = []
    for key in CORE_KEYS:
        definition_calc = _idx(calcs).get(key) or {}
        runtime_calc = runtime_by_key.get(key) or {}
        core_coverage.append(
            {
                "calc_key": key,
                "label_he": definition_calc.get("label_he"),
                "final_state": definition_calc.get("final_state"),
                "reason_bucket": definition_calc.get("final_reason_bucket"),
                "runtime_status": runtime_calc.get("status"),
                "has_runtime_trace": bool(runtime_calc.get("trace_is_full")),
            }
        )

    unresolved_top = _rank_unresolved(calcs, limit=15)

    ready_as_template = (
        final_state_counts.get("computable_with_trace", 0) >= 90
        and blocked_counts.get("missing_formula", 0) <= 10
        and blocked_counts.get("unsupported_executor_type", 0) <= 140
    )

    green_legacy_ok = False
    try:
        green_result = get_calculator(DEFAULT_CALCULATOR_ID).calculate(
            {
                "day": "17",
                "month": "05",
                "year": "1990",
                "first_name": "דני",
                "last_name": "כהן",
                "gender": "male",
            }
        )
        green_legacy_ok = bool(green_result.get("results"))
    except Exception:
        green_legacy_ok = False

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "book_id": after.get("book_id"),
        "definition_version_before": before.get("definition_version"),
        "definition_version_after": after.get("definition_version"),
        "total_entries": len(calcs),
        "final_state_counts": dict(final_state_counts),
        "blocked_counts_by_reason": dict(sorted(blocked_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "computed_with_interpretation": computed_with_interpretation,
        "computed_without_interpretation": computed_without_interpretation,
        "runtime_summary": runtime_report.get("summary"),
        "sample_payload": sample_payload,
        "newly_promoted_calculations": sorted(promoted),
        "interpretation_tables_added_count": len(interpretation_updates),
        "interpretation_tables_added_calculations": sorted(interpretation_updates),
        "core_calculations_coverage": core_coverage,
        "top_remaining_unresolved": unresolved_top,
        "ready_as_template_for_future_ocr": bool(ready_as_template),
        "green_legacy_still_works": green_legacy_ok,
        "no_production_switch": True,
        "no_second_book_added": True,
        "no_ocr_work_started": True,
        "no_broad_ui_redesign": True,
    }

    JSON_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Sefer Book Closure Pass",
        "",
        f"Generated: {report['generated_at']}",
        f"Definition version: {report['definition_version_before']} -> {report['definition_version_after']}",
        f"- Total entries: {report['total_entries']}",
        f"- computable_with_trace: {final_state_counts.get('computable_with_trace', 0)}",
        f"- computable_partial: {final_state_counts.get('computable_partial', 0)}",
        f"- interpretation_only: {final_state_counts.get('interpretation_only', 0)}",
        f"- blocked_with_reason: {final_state_counts.get('blocked_with_reason', 0)}",
        f"- Computed with interpretation (sample runtime): {computed_with_interpretation}",
        f"- Computed without interpretation (sample runtime): {computed_without_interpretation}",
        f"- Newly promoted calculations: {len(promoted)}",
        f"- Interpretation tables added: {len(interpretation_updates)}",
        "",
        "## Newly Promoted Calculations",
    ]

    if promoted:
        for key in sorted(promoted):
            lines.append(f"- `{key}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Blocked Counts By Reason"])
    for reason, count in sorted(blocked_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- `{reason}`: {count}")

    lines.extend(["", "## Core Calculations Coverage"])
    for item in core_coverage:
        lines.append(
            f"- `{item['calc_key']}` | final_state=`{item['final_state']}` | runtime=`{item['runtime_status']}` | trace={item['has_runtime_trace']}"
        )

    lines.extend(["", "## Top Remaining Unresolved"])
    for item in unresolved_top:
        lines.append(f"- `{item['calc_key']}` | reason=`{item['reason_bucket']}` | deps={item['input_dependencies']}")

    lines.extend(
        [
            "",
            "## Template Readiness",
            f"- ready_as_template_for_future_ocr: `{bool(ready_as_template)}`",
            f"- green_legacy_still_works: `{green_legacy_ok}`",
        ]
    )

    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
