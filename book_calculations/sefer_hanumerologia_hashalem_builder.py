from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BOOK_ID = "sefer_hanumerologia_hashalem"
BOOK_TITLE = "??? ??????????? ????"
DEFINITION_VERSION = "1.0.0"

ROOT = Path(__file__).resolve().parent.parent
INTERPRETATIONS_ROOT = ROOT / "interpretations"
CATALOG_PATH = ROOT / "book_lab_catalog.json"
FINAL_SCHEMA_PATH = next(INTERPRETATIONS_ROOT.rglob("*__final_schema.json"))
OUTPUT_PATH = Path(__file__).resolve().parent / "sefer_hanumerologia_hashalem.definition.json"

UNKNOWN_FORMULA_MARKERS = {
    "",
    "none",
    "n/a",
    "na",
    "unknown",
    "not specified",
}


@dataclass
class SourceCalc:
    calc_key: str
    label_he: str
    short_explanation: str
    input_dependencies: list[str]
    formula_text: str
    formula_steps: list[str]
    allowed_result_values: list[Any]
    interpretations_by_value: dict[str, dict[str, Any]]
    source_refs: list[str]
    confidence: float | None
    enabled_in_full_map: bool | None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_str_list(value: Any) -> list[str]:
    return [_clean_text(item) for item in _normalize_list(value) if _clean_text(item)]


def _parse_output_values(raw_outputs: Any) -> list[Any]:
    outputs = _normalize_list(raw_outputs)
    parsed: list[Any] = []
    for item in outputs:
        if isinstance(item, int):
            parsed.append(item)
            continue
        text = _clean_text(item)
        if text.isdigit():
            parsed.append(int(text))
            continue
        parsed.append(text)
    dedup: list[Any] = []
    seen: set[str] = set()
    for item in parsed:
        marker = json.dumps(item, ensure_ascii=False)
        if marker in seen:
            continue
        seen.add(marker)
        dedup.append(item)
    return dedup


def _collect_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _normalize_str_list(value):
            if item not in seen:
                seen.add(item)
                refs.append(item)
    return refs


def _build_catalog_index(catalog_data: dict[str, Any]) -> dict[str, SourceCalc]:
    index: dict[str, SourceCalc] = {}
    for calc in catalog_data.get("calculations", []):
        key = _clean_text(calc.get("calc_key"))
        if not key:
            continue
        interpretations: dict[str, dict[str, Any]] = {}
        for item in _normalize_list(calc.get("result_values")):
            value_key = _clean_text(item.get("value"))
            if not value_key:
                continue
            interpretations[value_key] = {
                "title": _clean_text(item.get("title")),
                "meaning": _clean_text(item.get("meaning")),
                "source_ref": _clean_text(item.get("source_ref")),
                "needs_review": bool(item.get("needs_review", False)),
            }
        index[key] = SourceCalc(
            calc_key=key,
            label_he=_clean_text(calc.get("label_he")),
            short_explanation=_clean_text(calc.get("short_explanation")),
            input_dependencies=_normalize_str_list(calc.get("input_dependencies")),
            formula_text=_clean_text(calc.get("formula_text")),
            formula_steps=_normalize_str_list(calc.get("formula_steps")),
            allowed_result_values=_normalize_list(calc.get("allowed_result_values")),
            interpretations_by_value=interpretations,
            source_refs=_collect_refs(calc.get("source_refs"), calc.get("chapter_ref"), calc.get("book_name")),
            confidence=None,
            enabled_in_full_map=bool(calc.get("enabled_in_full_map")),
        )
    return index


def _build_final_index(final_schema_data: dict[str, Any]) -> dict[str, SourceCalc]:
    index: dict[str, SourceCalc] = {}
    for calc in final_schema_data.get("calculations", []):
        key = _clean_text(calc.get("calculation_key"))
        if not key:
            continue
        index[key] = SourceCalc(
            calc_key=key,
            label_he=_clean_text(calc.get("label")),
            short_explanation=_clean_text(calc.get("description")),
            input_dependencies=_normalize_str_list(calc.get("inputs")),
            formula_text=_clean_text(calc.get("formula")),
            formula_steps=[],
            allowed_result_values=_parse_output_values(calc.get("outputs")),
            interpretations_by_value={},
            source_refs=_collect_refs(calc.get("source_refs"), calc.get("when_used"), calc.get("scope"), calc.get("notes")),
            confidence=calc.get("confidence"),
            enabled_in_full_map=None,
        )
    return index


def _execution_for_calc(calc_key: str, formula_text: str) -> dict[str, Any] | None:
    key = calc_key.lower()
    text = formula_text.lower()

    direct_map = {
        "destiny_path": "name_destiny_path",
        "destiny_number": "name_destiny_path",
        "expression_of_the_soul": "name_soul_expression",
        "soul_expression": "name_soul_expression",
        "soul_expression_number": "name_soul_expression",
        "behavior_number": "name_outer_behavior",
        "outer_behavior": "name_outer_behavior",
        "outward_behavior": "name_outer_behavior",
        "outward_behavior_number": "name_outer_behavior",
        "source_chapter_1": "name_full_raw_sum",
        "source_chapter_4": "birth_date_component_sum_reduced",
        "source_chapter_8": "name_digit_profile",
        "source_chapter_16": "birth_month_minus_day_reduced",
        "source_chapter_18": "name_full_raw_sum",
        "source_chapter_20": "birth_date_digit_sum_reduced",
        "source_chapter_21": "birth_date_digit_sum_reduced",
        "source_chapter_24": "letter_numeric_value",
        "source_chapter_26": "name_full_raw_sum",
        "source_chapter_30": "name_full_raw_sum",
        "source_chapter_31": "name_full_raw_sum",
        "source_chapter_33": "name_full_raw_sum",
        "birth_number": "birth_date_digit_sum_reduced",
        "birth_period_1": "birth_month_minus_day_reduced",
        "birth_period_2": "birth_year_minus_day_reduced",
        "age_after_marriage": "age_from_current_year",
        "life_path_number": "birth_date_digit_sum_reduced",
        "life_path_number_civil": "birth_date_component_sum_reduced",
        "life_path_number_gregorian": "birth_date_digit_sum_reduced",
        "mispar_holeeda": "birth_date_component_sum_reduced",
        "shvil_goral": "soul_plus_behavior_reduced",
        "destiny_path_calculation": "soul_plus_behavior_reduced",
        "name_number": "name_full_raw_sum",
        "name_number_calculation": "name_full_raw_sum",
        "tablat_tadri_hasaparim": "name_digit_profile",
        "excess_numbers": "name_digit_profile",
        "misparim_haserim": "name_digit_profile",
        "misparim_mitivim": "name_digit_profile",
        "misparim_odfim": "name_digit_profile",
        "encoded_letter_value": "letter_numeric_value",
        "letter_to_number_conversion": "letter_numeric_value",
        "first_letter": "first_letter",
        "last_letter": "last_letter",
        "month_of_birth": "month_of_birth",
        "year_of_birth": "year_of_birth_last_two_digits",
        "birth_date_civil": "birth_date_civil",
        "birth_date_summation": "birth_date_digit_sum_reduced",
        "life_path_number_western": "birth_date_digit_sum_reduced",
        "shiyur_haim_ezrahi": "birth_date_digit_sum_reduced",
        "annual_influence": "annual_influence_from_life_path_age",
        "annual_influence_civil": "annual_influence_from_life_path_age",
        "annual_influence_value": "annual_influence_from_life_path_age",
        "yearly_influence_calculation": "annual_influence_from_life_path_age",
        "yearly_life_path_number": "annual_influence_from_life_path_age",
        "end_of_period_1_civil": "period_end_plus_28_from_life_path",
        "first_season_end_age": "season_end_36_minus_life_path",
        "source_chapter_5": "name_middle_letter",
        "balance_point": "name_middle_letter",
        "source_chapter_6": "first_name_raw_sum",
        "hitnahagut_muhcenet": "first_name_raw_sum",
        "shvil_goral_shem_prati_rishon": "first_name_raw_sum",
        "hitnahagut_muhcenet_shem_lida_male": "name_full_raw_sum",
        "shvil_goral_shem_lida_male": "name_full_raw_sum",
        "number_of_birth": "birth_day_reduced",
    }
    if calc_key in direct_map:
        return {"method": direct_map[calc_key]}

    if key.startswith("bitui_neshama"):
        return {"method": "name_soul_expression"}
    if key.startswith("birth_number") and "meaning" not in key:
        return {"method": "birth_date_digit_sum_reduced"}
    if key.startswith("birth_period") and key.endswith("_3"):
        return {"method": "birth_year_minus_day_reduced"}

    if " + " in formula_text and "day" in text and "month" in text and "year" in text:
        return {"method": "birth_date_component_sum_reduced"}
    if "digit" in text and "birth" in text:
        return {"method": "birth_date_digit_sum_reduced"}
    if "month" in text and "-" in text and "day" in text:
        return {"method": "birth_month_minus_day_reduced"}
    if "vowel" in text and "name" in text:
        return {"method": "name_soul_expression"}
    if "consonant" in text and "name" in text:
        return {"method": "name_outer_behavior"}

    return None


def _calc_status(formula_text: str, execution: dict[str, Any] | None) -> str:
    normalized = formula_text.strip().lower()
    has_formula = normalized not in UNKNOWN_FORMULA_MARKERS
    if execution:
        return "computable"
    if has_formula:
        return "needs_review"
    return "unsupported"


def _calc_needs_review(formula_text: str, execution: dict[str, Any] | None, interpretations_by_value: dict[str, Any]) -> dict[str, Any]:
    normalized = formula_text.strip().lower()
    has_formula = normalized not in UNKNOWN_FORMULA_MARKERS
    return {
        "formula": execution is None,
        "missing_formula": not has_formula,
        "unsupported_inputs": execution is None and has_formula,
        "interpretations_missing": len(interpretations_by_value) == 0,
    }


def _blocked_reason(
    calc_key: str,
    formula_text: str,
    status: str,
    execution: dict[str, Any] | None,
    input_dependencies: list[str],
    allowed_result_values: list[Any],
    interpretations_by_value: dict[str, Any],
    source_refs: list[str],
) -> str | None:
    if status == "computable" and execution:
        return None

    key = calc_key.lower()
    formula_norm = formula_text.strip().lower()
    deps_text = " ".join(input_dependencies).lower()

    if not formula_norm or formula_norm in UNKNOWN_FORMULA_MARKERS:
        return "missing_formula"

    interpretation_only_keys = {
        "dealing_with_conflicts",
        "letter_alef_meaning",
        "letter_ayin_meaning",
        "letter_final_meaning",
        "letter_kaf_meaning",
        "letter_lamed_meaning",
        "letter_peh_meaning",
        "letter_resh_meaning",
        "letter_samech_meaning",
        "letter_tav_meaning",
        "letter_yod_meaning",
    }
    if key in interpretation_only_keys or formula_norm.startswith("n/a"):
        return "interpretation_only"

    if "hebrew" in deps_text or "hour" in deps_text or "minute" in deps_text:
        return "missing_input_mapping"

    if "shem_hiba" in key or "nickname" in key or "new_name" in key:
        return "missing_input_mapping"

    if "ivri" in key or "hebrew" in key:
        return "missing_input_mapping"

    if "44" in formula_norm and "8" in formula_norm and "or" in formula_norm:
        return "conflicting_source_evidence"

    if "/" in formula_norm and ("period" in formula_norm or "division" in formula_norm):
        return "missing_reduction_rule"

    if not allowed_result_values and not interpretations_by_value:
        return "missing_result_value_table"

    if not source_refs:
        return "insufficient_source_precision"

    if execution is None:
        if "not defined" in formula_norm or "not known" in formula_norm or "depends" in formula_norm:
            return "ambiguous_formula"
        return "unsupported_executor_type"

    return "insufficient_source_precision"


def build_definition() -> dict[str, Any]:
    catalog_data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    final_schema_data = json.loads(FINAL_SCHEMA_PATH.read_text(encoding="utf-8"))

    catalog_index = _build_catalog_index(catalog_data)
    final_index = _build_final_index(final_schema_data)

    ordered_keys = list(catalog_index.keys()) + sorted(key for key in final_index.keys() if key not in catalog_index)

    calculations: list[dict[str, Any]] = []
    for key in ordered_keys:
        catalog_item = catalog_index.get(key)
        final_item = final_index.get(key)

        label_he = (catalog_item.label_he if catalog_item else "") or (final_item.label_he if final_item else "")
        short_explanation = (catalog_item.short_explanation if catalog_item else "") or (final_item.short_explanation if final_item else "")
        input_dependencies = (catalog_item.input_dependencies if catalog_item else []) or (final_item.input_dependencies if final_item else [])
        formula_text = (catalog_item.formula_text if catalog_item else "") or (final_item.formula_text if final_item else "")
        formula_steps = (catalog_item.formula_steps if catalog_item else []) or (final_item.formula_steps if final_item else [])
        allowed_result_values = (catalog_item.allowed_result_values if catalog_item else []) or (final_item.allowed_result_values if final_item else [])
        interpretations_by_value = (catalog_item.interpretations_by_value if catalog_item else {}) or (final_item.interpretations_by_value if final_item else {})

        source_refs = _collect_refs(
            catalog_item.source_refs if catalog_item else [],
            final_item.source_refs if final_item else [],
        )

        confidence = final_item.confidence if final_item else None
        execution = _execution_for_calc(key, formula_text)
        status = _calc_status(formula_text, execution)
        needs_review = _calc_needs_review(formula_text, execution, interpretations_by_value)

        calculations.append(
            {
                "calc_key": key,
                "label_he": label_he,
                "short_explanation": short_explanation,
                "input_dependencies": input_dependencies,
                "formula_text": formula_text,
                "formula_steps": formula_steps,
                "reduction_rules": {
                    "type": "single_digit_with_masters",
                    "masters": [11, 22, 33],
                    "applies": execution is not None,
                },
                "allowed_result_values": allowed_result_values,
                "interpretations_by_value": interpretations_by_value,
                "source_refs": source_refs,
                "enabled_in_full_map": (catalog_item.enabled_in_full_map if catalog_item else None),
                "status": status,
                "blocked_reason": _blocked_reason(
                    calc_key=key,
                    formula_text=formula_text,
                    status=status,
                    execution=execution,
                    input_dependencies=input_dependencies,
                    allowed_result_values=allowed_result_values,
                    interpretations_by_value=interpretations_by_value,
                    source_refs=source_refs,
                ),
                "needs_review": needs_review,
                "metadata": {
                    "confidence": confidence,
                    "completeness": {
                        "has_formula_text": bool(formula_text),
                        "has_formula_steps": bool(formula_steps),
                        "has_interpretations": bool(interpretations_by_value),
                        "has_source_refs": bool(source_refs),
                    },
                    "sources": {
                        "from_catalog": catalog_item is not None,
                        "from_final_schema": final_item is not None,
                    },
                },
                "execution": execution,
            }
        )

    computable_count = sum(1 for calc in calculations if calc.get("execution"))
    return {
        "schema_version": "book_calculation_definition.v1",
        "definition_version": DEFINITION_VERSION,
        "book_id": BOOK_ID,
        "book_title": BOOK_TITLE,
        "generated_from": {
            "book_lab_catalog": str(CATALOG_PATH),
            "book_final_schema": str(FINAL_SCHEMA_PATH),
        },
        "coverage": {
            "total_calculations": len(calculations),
            "computable_calculations": computable_count,
            "non_computable_calculations": len(calculations) - computable_count,
        },
        "calculations": calculations,
    }


def write_definition(path: Path = OUTPUT_PATH) -> Path:
    definition = build_definition()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    output = write_definition()
    print(output)
