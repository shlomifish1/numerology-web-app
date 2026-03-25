from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
NUMEROLOGY_ROOT = SCRIPT_DIR.parent
if str(NUMEROLOGY_ROOT) not in sys.path:
    sys.path.insert(0, str(NUMEROLOGY_ROOT))

from book_calculations.sefer_hanumerologia_hashalem_builder import OUTPUT_PATH, write_definition

REPORTS_DIR = SCRIPT_DIR / "reports"
JSON_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.executor_expansion_pass.json"
MD_REPORT = REPORTS_DIR / "sefer_hanumerologia_hashalem.executor_expansion_pass.md"


def _infer_executor_type(calc_key: str, formula_text: str) -> str:
    key = calc_key.lower()
    formula = (formula_text or "").lower()

    if any(t in key for t in ["life_path", "shiyur_haim", "annual_influence", "yearly", "destiny_number_calculation", "mispar_holeeda"]):
        return "birth_date_life_path_composites"
    if any(t in key for t in ["first_letter", "last_letter", "balance_point", "source_chapter_5"]):
        return "name_letter_position"
    if any(t in key for t in ["source_chapter_6", "hitnahagut", "name_number", "shvil_goral_shem", "first_name"]):
        return "name_component_sum"
    if any(t in key for t in ["number_meaning", "street_number", "house_number", "passport_number", "id_number", "credit_card", "taxi_number", "car_number"]):
        return "external_identifier_digit_reduction"
    if any(t in key for t in ["period", "division", "season", "maturity", "action_point"]):
        return "period_arithmetic_sequences"
    if any(t in key for t in ["matching", "shared_life_path"]):
        return "pair_compatibility"
    if any(t in key for t in ["hebrew", "ivri", "month_number_calculation"]):
        return "hebrew_calendar_conversion"
    if any(t in key for t in ["missing_numbers", "excess_numbers", "master_number", "single_digit_reduction", "karma", "life_lesson"]):
        return "numeric_rule_engine"
    if "matrix" in key or "square" in key or "hexagon" in key or "chart" in key:
        return "matrix_structure_tables"
    if formula.startswith("n/a"):
        return "interpretation_only"
    return "misc_formula_executor"


def _type_profile(executor_type: str) -> dict[str, str | bool]:
    profiles = {
        "birth_date_life_path_composites": {"risk": "low", "uses_current_inputs": True, "deterministic": True},
        "name_letter_position": {"risk": "low", "uses_current_inputs": True, "deterministic": True},
        "name_component_sum": {"risk": "low", "uses_current_inputs": True, "deterministic": True},
        "numeric_rule_engine": {"risk": "medium", "uses_current_inputs": True, "deterministic": True},
        "period_arithmetic_sequences": {"risk": "medium", "uses_current_inputs": False, "deterministic": True},
        "external_identifier_digit_reduction": {"risk": "medium", "uses_current_inputs": False, "deterministic": True},
        "hebrew_calendar_conversion": {"risk": "high", "uses_current_inputs": False, "deterministic": False},
        "pair_compatibility": {"risk": "high", "uses_current_inputs": False, "deterministic": False},
        "matrix_structure_tables": {"risk": "high", "uses_current_inputs": False, "deterministic": False},
        "misc_formula_executor": {"risk": "high", "uses_current_inputs": False, "deterministic": False},
        "interpretation_only": {"risk": "low", "uses_current_inputs": False, "deterministic": False},
    }
    return profiles.get(executor_type, {"risk": "high", "uses_current_inputs": False, "deterministic": False})


def _index(calcs):
    return {c.get("calc_key"): c for c in calcs}


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    before = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    before_calcs = before.get("calculations", [])
    before_idx = _index(before_calcs)

    unsupported_before = [c for c in before_calcs if c.get("blocked_reason") == "unsupported_executor_type"]
    grouped = defaultdict(list)
    for c in unsupported_before:
        et = _infer_executor_type(str(c.get("calc_key") or ""), str(c.get("formula_text") or ""))
        grouped[et].append(str(c.get("calc_key")))

    ranked_executor_types = []
    for et, keys in sorted(grouped.items(), key=lambda kv: len(kv[1]), reverse=True):
        profile = _type_profile(et)
        ranked_executor_types.append(
            {
                "executor_type": et,
                "blocked_count": len(keys),
                "risk": profile["risk"],
                "uses_current_inputs": profile["uses_current_inputs"],
                "deterministic": profile["deterministic"],
                "sample_keys": keys[:10],
            }
        )

    write_definition(OUTPUT_PATH)

    after = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    after_calcs = after.get("calculations", [])
    after_idx = _index(after_calcs)

    computable_before = sum(1 for c in before_calcs if c.get("status") == "computable")
    computable_after = sum(1 for c in after_calcs if c.get("status") == "computable")

    unsupported_before_count = sum(1 for c in before_calcs if c.get("blocked_reason") == "unsupported_executor_type")
    unsupported_after_count = sum(1 for c in after_calcs if c.get("blocked_reason") == "unsupported_executor_type")

    promoted = []
    for key, after_calc in after_idx.items():
        before_calc = before_idx.get(key)
        if not before_calc:
            continue
        if before_calc.get("status") != "computable" and after_calc.get("status") == "computable":
            promoted.append(key)

    method_to_type = {
        "annual_influence_from_life_path_age": "birth_date_life_path_composites",
        "period_end_plus_28_from_life_path": "birth_date_life_path_composites",
        "season_end_36_minus_life_path": "birth_date_life_path_composites",
        "first_name_raw_sum": "name_component_sum",
        "name_middle_letter": "name_letter_position",
        "birth_day_reduced": "birth_date_life_path_composites",
    }

    unlocked_by_type: dict[str, list[str]] = defaultdict(list)
    for key in promoted:
        method = (after_idx.get(key, {}).get("execution") or {}).get("method")
        et = method_to_type.get(method)
        if not et:
            if method in {"birth_date_digit_sum_reduced", "birth_date_component_sum_reduced"}:
                et = "birth_date_life_path_composites"
            elif method in {"name_full_raw_sum", "name_digit_profile", "name_outer_behavior", "name_soul_expression", "name_destiny_path"}:
                et = "name_component_sum"
            elif method in {"first_letter", "last_letter"}:
                et = "name_letter_position"
            else:
                et = "misc_formula_executor"
        unlocked_by_type[et].append(key)

    blocked_after = [c for c in after_calcs if c.get("status") != "computable"]
    blocked_reason_counts = Counter((c.get("blocked_reason") or "unclassified") for c in blocked_after)

    implemented_executor_types = sorted([k for k in unlocked_by_type.keys()])

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "book_id": after.get("book_id"),
        "before": {
            "computable": computable_before,
            "unsupported_executor_type": unsupported_before_count,
        },
        "after": {
            "computable": computable_after,
            "unsupported_executor_type": unsupported_after_count,
        },
        "ranked_executor_types": ranked_executor_types,
        "implemented_executor_types": implemented_executor_types,
        "unlocked_by_executor_type": {k: sorted(v) for k, v in sorted(unlocked_by_type.items())},
        "blocked_counts_after_by_reason": dict(sorted(blocked_reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    }

    JSON_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Sefer Executor Expansion Pass",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Before / After",
        f"- Computable before: {computable_before}",
        f"- Computable after: {computable_after}",
        f"- unsupported_executor_type before: {unsupported_before_count}",
        f"- unsupported_executor_type after: {unsupported_after_count}",
        "",
        "## Implemented Executor Types",
    ]

    for et in implemented_executor_types:
        unlocked = report["unlocked_by_executor_type"].get(et, [])
        lines.append(f"- `{et}`: {len(unlocked)} unlocked")

    lines.extend(["", "## Ranked Unsupported Executor Types (Before)"])
    for row in ranked_executor_types:
        lines.append(
            f"- `{row['executor_type']}`: blocked={row['blocked_count']}, risk={row['risk']}, uses_current_inputs={row['uses_current_inputs']}, deterministic={row['deterministic']}"
        )

    lines.extend(["", "## Blocked After By Reason"])
    for reason, count in report["blocked_counts_after_by_reason"].items():
        lines.append(f"- `{reason}`: {count}")

    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "computable_before": computable_before,
        "computable_after": computable_after,
        "unsupported_executor_type_before": unsupported_before_count,
        "unsupported_executor_type_after": unsupported_after_count,
        "implemented_executor_types": implemented_executor_types,
        "unlocked_by_executor_type": {k: len(v) for k, v in unlocked_by_type.items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
