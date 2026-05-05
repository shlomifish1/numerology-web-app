from __future__ import annotations

import copy
import json
from collections import Counter
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
JSON_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.executor_wave_2.json"
MD_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.executor_wave_2.md"

SAMPLE_PAYLOAD = {
    "full_name": "\u05d3\u05e0\u05d9 \u05db\u05d4\u05df",
    "birth_date": "1990-05-17",
    "current_year": 2029,
    "letter": "\u05d0",
}

# Family 1: Civil life-path reduction aliases
FAMILY_CIVIL_REDUCTION = {
    "\u05e9\u05d9\u05e2\u05d5\u05e8_\u05d4\u05d7\u05d9\u05d9\u05dd_\u05d4\u05d0\u05d6\u05e8\u05d7\u05d9": "birth_date_digit_sum_reduced",
    "\u05d7\u05d9\u05e9\u05d5\u05d1_\u05de\u05e1\u05e4\u05e8_\u05d4\u05dc\u05d9\u05d3\u05d4": "birth_date_digit_sum_reduced",
    "karma_number": "birth_date_digit_sum_reduced",
}

# Family 2: Civil date components and cycle anchors
FAMILY_DATE_COMPONENTS = {
    "source_chapter_17": "month_of_birth",
    "\u05d7\u05d5\u05d3\u05e9_\u05dc\u05d9\u05d3\u05d4_\u05d0\u05d6\u05e8\u05d7\u05d9": "month_of_birth",
    "\u05ea\u05e7\u05d5\u05e4\u05ea_\u05d4\u05de\u05d7\u05d6\u05d5\u05e8_\u05d4\u05e9\u05e0\u05d9": "month_of_birth",
    "\u05de\u05e1\u05e4\u05e8_\u05dc\u05d9\u05d3\u05d4_\u05d0\u05d6\u05e8\u05d7\u05d9": "birth_day_reduced",
    "\u05ea\u05e7\u05d5\u05e4\u05ea_\u05d4\u05de\u05d7\u05d6\u05d5\u05e8_\u05d4\u05e8\u05d0\u05e9\u05d5\u05df": "birth_day_reduced",
}

# Family 3: Name-structure executors
FAMILY_NAME_STRUCTURE = {
    "\u05e1\u05db\u05d5\u05dd_\u05d4\u05ea\u05e0\u05d5\u05e2\u05d5\u05ea_\u05d1\u05e9\u05dd": "name_soul_expression",
    "\u05e1\u05db\u05d5\u05dd_\u05d4\u05e2\u05d9\u05e6\u05d5\u05e8\u05d9\u05dd_\u05d1\u05e9\u05dd": "name_outer_behavior",
    "\u05d1\u05d3\u05d9\u05e7\u05ea_\u05e2\u05d5\u05d3\u05e3_\u05e1\u05e4\u05e8\u05d5\u05ea": "name_digit_profile",
    "\u05d1\u05d3\u05d9\u05e7\u05ea_\u05e7\u05d9\u05d5\u05dd_\u05e1\u05e4\u05e8\u05d5\u05ea_\u05d1\u05e9\u05dd_\u05d4\u05de\u05dc\u05d0": "name_digit_profile",
    "letter_repetition": "letter_repetition_count",
}

# Family 4: 9-year cycle position
FAMILY_CYCLE_POSITION = {
    "calculate_life_cycle_position": "life_cycle_position_9_year",
    "source_chapter_19": "life_cycle_position_9_year",
    "periodic_influences": "annual_influence_from_life_path_age",
    "source_chapter_14": "annual_influence_from_life_path_age",
}

PROMOTION_FAMILIES: dict[str, dict[str, str]] = {
    "civil_birthdate_reduction_aliases": FAMILY_CIVIL_REDUCTION,
    "civil_date_component_extractors": FAMILY_DATE_COMPONENTS,
    "name_structure_analysis": FAMILY_NAME_STRUCTURE,
    "nine_year_cycle_position": FAMILY_CYCLE_POSITION,
}

FALLBACK_INTERPRETATION_METHODS = {
    "annual_influence_from_life_path_age",
    "life_cycle_position_9_year",
    "month_of_birth",
    "birth_day_reduced",
}

FINAL_STATES = {
    "computable_with_trace",
    "computable_partial",
    "interpretation_only",
    "blocked_with_reason",
}


def _load_definition() -> dict[str, Any]:
    return json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))


def _save_definition(definition: dict[str, Any]) -> None:
    DEFINITION_PATH.write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")


def _idx(calcs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(calc.get("calc_key")): calc for calc in calcs}


def _is_meaningful_table(table: Any) -> bool:
    if not isinstance(table, dict) or not table:
        return False
    numeric_like = [str(key).strip() for key in table.keys() if str(key).strip().lstrip("-").isdigit()]
    return bool(numeric_like)


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


def _general_number_table(calcs: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    index = _idx(calcs)
    for key in ("personality_number", "birth_number", "destiny_path"):
        calc = index.get(key)
        if not calc:
            continue
        table = calc.get("interpretations_by_value") or {}
        if _is_meaningful_table(table):
            return key, table
    return None


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


def _computed_with_interpretation(report: dict[str, Any]) -> int:
    count = 0
    for item in report.get("calculations", []):
        if str(item.get("status")) != "computed":
            continue
        if str(item.get("interpretation") or "").strip():
            count += 1
    return count


def _unsupported_count_from_definition(definition: dict[str, Any]) -> int:
    count = 0
    for calc in definition.get("calculations", []):
        if str(calc.get("final_state") or "") != "blocked_with_reason":
            continue
        reason = str(calc.get("final_reason_bucket") or calc.get("blocked_reason") or "")
        if reason == "unsupported_executor_type":
            count += 1
    return count


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    before_definition = _load_definition()
    before_runtime = run_subject_map(dict(SAMPLE_PAYLOAD))
    before_computable_with_trace = int(before_runtime.get("summary", {}).get("computed_with_full_trace", 0))
    before_computed_with_interpretation = _computed_with_interpretation(before_runtime)

    before_unsupported = _unsupported_count_from_definition(before_definition)
    if before_unsupported == 0:
        # Fallback for definitions created before final_state standardization.
        before_unsupported = sum(
            1
            for calc in before_definition.get("calculations", [])
            if str(calc.get("blocked_reason") or "") == "unsupported_executor_type"
        )

    after_definition = copy.deepcopy(before_definition)
    after_definition["definition_version"] = "1.2.0"
    after_definition["executor_wave"] = {
        "wave_id": "sefer_executor_wave_2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    calcs = after_definition.get("calculations", [])
    index = _idx(calcs)

    promoted: list[str] = []
    promoted_by_family: dict[str, list[str]] = {}
    for family_name, mapping in PROMOTION_FAMILIES.items():
        promoted_by_family[family_name] = []
        for calc_key, method in mapping.items():
            calc = index.get(calc_key)
            if not calc:
                continue
            was_computable = str(calc.get("status") or "") == "computable"
            calc["status"] = "computable"
            calc["blocked_reason"] = None
            calc["execution"] = {"method": method}
            review = calc.get("needs_review")
            if not isinstance(review, dict):
                review = {}
            review["executor_wave_2"] = "promoted"
            review["executor_family"] = family_name
            calc["needs_review"] = review
            if not was_computable:
                promoted.append(calc_key)
                promoted_by_family[family_name].append(calc_key)

    canonical = _canonical_tables(calcs)
    general_table = _general_number_table(calcs)
    interpretation_tables_added: list[str] = []

    for calc_key in promoted:
        calc = index.get(calc_key)
        if not calc:
            continue
        table = calc.get("interpretations_by_value") or {}
        if isinstance(table, dict) and table:
            continue

        method = str((calc.get("execution") or {}).get("method") or "").strip()
        method_source = canonical.get(method)
        if method_source:
            source_key, source_table = method_source
            calc["interpretations_by_value"] = copy.deepcopy(source_table)
            calc["interpretation_table_source_calc_key"] = source_key
            interpretation_tables_added.append(calc_key)
            continue

        if method in FALLBACK_INTERPRETATION_METHODS and general_table:
            source_key, source_table = general_table
            calc["interpretations_by_value"] = copy.deepcopy(source_table)
            calc["interpretation_table_source_calc_key"] = source_key
            calc["interpretation_table_note"] = "general_number_meaning_fallback"
            interpretation_tables_added.append(calc_key)

    for calc in calcs:
        _finalize_state(calc)
        if str(calc.get("final_state") or "") not in FINAL_STATES:
            calc["final_state"] = "blocked_with_reason"
            calc["final_reason_bucket"] = str(calc.get("blocked_reason") or "unsupported_executor_type")

    _save_definition(after_definition)

    after_runtime = run_subject_map(dict(SAMPLE_PAYLOAD))
    after_computable_with_trace = int(after_runtime.get("summary", {}).get("computed_with_full_trace", 0))
    after_computed_with_interpretation = _computed_with_interpretation(after_runtime)
    after_unsupported = _unsupported_count_from_definition(after_definition)

    promoted_runtime_computed: list[str] = []
    runtime_by_key = {str(item.get("calc_key")): item for item in after_runtime.get("calculations", [])}
    for calc_key in promoted:
        row = runtime_by_key.get(calc_key) or {}
        if str(row.get("status")) == "computed":
            promoted_runtime_computed.append(calc_key)

    blocked_counts = Counter(
        str(calc.get("final_reason_bucket") or calc.get("blocked_reason") or "unclassified")
        for calc in calcs
        if str(calc.get("final_state")) == "blocked_with_reason"
    )

    green_legacy_ok = False
    try:
        legacy = get_calculator(DEFAULT_CALCULATOR_ID)
        result = legacy.calculate(
            {
                "day": "17",
                "month": "05",
                "year": "1990",
                "first_name": "\u05d3\u05e0\u05d9",
                "last_name": "\u05db\u05d4\u05df",
                "gender": "male",
            }
        )
        green_legacy_ok = bool(result.get("results"))
    except Exception:
        green_legacy_ok = False

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "book_id": after_definition.get("book_id"),
        "definition_version_before": before_definition.get("definition_version"),
        "definition_version_after": after_definition.get("definition_version"),
        "sample_payload": SAMPLE_PAYLOAD,
        "metrics_before": {
            "computable_with_trace": before_computable_with_trace,
            "unsupported_executor_type": before_unsupported,
            "computed_with_interpretation": before_computed_with_interpretation,
        },
        "metrics_after": {
            "computable_with_trace": after_computable_with_trace,
            "unsupported_executor_type": after_unsupported,
            "computed_with_interpretation": after_computed_with_interpretation,
        },
        "executor_families_implemented": list(PROMOTION_FAMILIES.keys()),
        "promoted_calculations": sorted(promoted),
        "promoted_calculations_computed_in_sample": sorted(promoted_runtime_computed),
        "interpretation_tables_added_count": len(interpretation_tables_added),
        "interpretation_tables_added_calculations": sorted(interpretation_tables_added),
        "blocked_counts_by_reason_after": dict(sorted(blocked_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "green_legacy_still_works": green_legacy_ok,
        "no_production_switch": True,
        "no_second_book_added": True,
        "no_ocr_work_started": True,
        "no_broad_ui_redesign": True,
    }

    JSON_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Sefer Executor Wave 2",
        "",
        f"Generated: {report['generated_at']}",
        f"Definition version: {report['definition_version_before']} -> {report['definition_version_after']}",
        "",
        "## Metrics",
        f"- computable_with_trace: {before_computable_with_trace} -> {after_computable_with_trace}",
        f"- unsupported_executor_type: {before_unsupported} -> {after_unsupported}",
        f"- computed_with_interpretation: {before_computed_with_interpretation} -> {after_computed_with_interpretation}",
        "",
        "## Families Implemented",
    ]
    for family in report["executor_families_implemented"]:
        lines.append(f"- `{family}` ({len(promoted_by_family.get(family, []))} promoted)")

    lines.extend(["", "## High-Value Newly Promoted"])
    for calc_key in sorted(promoted_runtime_computed):
        lines.append(f"- `{calc_key}`")

    lines.extend(["", "## Blocked Counts By Reason (After)"])
    for reason, count in sorted(blocked_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- `{reason}`: {count}")

    lines.extend(
        [
            "",
            "## Guards",
            f"- green_legacy_still_works: `{green_legacy_ok}`",
            "- production switch: `false`",
            "- second book added: `false`",
            "- OCR work started: `false`",
            "- broad UI redesign: `false`",
        ]
    )

    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
