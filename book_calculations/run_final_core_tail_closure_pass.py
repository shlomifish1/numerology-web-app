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
JSON_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.final_core_tail_closure.json"
MD_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.final_core_tail_closure.md"

BASELINE_METRICS = {
    "computable_with_trace": 197,
    "unsupported_executor_type": 52,
    "computed_with_interpretation": 103,
}

SAMPLE_PAYLOAD = {
    "full_name": "דני כהן",
    "first_name": "דני",
    "last_name": "כהן",
    "birth_date": "1990-05-17",
    "current_year": 2029,
    "letter": "א",
    "apartment_number": "245",
    "house_number": "18",
    "id_number": "123456782",
    "passport_number": "A1234567",
    "taxi_number": "7843",
    "transit_pass_number": "554433",
    "credit_card_number": "4580458045801234",
    "car_number": "93-456-78",
    "workplace_birth_date": "2004-09-26",
    "multi_digit_number": "987654",
    "city_name": "תל אביב",
    "street_name": "הרצל",
    "workplace_name": "מגדל שלום",
    "nickname": "דניו",
    "existing_name": "דני כהן",
    "new_name": "דן כהן",
    "name_before_change": "דני כהן",
    "name_after_change": "דן כהן",
    "family_name_before_marriage": "לוי",
    "family_name_after_marriage": "כהן",
    "name_original_language": "דני",
    "name_transliterated": "Dani",
    "period_value": 36,
    "year_value": 2026,
    "birth_hour": 14,
    "birth_quarter_index": 3,
    "birth_minute": 20,
    "minute_quarter_index": 2,
    "civil_life_path": 5,
    "destiny_path_value": 8,
    "hebrew_personal_peak": 7,
    "civil_personal_peak": 4,
    "hebrew_life_path": 6,
    "partner_life_path": 3,
    "second_partner_life_path": 5,
    "master_number_value": 22,
    "hebrew_birth_day": 10,
    "civil_birth_day": 17,
    "hebrew_birth_month": 2,
    "civil_birth_month": 5,
    "hebrew_birth_year": 5750,
    "civil_birth_year": 1990,
    "hebrew_birth_date": "10-02-5750",
    "hebrew_birth_month_name": "תשרי",
    "birth_name_full": "דניאל כהן",
    "universal_year": 9,
    "personal_year": 5,
    "life_path": 6,
    "year_type": "מעוברת",
    "caregiver_role": "אם",
    "child_age": 6,
    "child_name": "נועם",
    "mother_name": "שרה",
    "father_name": "דוד",
}

FINAL_STATES = {
    "computable_with_trace",
    "computable_partial",
    "interpretation_only",
    "blocked_missing_formula",
    "blocked_missing_input_mapping",
    "blocked_unsupported_executor_type",
    "blocked_ambiguous_source",
    "blocked_other",
}


def _load_definition() -> dict[str, Any]:
    return json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))


def _save_definition(definition: dict[str, Any]) -> None:
    DEFINITION_PATH.write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")


def _computed_with_interpretation(report: dict[str, Any]) -> int:
    return sum(
        1
        for item in report.get("calculations", [])
        if str(item.get("status")) == "computed" and str(item.get("interpretation") or "").strip()
    )


def _unsupported_count(definition: dict[str, Any]) -> int:
    count = 0
    for calc in definition.get("calculations", []):
        reason = str(calc.get("final_reason_bucket") or calc.get("blocked_reason") or "")
        if reason == "unsupported_executor_type":
            count += 1
    return count


def _is_ambiguous_formula(formula_text: str) -> bool:
    text = str(formula_text or "")
    markers = [
        "לא ידוע",
        "לא מפורט",
        "לא מוגדר",
        "לא צויין",
        "אין נוסחה אחידה",
        "מפורט בטקסט",
        "המצאה",
        "דורש",
        "תלויה",
    ]
    return any(marker in text for marker in markers)


def _promote(
    *,
    index: dict[str, dict[str, Any]],
    calc_key: str,
    family: str,
    execution: dict[str, Any],
    promoted: list[str],
) -> None:
    calc = index.get(calc_key)
    if not calc:
        return
    reason = str(calc.get("final_reason_bucket") or calc.get("blocked_reason") or "")
    if reason != "unsupported_executor_type":
        return
    calc["status"] = "computable"
    calc["blocked_reason"] = ""
    calc["execution"] = execution
    review = calc.get("needs_review")
    if not isinstance(review, dict):
        review = {}
    review["final_core_tail_closure"] = "promoted"
    review["closure_family"] = family
    calc["needs_review"] = review
    promoted.append(calc_key)


def _reclassify_interpretation_only(calc: dict[str, Any]) -> None:
    calc["status"] = "needs_review"
    calc["blocked_reason"] = "interpretation_only"
    review = calc.get("needs_review")
    if not isinstance(review, dict):
        review = {}
    review["final_core_tail_closure"] = "reclassified_interpretation_only"
    calc["needs_review"] = review


def _finalize_state(calc: dict[str, Any]) -> None:
    status = str(calc.get("status") or "").strip()
    blocked_reason = str(calc.get("blocked_reason") or calc.get("final_reason_bucket") or "").strip()
    formula_text = str(calc.get("formula_text") or "")

    if status == "computable":
        calc["final_state"] = "computable_with_trace"
        calc["final_reason_bucket"] = ""
        return

    if status == "computable_partial":
        calc["final_state"] = "computable_partial"
        calc["final_reason_bucket"] = ""
        return

    if blocked_reason == "interpretation_only":
        calc["final_state"] = "interpretation_only"
        calc["final_reason_bucket"] = "interpretation_only"
        return

    if blocked_reason in {"missing_input_mapping", "blocked_missing_input_mapping"}:
        calc["blocked_reason"] = "blocked_missing_input_mapping"
        calc["final_state"] = "blocked_missing_input_mapping"
        calc["final_reason_bucket"] = "missing_input_mapping"
        return

    if blocked_reason in {"missing_formula", "blocked_missing_formula"}:
        calc["blocked_reason"] = "blocked_missing_formula"
        calc["final_state"] = "blocked_missing_formula"
        calc["final_reason_bucket"] = "missing_formula"
        return

    if blocked_reason in {"unsupported_executor_type", "blocked_unsupported_executor_type"}:
        if _is_ambiguous_formula(formula_text):
            calc["blocked_reason"] = "blocked_ambiguous_source"
            calc["final_state"] = "blocked_ambiguous_source"
            calc["final_reason_bucket"] = "ambiguous_source"
        else:
            calc["blocked_reason"] = "blocked_unsupported_executor_type"
            calc["final_state"] = "blocked_unsupported_executor_type"
            calc["final_reason_bucket"] = "unsupported_executor_type"
        return

    if _is_ambiguous_formula(formula_text):
        calc["blocked_reason"] = "blocked_ambiguous_source"
        calc["final_state"] = "blocked_ambiguous_source"
        calc["final_reason_bucket"] = "ambiguous_source"
        return

    calc["blocked_reason"] = "blocked_other"
    calc["final_state"] = "blocked_other"
    calc["final_reason_bucket"] = "other"


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    before_definition = _load_definition()
    initial_unsupported_keys = {
        str(calc.get("calc_key"))
        for calc in before_definition.get("calculations", [])
        if str(calc.get("final_reason_bucket") or calc.get("blocked_reason") or "") == "unsupported_executor_type"
    }

    after_definition = copy.deepcopy(before_definition)
    after_definition["definition_version"] = "1.5.0"
    after_definition["closure_pass"] = {
        "pass_id": "sefer_final_core_tail_closure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    calcs = after_definition.get("calculations", [])
    index = {str(calc.get("calc_key")): calc for calc in calcs}

    promoted: list[str] = []
    promoted_by_family: dict[str, list[str]] = defaultdict(list)
    promotions = {
        "core_dual_date_logic": {
            "destiny_number_calculation": {
                "method": "digit_sums_of_inputs_reduce",
                "input_keys": ["hebrew_birth_date", "birth_date"],
                "input_aliases": ["תאריך לידה עברי", "תאריך לידה אזרחי"],
                "keep_masters": True,
                "min_inputs": 2,
            },
            "life_path_number_combined": {"method": "life_path_combined_dual_method"},
            "שיעור_החיים_העברי": {
                "method": "digit_sum_reduce_input",
                "input_key": "hebrew_birth_date",
                "input_aliases": ["תאריך לידה עברי"],
                "keep_masters": True,
            },
            "מספר_לידה_עברי": {
                "method": "digit_sum_reduce_input",
                "input_key": "hebrew_birth_date",
                "input_aliases": ["תאריך לידה עברי"],
                "keep_masters": True,
            },
            "שנת_לידה_עברית": {
                "method": "input_as_integer",
                "input_keys": ["hebrew_birth_year"],
                "input_aliases": ["שנת לידה עברית"],
            },
            "חודש_לידה_עברי": {
                "method": "hebrew_month_name_to_number",
                "input_keys": ["hebrew_birth_month_name"],
                "input_aliases": ["חודש לידה עברי", "שם חודש עברי"],
            },
        },
        "core_name_and_master_logic": {
            "hidden_master_number_in_name": {"method": "hidden_master_number_in_name", "input_key": "full_name"},
            "semi_annual_influence": {"method": "semi_annual_influence", "reduce_outputs": True},
            "leap_year_adjustment": {"method": "leap_year_adjustment"},
            "parents_role": {"method": "parent_role_gate"},
            "התאמה_להורים": {"method": "parent_child_name_overlap"},
            "זיהוי_אותיות_משותפות": {
                "method": "common_letters_between_names",
                "left_input_key": "first_name",
                "right_input_key": "last_name",
            },
        },
        "source_bridge_with_trace": {
            "source_chapter_22": {
                "method": "letter_value_span_from_name",
                "input_key": "first_name",
                "input_aliases": ["שם פרטי"],
                "return_value_constant": "source",
            },
            "source_chapter_15": {
                "method": "constant_signature",
                "constants": [44, 8],
                "return_value_constant": "source",
            },
            "source_d9447302fe2e": {
                "method": "constant_signature",
                "constants": [44, 8],
                "return_value_constant": "source",
            },
            "44_or_8_destiny_number": {
                "method": "constant_signature",
                "constants": [44, 8],
            },
            "הצבת_אותיות_בטבלת_גילאים": {
                "method": "letter_value_span_from_name",
                "input_key": "first_name",
                "input_aliases": ["שם פרטי"],
            },
        },
    }

    for family, mapping in promotions.items():
        for calc_key, execution in mapping.items():
            before = len(promoted)
            _promote(index=index, calc_key=calc_key, family=family, execution=execution, promoted=promoted)
            if len(promoted) > before:
                promoted_by_family[family].append(calc_key)

    interpretation_only_reclassified = [
        "source_84cb362f462e",
        "source_chapter_32",
    ]
    for calc_key in interpretation_only_reclassified:
        calc = index.get(calc_key)
        if not calc:
            continue
        reason = str(calc.get("final_reason_bucket") or calc.get("blocked_reason") or "")
        if reason != "unsupported_executor_type":
            continue
        _reclassify_interpretation_only(calc)

    for calc in calcs:
        _finalize_state(calc)
        if str(calc.get("final_state") or "") not in FINAL_STATES:
            calc["final_state"] = "blocked_other"
            calc["blocked_reason"] = "blocked_other"
            calc["final_reason_bucket"] = "other"

    _save_definition(after_definition)

    after_runtime = run_subject_map(dict(SAMPLE_PAYLOAD))
    after_computable = int(after_runtime.get("summary", {}).get("computed_with_full_trace", 0))
    after_with_interpretation = _computed_with_interpretation(after_runtime)
    after_unsupported = _unsupported_count(after_definition)

    runtime_by_key = {str(item.get("calc_key")): item for item in after_runtime.get("calculations", [])}
    promoted_runtime_computed = sorted(
        key for key in promoted if str((runtime_by_key.get(key) or {}).get("status")) == "computed"
    )

    final_state_counts = Counter(str(calc.get("final_state") or "") for calc in calcs)
    final_reason_counts = Counter(str(calc.get("final_reason_bucket") or "") for calc in calcs)

    reclassified_tail_count = 0
    for calc in calcs:
        calc_key = str(calc.get("calc_key") or "")
        if calc_key not in initial_unsupported_keys:
            continue
        if calc_key in promoted:
            continue
        if str(calc.get("final_state") or "") != "blocked_unsupported_executor_type":
            reclassified_tail_count += 1

    green_legacy_ok = False
    try:
        legacy = get_calculator(DEFAULT_CALCULATOR_ID)
        result = legacy.calculate(
            {
                "day": "17",
                "month": "05",
                "year": "1990",
                "first_name": "דני",
                "last_name": "כהן",
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
        "metrics_before": dict(BASELINE_METRICS),
        "metrics_after": {
            "computable_with_trace": after_computable,
            "unsupported_executor_type": after_unsupported,
            "computed_with_interpretation": after_with_interpretation,
        },
        "executor_families_implemented": [family for family, keys in promoted_by_family.items() if keys],
        "promoted_calculations": sorted(promoted),
        "promoted_calculations_computed_in_sample": promoted_runtime_computed,
        "reclassified_tail_count": reclassified_tail_count,
        "final_state_counts": dict(sorted(final_state_counts.items())),
        "final_reason_counts": dict(sorted(final_reason_counts.items())),
        "green_legacy_still_works": green_legacy_ok,
        "no_production_switch": True,
        "no_second_book_added": True,
        "no_ocr_implementation_started": True,
        "no_broad_ui_redesign": True,
    }

    JSON_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Sefer Final Core-and-Tail Closure",
        "",
        f"Generated: {report['generated_at']}",
        f"Definition version: {report['definition_version_before']} -> {report['definition_version_after']}",
        "",
        "## Metrics",
        f"- computable_with_trace: {BASELINE_METRICS['computable_with_trace']} -> {after_computable}",
        f"- unsupported_executor_type: {BASELINE_METRICS['unsupported_executor_type']} -> {after_unsupported}",
        f"- computed_with_interpretation: {BASELINE_METRICS['computed_with_interpretation']} -> {after_with_interpretation}",
        "",
        "## Families Implemented",
    ]
    for family in report["executor_families_implemented"]:
        lines.append(f"- `{family}`")
    lines.extend(["", "## Newly Closed (Computed In Sample)"])
    for calc_key in promoted_runtime_computed:
        lines.append(f"- `{calc_key}`")
    lines.extend(["", "## Final State Counts"])
    for state, count in sorted(final_state_counts.items()):
        lines.append(f"- `{state}`: {count}")
    lines.extend(
        [
            "",
            "## Guards",
            f"- green_legacy_still_works: `{green_legacy_ok}`",
            "- production switch: `false`",
            "- second book added: `false`",
            "- OCR implementation started: `false`",
            "- broad UI redesign: `false`",
        ]
    )
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
