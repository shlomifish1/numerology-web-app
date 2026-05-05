from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
NUMEROLOGY_ROOT = SCRIPT_DIR.parent
if str(NUMEROLOGY_ROOT) not in sys.path:
    sys.path.insert(0, str(NUMEROLOGY_ROOT))

from calculators.registry import get_calculator
from book_calculations.subject_map_store import SeferSubjectMapStore

CALCULATOR_ID = "sefer_hanumerologia_hashalem"
DEFINITION_PATH = SCRIPT_DIR / "sefer_hanumerologia_hashalem.definition.json"
REPORTS_DIR = SCRIPT_DIR / "reports"


def _default_payload() -> dict[str, object]:
    return {
        "full_name": "???? ???",
        "birth_date": "1990-05-17",
        "current_year": 2026,
        "letter": "?",
    }


def _trace_is_full(trace: Mapping[str, Any] | None, computed_value: Any) -> bool:
    if not isinstance(trace, Mapping):
        return False
    if trace.get("trace_has_real_runtime_data") is not True:
        return False
    if trace.get("final_computed_value") != computed_value:
        return False
    runtime_steps = trace.get("runtime_steps")
    subject_inputs = trace.get("subject_inputs_used")
    return isinstance(runtime_steps, list) and len(runtime_steps) > 0 and isinstance(subject_inputs, Mapping)


def _final_status(runtime_status: str, blocked_reason: str | None, trace_is_full: bool) -> str:
    if runtime_status == "computed":
        return "computed" if trace_is_full else "partially_computed"
    if runtime_status == "unsupported_inputs":
        return "missing_inputs"
    if blocked_reason:
        return blocked_reason
    if runtime_status:
        return runtime_status
    return "needs_review"


def _result_group(status: str, scope: str) -> str:
    if status == "computed":
        return "computed_with_trace"
    if status == "partially_computed":
        return "computed_partial"
    if status == "interpretation_only" or scope == "research_only":
        return "interpretation_research"
    return "blocked_unsupported"


def _normalize_subject_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    full_name = str(payload.get("full_name") or "").strip()
    if not full_name:
        full_name = " ".join(part for part in (first_name, last_name) if part).strip()
    birth_date = str(payload.get("birth_date") or "").strip()

    normalized: dict[str, Any] = {
        "full_name": full_name,
        "birth_date": birth_date,
    }
    if first_name:
        normalized["first_name"] = first_name
    if last_name:
        normalized["last_name"] = last_name

    for key in ("current_year", "day", "month", "year"):
        value = payload.get(key)
        if value is None or str(value).strip() == "":
            continue
        try:
            normalized[key] = int(value)
        except Exception:
            normalized[key] = value

    letter = str(payload.get("letter") or "").strip()
    if letter:
        normalized["letter"] = letter

    # Keep additional internal research inputs (Hebrew aliases/custom keys)
    # without overriding canonical normalized fields above.
    for key, value in payload.items():
        if key in normalized:
            continue
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                continue
            normalized[key] = stripped
            continue
        normalized[key] = value

    return normalized


def _subject_identity(payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        "full_name": str(payload.get("full_name") or "").strip(),
        "first_name": str(payload.get("first_name") or "").strip(),
        "last_name": str(payload.get("last_name") or "").strip(),
        "birth_date": str(payload.get("birth_date") or "").strip(),
    }


def _stable_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _subject_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _cache_key(
    *,
    subject_hash: str,
    book_id: str,
    calculator_id: str,
    definition_version: str,
    calculator_version: str,
) -> str:
    key_payload = {
        "subject_hash": subject_hash,
        "book_id": book_id,
        "calculator_id": calculator_id,
        "definition_version": definition_version,
        "calculator_version": calculator_version,
    }
    return hashlib.sha256(_stable_json(key_payload).encode("utf-8")).hexdigest()


def run_subject_map(payload: dict[str, object]) -> dict[str, object]:
    normalized_payload = _normalize_subject_payload(payload)
    identity = _subject_identity(normalized_payload)
    calculator = get_calculator(CALCULATOR_ID)
    definition = json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))
    book_id = str(calculator.get_book_id() or CALCULATOR_ID)
    calculator_version = str(calculator.get_version() or "")
    definition_version = str(definition.get("definition_version") or "")

    subject_hash = _subject_hash(normalized_payload)
    cache_key = _cache_key(
        subject_hash=subject_hash,
        book_id=book_id,
        calculator_id=CALCULATOR_ID,
        definition_version=definition_version,
        calculator_version=calculator_version,
    )
    store = SeferSubjectMapStore()
    cached = store.get_cached_report(cache_key)
    if cached:
        cache_meta = cached.pop("_cache_db_meta", {}) if isinstance(cached.get("_cache_db_meta"), Mapping) else {}
        cached["materialization"] = {
            "source": "db_cache",
            "cache_hit": True,
            "cache_key": cache_key,
            "run_id": cache_meta.get("run_id"),
            "cached_created_at": cache_meta.get("created_at"),
            "cached_updated_at": cache_meta.get("updated_at"),
        }
        cached["subject_payload"] = normalized_payload
        cached["calculator_id"] = CALCULATOR_ID
        cached["book_id"] = book_id
        cached["calculator_version"] = calculator_version
        cached["definition_version"] = definition_version
        return cached

    runtime = calculator.calculate(normalized_payload)
    runtime_by_key = {str(item.get("calc_key")): item for item in runtime.get("results", [])}

    entries: list[dict[str, object]] = []
    blocked_counter: Counter[str] = Counter()
    group_counter: Counter[str] = Counter()
    with_interpretation = 0
    missing_interpretation = 0
    downgraded_partial = 0

    for calc in definition.get("calculations", []):
        calc_key = str(calc.get("calc_key"))
        runtime_item = runtime_by_key.get(calc_key, {})

        runtime_status = str(runtime_item.get("status") or "")
        blocked_reason = calc.get("blocked_reason")
        execution_trace = runtime_item.get("execution_trace")
        computed_value = runtime_item.get("value")
        trace_is_full = _trace_is_full(execution_trace if isinstance(execution_trace, Mapping) else None, computed_value)
        final_status = _final_status(runtime_status, blocked_reason if runtime_status != "computed" else None, trace_is_full)
        if runtime_status == "computed" and final_status == "partially_computed":
            downgraded_partial += 1

        interpretation = str(runtime_item.get("interpretation") or "")
        if interpretation.strip():
            with_interpretation += 1
        else:
            missing_interpretation += 1

        if final_status not in {"computed", "partially_computed"}:
            blocked_counter[final_status] += 1

        enabled_in_full_map = calc.get("enabled_in_full_map")
        if enabled_in_full_map is True:
            scope = "full_map"
        elif enabled_in_full_map is False:
            scope = "research_only"
        else:
            scope = "unspecified"
        group = _result_group(final_status, scope)
        group_counter[group] += 1

        entries.append(
            {
                "calc_key": calc_key,
                "label_he": calc.get("label_he"),
                "computed_value": computed_value,
                "status": final_status,
                "runtime_status": runtime_status,
                "reason_bucket": final_status if final_status not in {"computed", "partially_computed"} else "",
                "short_explanation": calc.get("short_explanation"),
                "interpretation": interpretation,
                "formula_text": calc.get("formula_text"),
                "formula_steps": calc.get("formula_steps") or [],
                "input_dependencies": calc.get("input_dependencies") or [],
                "source_refs": calc.get("source_refs") or [],
                "enabled_in_full_map": enabled_in_full_map,
                "scope": scope,
                "result_group": group,
                "trace_is_full": trace_is_full,
                "execution_trace": execution_trace if isinstance(execution_trace, dict) else {},
            }
        )

    summary = {
        "total_calculations": len(entries),
        "computed_with_full_trace": group_counter.get("computed_with_trace", 0),
        "computed_partial": group_counter.get("computed_partial", 0),
        "computable_returned": group_counter.get("computed_with_trace", 0) + group_counter.get("computed_partial", 0),
        "blocked_by_reason": dict(sorted(blocked_counter.items(), key=lambda kv: (-kv[1], kv[0]))),
        "interpretation_only": sum(1 for item in entries if item.get("status") == "interpretation_only"),
        "missing_interpretation": missing_interpretation,
        "with_interpretation": with_interpretation,
        "without_interpretation": missing_interpretation,
        "downgraded_to_partial_due_trace": downgraded_partial,
        "groups": dict(group_counter),
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "calculator_id": CALCULATOR_ID,
        "book_id": book_id,
        "calculator_version": calculator_version,
        "definition_version": definition_version,
        "subject_payload": normalized_payload,
        "summary": summary,
        "calculations": entries,
        "materialization": {
            "source": "fresh_execution",
            "cache_hit": False,
            "cache_key": cache_key,
            "run_id": None,
        },
    }
    run_id = store.save_report(
        cache_key=cache_key,
        subject_hash=subject_hash,
        subject_identity=identity,
        subject_payload=normalized_payload,
        book_id=book_id,
        calculator_id=CALCULATOR_ID,
        definition_version=definition_version,
        calculator_version=calculator_version,
        report=report,
    )
    report["materialization"]["run_id"] = run_id
    return report


def _write_markdown(report: dict[str, object], path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# Sefer Internal Subject Map",
        "",
        f"Generated: {report['generated_at']}",
        f"Calculator: `{report['calculator_id']}`",
        "",
        "## Summary",
        f"- Total calculations: {summary['total_calculations']}",
        f"- Computed with full trace: {summary.get('computed_with_full_trace', 0)}",
        f"- Computed partial: {summary.get('computed_partial', 0)}",
        f"- Computable returned: {summary['computable_returned']}",
        f"- With interpretation: {summary['with_interpretation']}",
        f"- Without interpretation: {summary['without_interpretation']}",
        f"- Missing interpretation: {summary.get('missing_interpretation', 0)}",
        f"- Downgraded to partial (trace): {summary.get('downgraded_to_partial_due_trace', 0)}",
        "- Blocked by reason:",
    ]
    for reason, count in summary["blocked_by_reason"].items():
        lines.append(f"  - `{reason}`: {count}")

    lines.extend(["", "## Calculations"])
    for calc in report["calculations"]:
        lines.extend(
            [
                f"### {calc['calc_key']}",
                f"- Label: {calc.get('label_he') or ''}",
                f"- Status: `{calc['status']}`",
                f"- Value: `{calc.get('computed_value')}`",
                f"- Scope: `{calc.get('scope')}`",
                f"- Interpretation available: {'yes' if str(calc.get('interpretation') or '').strip() else 'no'}",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Internal subject-map runner for sefer_hanumerologia_hashalem")
    parser.add_argument("--full-name", default=None)
    parser.add_argument("--birth-date", default=None)
    parser.add_argument("--current-year", type=int, default=None)
    parser.add_argument("--letter", default=None)
    parser.add_argument("--output-prefix", default="sefer_subject_map_sample")
    args = parser.parse_args()

    payload = _default_payload()
    if args.full_name:
        payload["full_name"] = args.full_name
    if args.birth_date:
        payload["birth_date"] = args.birth_date
    if args.current_year is not None:
        payload["current_year"] = args.current_year
    if args.letter:
        payload["letter"] = args.letter

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = run_subject_map(payload)

    json_path = REPORTS_DIR / f"{args.output_prefix}.json"
    md_path = REPORTS_DIR / f"{args.output_prefix}.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report, md_path)

    print(json.dumps({
        "json_output": str(json_path),
        "markdown_output": str(md_path),
        "summary": report["summary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
