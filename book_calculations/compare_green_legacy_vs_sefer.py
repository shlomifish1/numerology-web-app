from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
NUMEROLOGY_ROOT = SCRIPT_DIR.parent
if str(NUMEROLOGY_ROOT) not in sys.path:
    sys.path.insert(0, str(NUMEROLOGY_ROOT))

from calculators.registry import get_calculator

ROOT = SCRIPT_DIR
MAPPING_PATH = ROOT / "mappings" / "green_legacy_vs_sefer_hanumerologia_hashalem.overlap.json"
REPORTS_DIR = ROOT / "reports"
JSON_REPORT_PATH = REPORTS_DIR / "green_legacy_vs_sefer_hanumerologia_hashalem.parity.json"
MD_REPORT_PATH = REPORTS_DIR / "green_legacy_vs_sefer_hanumerologia_hashalem.parity.md"


def _split_birth_date(value: str) -> tuple[str, str, str]:
    year, month, day = value.split("-")
    return day, month, year


def _normalize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _legacy_payload(sample: dict[str, Any]) -> dict[str, Any]:
    day, month, year = _split_birth_date(str(sample["birth_date"]))
    return {
        "day": day,
        "month": month,
        "year": year,
        "first_name": sample["first_name"],
        "last_name": sample["last_name"],
        "gender": sample.get("gender", "female"),
    }


def _definition_payload(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "first_name": sample["first_name"],
        "last_name": sample["last_name"],
        "full_name": f"{sample['first_name']} {sample['last_name']}".strip(),
        "birth_date": sample["birth_date"],
        "current_year": sample.get("current_year", 2026),
        "letter": sample.get("letter", ""),
        "gender": sample.get("gender", "female"),
    }


def run() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    legacy = get_calculator(mapping["legacy_calculator_id"])
    definition = get_calculator(mapping["definition_calculator_id"])

    samples = mapping["sample_subjects"]

    legacy_by_sample: dict[str, dict[str, Any]] = {}
    definition_by_sample: dict[str, dict[str, Any]] = {}
    definition_entries_by_sample: dict[str, dict[str, dict[str, Any]]] = {}

    for sample in samples:
        sample_id = sample["sample_id"]
        legacy_result = legacy.calculate(_legacy_payload(sample))["results"]
        definition_result = definition.calculate(_definition_payload(sample))

        legacy_by_sample[sample_id] = legacy_result
        definition_by_sample[sample_id] = definition_result
        definition_entries_by_sample[sample_id] = {
            str(item.get("calc_key")): item
            for item in definition_result.get("results", [])
        }

    definition_supported = {
        str(item.get("calc_key")): item
        for item in definition.get_supported_calculations()
    }

    per_calculation: list[dict[str, Any]] = []
    total_missing_interpretation_text = 0
    total_missing_input_dependency_support = 0
    total_computable_only_legacy = 0
    total_computable_only_definition = 0

    for item in mapping["comparable_mappings"]:
        legacy_field = item["legacy_field"]
        legacy_interp_key = item.get("legacy_interpretation_key", "")
        definition_key = item["definition_calc_key"]

        sample_rows: list[dict[str, Any]] = []
        matched_samples = 0
        mismatched_samples = 0
        missing_samples = 0

        for sample in samples:
            sample_id = sample["sample_id"]
            legacy_value = legacy_by_sample[sample_id].get(legacy_field)
            def_entry = definition_entries_by_sample[sample_id].get(definition_key, {})
            definition_value = def_entry.get("value")
            definition_runtime_status = def_entry.get("status", "missing")

            if definition_runtime_status == "unsupported_inputs":
                total_missing_input_dependency_support += 1

            if legacy_value is not None and definition_runtime_status == "computed":
                if _normalize(legacy_value) == _normalize(definition_value):
                    compare_state = "same"
                    matched_samples += 1
                else:
                    compare_state = "different"
                    mismatched_samples += 1
            else:
                compare_state = "missing"
                missing_samples += 1
                if legacy_value is not None and definition_runtime_status != "computed":
                    total_computable_only_legacy += 1
                if legacy_value is None and definition_runtime_status == "computed":
                    total_computable_only_definition += 1

            legacy_interp = ""
            if legacy_interp_key and legacy_value is not None:
                try:
                    legacy_interp = legacy.get_interpretation(
                        legacy_interp_key,
                        legacy_value,
                        context={"gender": sample.get("gender", "female")},
                    )
                except Exception:
                    legacy_interp = ""

            definition_interp = str(def_entry.get("interpretation") or "")

            legacy_interp_available = bool(str(legacy_interp).strip())
            definition_interp_available = bool(definition_interp.strip())
            interpretation_available = legacy_interp_available or definition_interp_available
            if not interpretation_available:
                total_missing_interpretation_text += 1

            sample_rows.append(
                {
                    "sample_id": sample_id,
                    "legacy_result": legacy_value,
                    "definition_result": definition_value,
                    "comparison": compare_state,
                    "legacy_interpretation_available": legacy_interp_available,
                    "definition_interpretation_available": definition_interp_available,
                    "interpretation_available": interpretation_available,
                    "definition_runtime_status": definition_runtime_status,
                }
            )

        if mismatched_samples > 0:
            aggregate = "different"
        elif matched_samples > 0 and missing_samples == 0:
            aggregate = "same"
        elif matched_samples > 0:
            aggregate = "partial"
        else:
            aggregate = "missing"

        definition_status = definition_supported.get(definition_key, {}).get("status", "missing")

        per_calculation.append(
            {
                "calc_key": definition_key,
                "legacy_field": legacy_field,
                "equivalence": item.get("equivalence", ""),
                "notes": item.get("notes", ""),
                "definition_status": definition_status,
                "aggregate_comparison": aggregate,
                "sample_results": sample_rows,
                "counts": {
                    "matched_samples": matched_samples,
                    "mismatched_samples": mismatched_samples,
                    "missing_samples": missing_samples,
                },
            }
        )

    definition_status_counts: dict[str, int] = {}
    for supported in definition_supported.values():
        status = str(supported.get("status") or "")
        definition_status_counts[status] = definition_status_counts.get(status, 0) + 1

    matched_calc_count = sum(1 for row in per_calculation if row["aggregate_comparison"] == "same")
    mismatched_calc_count = sum(1 for row in per_calculation if row["aggregate_comparison"] == "different")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparison_id": mapping["comparison_id"],
        "legacy_calculator_id": mapping["legacy_calculator_id"],
        "definition_calculator_id": mapping["definition_calculator_id"],
        "samples": samples,
        "mapping": {
            "comparable_mappings": mapping["comparable_mappings"],
            "non_equivalent_mappings": mapping["non_equivalent_mappings"],
        },
        "per_calculation": per_calculation,
        "summary": {
            "total_overlapping_calculations": len(per_calculation),
            "matching_results_count": matched_calc_count,
            "mismatching_results_count": mismatched_calc_count,
            "computable_only_in_legacy": total_computable_only_legacy,
            "computable_only_in_definition": total_computable_only_definition,
            "still_needs_review": definition_status_counts.get("needs_review", 0),
            "unsupported": definition_status_counts.get("unsupported", 0),
            "missing_interpretation_text": total_missing_interpretation_text,
            "missing_input_dependency_support": total_missing_input_dependency_support,
            "could_not_map_reliably": len(mapping["non_equivalent_mappings"]),
        },
    }

    JSON_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Green Legacy vs Sefer Definition Parity Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Legacy calculator: `{report['legacy_calculator_id']}`",
        f"Definition calculator: `{report['definition_calculator_id']}`",
        "",
        "## Summary",
        f"- Overlapping calculations compared: {report['summary']['total_overlapping_calculations']}",
        f"- Matching results count: {report['summary']['matching_results_count']}",
        f"- Mismatching results count: {report['summary']['mismatching_results_count']}",
        f"- Computable only in legacy (sample-level): {report['summary']['computable_only_in_legacy']}",
        f"- Computable only in definition (sample-level): {report['summary']['computable_only_in_definition']}",
        f"- Definition still needs_review: {report['summary']['still_needs_review']}",
        f"- Definition unsupported: {report['summary']['unsupported']}",
        f"- Missing interpretation text (sample-level): {report['summary']['missing_interpretation_text']}",
        f"- Missing input dependency support (sample-level): {report['summary']['missing_input_dependency_support']}",
        f"- Could not map reliably: {report['summary']['could_not_map_reliably']}",
        "",
        "## Comparable Calculations",
    ]

    for row in per_calculation:
        lines.extend(
            [
                f"### {row['calc_key']}",
                f"- Legacy field: `{row['legacy_field']}`",
                f"- Equivalence: `{row['equivalence']}`",
                f"- Aggregate comparison: `{row['aggregate_comparison']}`",
                f"- Definition status: `{row['definition_status']}`",
                f"- Notes: {row['notes']}",
                f"- Sample counts: matched={row['counts']['matched_samples']}, mismatched={row['counts']['mismatched_samples']}, missing={row['counts']['missing_samples']}",
                "",
            ]
        )

    lines.append("## Non-Equivalent Mappings")
    for item in mapping["non_equivalent_mappings"]:
        lines.append(f"- `{item['legacy_field']}` -> `{item.get('definition_calc_key') or '(none)'}`: {item['reason']}")

    MD_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    return report


if __name__ == "__main__":
    data = run()
    print(json.dumps(data["summary"], ensure_ascii=False, indent=2))
