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
JSON_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.executor_wave_4.json"
MD_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.executor_wave_4.md"

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
}

BASELINE_METRICS = {
    "computable_with_trace": 152,
    "unsupported_executor_type": 97,
    "computed_with_interpretation": 98,
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


def _computed_with_interpretation(report: dict[str, Any]) -> int:
    return sum(
        1
        for item in report.get("calculations", [])
        if str(item.get("status")) == "computed" and str(item.get("interpretation") or "").strip()
    )


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
    current_reason = str(calc.get("blocked_reason") or calc.get("final_reason_bucket") or "")
    if current_reason != "unsupported_executor_type":
        return
    calc["status"] = "computable"
    calc["blocked_reason"] = None
    calc["execution"] = execution
    review = calc.get("needs_review")
    if not isinstance(review, dict):
        review = {}
    review["executor_wave_4"] = "promoted"
    review["executor_family"] = family
    calc["needs_review"] = review
    promoted.append(calc_key)


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    before_definition = _load_definition()
    before_runtime = run_subject_map(dict(SAMPLE_PAYLOAD))
    before_computable_with_trace = int(BASELINE_METRICS["computable_with_trace"])
    before_unsupported = int(BASELINE_METRICS["unsupported_executor_type"])
    before_computed_with_interpretation = int(BASELINE_METRICS["computed_with_interpretation"])

    after_definition = copy.deepcopy(before_definition)
    after_definition["definition_version"] = "1.4.0"
    after_definition["executor_wave"] = {
        "wave_id": "sefer_executor_wave_4",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    calcs = after_definition.get("calculations", [])
    index = {str(calc.get("calc_key")): calc for calc in calcs}
    promoted: list[str] = []
    promoted_by_family: dict[str, list[str]] = defaultdict(list)

    family_definitions: dict[str, dict[str, dict[str, Any]]] = {
        "numeric_identifier_digit_reduction": {
            "apartment_number_meaning": {"method": "digit_sum_reduce_input", "input_key": "apartment_number", "input_aliases": ["מספר הדירה"]},
            "house_number_meaning": {"method": "digit_sum_reduce_input", "input_key": "house_number", "input_aliases": ["מספר הבית"]},
            "id_number_meaning": {"method": "digit_sum_reduce_input", "input_key": "id_number", "input_aliases": ["מספר תעודת זהות"]},
            "passport_number_meaning": {"method": "digit_sum_reduce_input", "input_key": "passport_number", "input_aliases": ["מספר דרכון"]},
            "taxi_number_meaning": {"method": "digit_sum_reduce_input", "input_key": "taxi_number", "input_aliases": ["מספר המונית"]},
            "transit_pass_number_meaning": {"method": "digit_sum_reduce_input", "input_key": "transit_pass_number", "input_aliases": ["מספר כרטיס נסיעה"]},
            "credit_card_number_meaning": {"method": "digit_sum_reduce_input", "input_key": "credit_card_number", "input_aliases": ["מספר כרטיס אשראי"]},
            "car_number_meaning": {"method": "digit_sum_reduce_input", "input_key": "car_number", "input_aliases": ["מספר רישוי רכב"]},
            "birthdate_meaning": {"method": "digit_sum_reduce_input", "input_key": "workplace_birth_date", "input_aliases": ["תאריך הלידה של מקום העבודה"]},
            "single_digit_reduction": {"method": "digit_sum_reduce_input", "input_key": "multi_digit_number", "input_aliases": ["מספר רב ספרתי"]},
            "source_chapter_13": {
                "method": "digit_sum_reduce_input",
                "input_key": "apartment_number",
                "input_aliases": ["מספר הדירה"],
                "return_value_constant": "source",
            },
            "source_chapter_9": {
                "method": "digit_sum_reduce_input",
                "input_key": "hebrew_birth_date",
                "input_aliases": ["תאריך לידה עברי"],
                "return_value_constant": "source",
            },
        },
        "textual_name_reduction": {
            "city_name_meaning": {"method": "letter_sum_reduce_input", "input_key": "city_name", "input_aliases": ["שם הישוב"]},
            "street_number_meaning": {"method": "letter_sum_reduce_input", "input_key": "street_name", "input_aliases": ["שם הרחוב"]},
            "workplace_name_meaning": {"method": "letter_sum_reduce_input", "input_key": "workplace_name", "input_aliases": ["שם מקום העבודה"]},
            "hibush_shem_mispar_lidah": {"method": "letter_sum_reduce_input", "input_key": "nickname", "input_aliases": ["שם חיבה"]},
            "source_chapter_12": {
                "method": "letter_sum_reduce_input",
                "input_key": "nickname",
                "input_aliases": ["שם חיבה"],
                "return_value_constant": "source",
            },
        },
        "name_change_profile": {
            "added_name_impact": {
                "method": "name_change_delta_reduced",
                "original_input_key": "existing_name",
                "original_input_aliases": ["שם קיים"],
                "new_input_key": "new_name",
                "new_input_aliases": ["שם חדש"],
                "value_mode": "combined_final",
            },
            "name_change_impact": {
                "method": "name_change_delta_reduced",
                "original_input_key": "name_before_change",
                "original_input_aliases": ["שם לפני שינוי"],
                "new_input_key": "name_after_change",
                "new_input_aliases": ["שם אחרי שינוי"],
                "value_mode": "combined_final",
            },
            "marriage_name_change_impact": {
                "method": "name_change_delta_reduced",
                "original_input_key": "family_name_before_marriage",
                "original_input_aliases": ["שם משפחה לפני נישואין"],
                "new_input_key": "family_name_after_marriage",
                "new_input_aliases": ["שם משפחה אחרי נישואין"],
                "value_mode": "combined_final",
            },
            "name_transliteration_impact": {
                "method": "name_change_delta_reduced",
                "original_input_key": "name_original_language",
                "original_input_aliases": ["שם בשפה מקורית"],
                "new_input_key": "name_transliterated",
                "new_input_aliases": ["שם בשפה אחרת"],
                "value_mode": "combined_final",
            },
            "source_chapter_11": {
                "method": "name_change_delta_reduced",
                "original_input_key": "existing_name",
                "original_input_aliases": ["שם קיים"],
                "new_input_key": "new_name",
                "new_input_aliases": ["שם חדש"],
                "value_mode": "source",
            },
        },
        "period_division_and_linear_timing": {
            "quarterly_division": {"method": "divide_input", "input_key": "period_value", "input_aliases": ["תקופה"], "divisor": 4},
            "action_point_calculation": {"method": "divide_input", "input_key": "period_value", "input_aliases": ["תקופה"], "divisor": 4},
            "maturity_focus_date": {"method": "divide_input", "input_key": "period_value", "input_aliases": ["תקופה"], "divisor": 2},
            "bi_monthly_division": {"method": "divide_input", "input_key": "year_value", "input_aliases": ["שנה"], "divisor": 6},
            "day_division": {
                "method": "base_plus_factor_times_input",
                "base_input_key": "birth_hour",
                "base_input_aliases": ["שעת לידה"],
                "index_input_key": "birth_quarter_index",
                "index_input_aliases": ["מספר רבע (1-4)"],
                "factor": 6,
            },
            "hourly_division": {
                "method": "base_plus_factor_times_input",
                "base_input_key": "birth_minute",
                "base_input_aliases": ["דקת לידה"],
                "index_input_key": "minute_quarter_index",
                "index_input_aliases": ["מספר רבע (1-4)"],
                "factor": 15,
            },
        },
        "combined_sum_calculations": {
            "pisga_ishit_ezrahi": {
                "method": "sum_inputs_reduce",
                "input_keys": ["destiny_path_value", "civil_life_path"],
                "input_aliases": ["שביל גורל", "שיעור חיים אזרחי"],
                "apply_reduction": True,
                "keep_masters": False,
                "min_inputs": 2,
            },
            "pisga_ishit_meshutaf": {
                "method": "sum_inputs_reduce",
                "input_keys": ["hebrew_personal_peak", "civil_personal_peak"],
                "input_aliases": ["פסגה אישית עברי", "פסגה אישית אזרחי"],
                "apply_reduction": True,
                "keep_masters": False,
                "min_inputs": 2,
            },
            "shiyur_haim_meshutaf": {
                "method": "sum_inputs_reduce",
                "input_keys": ["hebrew_life_path", "civil_life_path"],
                "input_aliases": ["שיעור חיים עברי", "שיעור חיים אזרחי"],
                "apply_reduction": True,
                "keep_masters": True,
                "min_inputs": 2,
            },
            "shared_life_path_number": {
                "method": "sum_inputs_reduce",
                "input_keys": ["partner_life_path", "second_partner_life_path"],
                "input_aliases": ["שיעור חיים של בן זוג 1", "שיעור חיים של בן זוג 2"],
                "apply_reduction": True,
                "keep_masters": True,
                "min_inputs": 2,
            },
            "master_number_reduction": {
                "method": "sum_inputs_reduce",
                "input_keys": ["master_number_value"],
                "input_aliases": ["מספר מאסטר"],
                "apply_reduction": True,
                "keep_masters": False,
                "min_inputs": 1,
            },
            "master_number_handling": {
                "method": "sum_inputs_reduce",
                "input_keys": ["master_number_value"],
                "input_aliases": ["מספר מאסטר"],
                "apply_reduction": True,
                "keep_masters": False,
                "min_inputs": 1,
            },
            "חיבור_ימי_הולדת": {
                "method": "sum_inputs_reduce",
                "input_keys": ["hebrew_birth_day", "civil_birth_day"],
                "input_aliases": ["יום לידה עברי", "יום לידה אזרחי"],
                "apply_reduction": True,
                "keep_masters": False,
                "min_inputs": 2,
            },
            "חיבור_חודשי_לידה": {
                "method": "sum_inputs_reduce",
                "input_keys": ["hebrew_birth_month", "civil_birth_month"],
                "input_aliases": ["חודש לידה עברי", "חודש לידה אזרחי"],
                "apply_reduction": True,
                "keep_masters": False,
                "min_inputs": 2,
            },
            "חיבור_שנות_לידה": {
                "method": "sum_inputs_reduce",
                "input_keys": ["hebrew_birth_year", "civil_birth_year"],
                "input_aliases": ["שנת לידה עברית", "שנת לידה אזרחית"],
                "apply_reduction": True,
                "keep_masters": False,
                "min_inputs": 2,
            },
            "שביל_הגורל": {
                "method": "digit_sums_of_inputs_reduce",
                "input_keys": ["hebrew_birth_date", "birth_date"],
                "input_aliases": ["תאריך לידה עברי", "תאריך לידה אזרחי"],
                "keep_masters": True,
                "min_inputs": 2,
            },
            "שיעור_החיים_המשותף": {
                "method": "digit_sums_of_inputs_reduce",
                "input_keys": ["hebrew_birth_date", "birth_date"],
                "input_aliases": ["תאריך לידה עברי", "תאריך לידה אזרחי"],
                "keep_masters": True,
                "min_inputs": 2,
            },
            "source_chapter_3": {
                "method": "digit_sums_of_inputs_reduce",
                "input_keys": ["hebrew_birth_date", "birth_date"],
                "input_aliases": ["תאריך לידה עברי", "תאריך לידה אזרחי"],
                "keep_masters": True,
                "min_inputs": 2,
                "return_value_constant": "source",
            },
        },
        "input_extraction_and_classification": {
            "חישוב_ערך_מספרי_של_אות": {"method": "letter_numeric_value"},
            "סיווג_אותיות_ליחידות_עשרות_ומאות": {"method": "classify_name_letter_ranges", "input_key": "full_name", "input_aliases": ["אותיות השם"]},
            "שנת_לידה_אזרחית": {"method": "input_as_integer", "input_keys": ["civil_birth_year", "year"], "input_aliases": ["שנת לידה אזרחית"]},
            "month_number_calculation": {
                "method": "hebrew_month_name_to_number",
                "input_keys": ["hebrew_birth_month_name"],
                "input_aliases": ["שם חודש עברי", "חודש לידה עברי"],
            },
            "missing_numbers": {
                "method": "missing_numbers_profile",
                "name_input_keys": ["birth_name_full", "full_name"],
                "name_input_aliases": ["שם לידה מלא", "שם מלא"],
                "date_input_keys": ["birth_date"],
                "date_input_aliases": ["תאריך לידה"],
            },
        },
    }

    for family, mapping in family_definitions.items():
        for calc_key, execution in mapping.items():
            before = len(promoted)
            _promote(index=index, calc_key=calc_key, family=family, execution=execution, promoted=promoted)
            if len(promoted) > before:
                promoted_by_family[family].append(calc_key)

    if not promoted:
        for calc in calcs:
            review = calc.get("needs_review") or {}
            if not isinstance(review, dict):
                continue
            if review.get("executor_wave_4") != "promoted":
                continue
            calc_key = str(calc.get("calc_key") or "")
            if not calc_key:
                continue
            family = str(review.get("executor_family") or "wave_4_existing")
            promoted.append(calc_key)
            promoted_by_family[family].append(calc_key)

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
        "executor_families_implemented": [family for family, keys in promoted_by_family.items() if keys],
        "promoted_calculations": sorted(promoted),
        "promoted_calculations_computed_in_sample": promoted_runtime_computed,
        "blocked_counts_by_reason_after": dict(sorted(blocked_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "green_legacy_still_works": green_legacy_ok,
        "no_production_switch": True,
        "no_second_book_added": True,
        "no_ocr_work_started": True,
        "no_broad_ui_redesign": True,
    }

    JSON_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Sefer Executor Wave 4",
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
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
