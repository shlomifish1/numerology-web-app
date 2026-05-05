from __future__ import annotations

import copy
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re
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
JSON_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.executor_wave_3.json"
MD_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.executor_wave_3.md"

SAMPLE_PAYLOAD = {
    "full_name": "\u05d3\u05e0\u05d9 \u05db\u05d4\u05df",
    "birth_date": "1990-05-17",
    "current_year": 2029,
    "letter": "\u05d0",
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


def _computed_with_interpretation(report: dict[str, Any]) -> int:
    count = 0
    for item in report.get("calculations", []):
        if str(item.get("status")) != "computed":
            continue
        if str(item.get("interpretation") or "").strip():
            count += 1
    return count


def _unsupported_count(definition: dict[str, Any]) -> int:
    count = 0
    for calc in definition.get("calculations", []):
        if str(calc.get("final_state") or "") != "blocked_with_reason":
            continue
        reason = str(calc.get("final_reason_bucket") or calc.get("blocked_reason") or "")
        if reason == "unsupported_executor_type":
            count += 1
    if count == 0:
        count = sum(
            1
            for calc in definition.get("calculations", [])
            if str(calc.get("blocked_reason") or "") == "unsupported_executor_type"
        )
    return count


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


def _calc_key_number(calc_key: str) -> int | None:
    matches = re.findall(r"\d+", str(calc_key or ""))
    if not matches:
        return None
    try:
        return int(matches[0])
    except Exception:
        return None


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    before_definition = _load_definition()
    before_runtime = run_subject_map(dict(SAMPLE_PAYLOAD))
    before_computable_with_trace = int(before_runtime.get("summary", {}).get("computed_with_full_trace", 0))
    before_unsupported = _unsupported_count(before_definition)
    before_computed_with_interpretation = _computed_with_interpretation(before_runtime)

    after_definition = copy.deepcopy(before_definition)
    after_definition["definition_version"] = "1.3.0"
    after_definition["executor_wave"] = {
        "wave_id": "sefer_executor_wave_3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    calcs = after_definition.get("calculations", [])
    index = _idx(calcs)

    # Wave 3 families chosen for deterministic, high-volume unlocks.
    temporary_family = sorted(
        key
        for key, calc in index.items()
        if str(calc.get("blocked_reason") or calc.get("final_reason_bucket") or "") == "unsupported_executor_type"
        and key.startswith("birth_number_meaning_")
    )
    career_family = sorted(
        key
        for key, calc in index.items()
        if str(calc.get("blocked_reason") or calc.get("final_reason_bucket") or "") == "unsupported_executor_type"
        and key.startswith("career_number_")
    )
    generic_number_family = sorted(
        key
        for key, calc in index.items()
        if str(calc.get("blocked_reason") or calc.get("final_reason_bucket") or "") == "unsupported_executor_type"
        and key.startswith("number_")
    )
    outward_family = sorted(
        key
        for key, calc in index.items()
        if str(calc.get("blocked_reason") or calc.get("final_reason_bucket") or "") == "unsupported_executor_type"
        and key.startswith("lifa_mispar_")
    )

    promoted_by_family = {
        "temporary_number_meanings": temporary_family + ["source_chapter_25"],
        "career_number_meanings": career_family + ["source_chapter_7"],
        "general_number_meanings": generic_number_family,
        "outward_behavior_number_meanings": outward_family,
    }

    promoted: list[str] = []
    for family_name, keys in promoted_by_family.items():
        for calc_key in keys:
            calc = index.get(calc_key)
            if not calc:
                continue
            current_reason = str(calc.get("blocked_reason") or calc.get("final_reason_bucket") or "")
            if current_reason != "unsupported_executor_type":
                continue

            if calc_key == "source_chapter_25":
                method = "annual_influence_from_life_path_age"
            elif calc_key == "source_chapter_7":
                method = "birth_date_digit_sum_reduced"
            else:
                method = "fixed_number_from_calc_key"

            calc["status"] = "computable"
            calc["blocked_reason"] = None
            calc["execution"] = {"method": method}
            review = calc.get("needs_review")
            if not isinstance(review, dict):
                review = {}
            review["executor_wave_3"] = "promoted"
            review["executor_family"] = family_name
            calc["needs_review"] = review
            promoted.append(calc_key)

    # Deterministic interpretation coverage improvements for promoted fixed-number entries.
    source_temp_table = (index.get("source_chapter_25") or {}).get("interpretations_by_value") or {}
    source_career_table = (index.get("source_chapter_7") or {}).get("interpretations_by_value") or {}
    source_generic_table = (index.get("personality_number") or {}).get("interpretations_by_value") or {}

    interpretation_tables_added: list[str] = []
    for calc_key in promoted:
        calc = index.get(calc_key)
        if not calc:
            continue
        existing_table = calc.get("interpretations_by_value") or {}
        if isinstance(existing_table, dict) and existing_table:
            continue

        target_table: dict[str, Any] = {}
        if calc_key.startswith("career_number_"):
            target_table = source_career_table
        elif calc_key.startswith("number_"):
            target_table = source_generic_table
        elif calc_key.startswith("birth_number_meaning_") or calc_key.startswith("lifa_mispar_"):
            target_table = source_temp_table

        if not isinstance(target_table, dict) or not target_table:
            continue

        number = _calc_key_number(calc_key)
        if number is None:
            continue
        number_key = str(number)
        if number_key not in target_table:
            continue

        calc["interpretations_by_value"] = copy.deepcopy(target_table)
        calc["interpretation_table_source_calc_key"] = (
            "source_chapter_7"
            if calc_key.startswith("career_number_")
            else ("personality_number" if calc_key.startswith("number_") else "source_chapter_25")
        )
        interpretation_tables_added.append(calc_key)

    for calc in calcs:
        _finalize_state(calc)
        if str(calc.get("final_state") or "") not in FINAL_STATES:
            calc["final_state"] = "blocked_with_reason"
            calc["final_reason_bucket"] = str(calc.get("blocked_reason") or "unsupported_executor_type")

    _save_definition(after_definition)

    after_runtime = run_subject_map(dict(SAMPLE_PAYLOAD))
    after_computable_with_trace = int(after_runtime.get("summary", {}).get("computed_with_full_trace", 0))
    after_unsupported = _unsupported_count(after_definition)
    after_computed_with_interpretation = _computed_with_interpretation(after_runtime)

    runtime_by_key = {str(item.get("calc_key")): item for item in after_runtime.get("calculations", [])}
    promoted_runtime_computed = sorted(
        key for key in promoted if str((runtime_by_key.get(key) or {}).get("status")) == "computed"
    )

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
        "executor_families_implemented": list(promoted_by_family.keys()),
        "promoted_calculations": sorted(promoted),
        "promoted_calculations_computed_in_sample": promoted_runtime_computed,
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
        "# Sefer Executor Wave 3",
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
        lines.append(f"- `{family}`")

    lines.extend(["", "## Newly Promoted (Computed In Sample)"])
    for calc_key in promoted_runtime_computed:
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
    # Keep stdout portable on Windows terminals that are not UTF-8.
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
