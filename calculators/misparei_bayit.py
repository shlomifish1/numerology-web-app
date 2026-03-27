from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import json


class MispareiBayitCalculator:
    """Pilot per-book calculator for מספרי בית."""

    _BOOK_ID = "misparei_bayit"
    _VERSION = "0.1.0"

    def __init__(self, definition_path: str | None = None):
        self._definition_path = Path(definition_path) if definition_path else (
            Path(__file__).resolve().parent.parent / "book_calculations" / "misparei_bayit.definition.json"
        )
        self._definition = json.loads(self._definition_path.read_text(encoding="utf-8"))

    def calculate(self, subject_payload: Mapping[str, Any]) -> dict[str, Any]:
        context = self._build_context(subject_payload)
        calculations = list(self._definition.get("calculations") or [])
        results: list[dict[str, Any]] = []

        blocked_by_reason: dict[str, int] = {}
        computed_count = 0
        for calc in calculations:
            result = self._execute_calculation(calc, context)
            results.append(result)
            status = str(result.get("status") or "")
            if status == "computed":
                computed_count += 1
            else:
                reason_bucket = str(result.get("reason_bucket") or "needs_review")
                blocked_by_reason[reason_bucket] = blocked_by_reason.get(reason_bucket, 0) + 1

        return {
            "book_id": self.get_book_id(),
            "version": self.get_version(),
            "definition_version": self._definition.get("definition_version"),
            "results": results,
            "summary": {
                "total": len(results),
                "computed": computed_count,
                "blocked": len(results) - computed_count,
                "blocked_by_reason": blocked_by_reason,
                "with_interpretation": sum(1 for item in results if str(item.get("interpretation") or "").strip()),
                "without_interpretation": sum(1 for item in results if not str(item.get("interpretation") or "").strip()),
            },
        }

    def get_interpretation(self, calc_key: str, value: Any, context: Mapping[str, Any] | None = None) -> str:
        context = context or {}
        calc = next(
            (item for item in self._definition.get("calculations", []) if str(item.get("calc_key")) == calc_key),
            None,
        )
        if calc is None:
            return str(context.get("fallback", ""))
        return self._resolve_interpretation(calc, value)

    def get_supported_calculations(self) -> list[dict[str, Any]]:
        return [
            {
                "calc_key": calc.get("calc_key"),
                "label_he": calc.get("label_he"),
                "status": calc.get("status"),
                "reason_bucket": calc.get("reason_bucket"),
                "short_explanation": calc.get("short_explanation"),
                "available_for_runtime": bool(((calc.get("input_metadata") or {}).get("available_for_runtime"))),
                "input_metadata": dict(calc.get("input_metadata") or {}),
            }
            for calc in self._definition.get("calculations", [])
        ]

    def get_calculation_input_metadata(self, calc_key: str | None = None) -> dict[str, Any]:
        if calc_key:
            calc = self._calc_by_key(calc_key)
            if calc is None:
                return {}
            return dict(calc.get("input_metadata") or {})
        return {
            str(calc.get("calc_key")): dict(calc.get("input_metadata") or {})
            for calc in self._definition.get("calculations", [])
        }

    def get_active_inputs_for_selection(self, selected_calculations: Sequence[str] | None = None) -> dict[str, Any]:
        selected = list(selected_calculations or [])
        selected_set = set(selected)
        if not selected:
            selected_set = {str(calc.get("calc_key")) for calc in self._definition.get("calculations", [])}

        active_inputs: set[str] = set()
        inherited_context_inputs: set[str] = set()
        labels: dict[str, str] = {}
        help_text: dict[str, str] = {}
        calculations_summary: list[dict[str, Any]] = []

        for calc in self._definition.get("calculations", []):
            calc_key = str(calc.get("calc_key") or "")
            if calc_key not in selected_set:
                continue
            input_meta = dict(calc.get("input_metadata") or {})
            required = [str(item) for item in input_meta.get("required_inputs") or []]
            optional = [str(item) for item in input_meta.get("optional_inputs") or []]
            inherited = [str(item) for item in input_meta.get("inherited_context_inputs") or []]
            active_inputs.update(required)
            active_inputs.update(optional)
            inherited_context_inputs.update(inherited)

            labels.update({str(k): str(v) for k, v in (input_meta.get("input_labels_he") or {}).items()})
            help_text.update({str(k): str(v) for k, v in (input_meta.get("input_help_text") or {}).items()})

            calculations_summary.append(
                {
                    "calc_key": calc_key,
                    "label_he": calc.get("label_he"),
                    "status": calc.get("status"),
                    "available_for_runtime": bool(input_meta.get("available_for_runtime")),
                    "required_inputs": required,
                    "optional_inputs": optional,
                    "inherited_context_inputs": inherited,
                }
            )

        return {
            "selected_calculations": sorted(selected_set),
            "active_inputs": sorted(active_inputs),
            "inherited_context_inputs": sorted(inherited_context_inputs),
            "input_labels_he": labels,
            "input_help_text": help_text,
            "calculations": calculations_summary,
        }

    def get_book_id(self) -> str:
        return self._BOOK_ID

    def get_version(self) -> str:
        return self._VERSION

    def _calc_by_key(self, calc_key: str) -> dict[str, Any] | None:
        for calc in self._definition.get("calculations", []):
            if str(calc.get("calc_key") or "") == calc_key:
                return dict(calc)
        return None

    def _build_context(self, subject_payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized_inputs: dict[str, Any] = {
            "apartment_number": subject_payload.get("apartment_number"),
            "street_number": subject_payload.get("street_number"),
            "address": subject_payload.get("address"),
            "building_number": subject_payload.get("building_number"),
            "floor_number": subject_payload.get("floor_number"),
            "current_year": subject_payload.get("current_year"),
        }
        return {
            "normalized_inputs": normalized_inputs,
            "raw_subject_payload": dict(subject_payload),
        }

    def _execute_calculation(self, calc: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
        calc_key = str(calc.get("calc_key") or "")
        method = str(((calc.get("execution") or {}).get("method") or "")).strip()

        if method == "house_number_basic":
            value, status, reason_bucket, trace = self._compute_house_number_basic(calc_key, context)
        elif method == "annual_house_frequency":
            value, status, reason_bucket, trace = self._compute_annual_house_frequency(calc_key, context)
        else:
            value = None
            status = str(calc.get("status") or "needs_review")
            reason_bucket = str(calc.get("reason_bucket") or "needs_review")
            trace = self._non_computable_trace(
                method=method or None,
                context=context,
                reason=f"Calculation '{calc_key}' is still in review",
            )

        interpretation = self._resolve_interpretation(calc, value)
        trace_has_real_runtime_data = self._has_real_trace(trace)
        trace["trace_has_real_runtime_data"] = trace_has_real_runtime_data

        return {
            "calc_key": calc_key,
            "label_he": str(calc.get("label_he") or ""),
            "status": status,
            "computed_value": value,
            "value": value,
            "interpretation": interpretation,
            "short_explanation": str(calc.get("short_explanation") or ""),
            "formula_text": str(calc.get("formula_text") or ""),
            "formula_steps": list(calc.get("formula_steps") or []),
            "source_refs": list(calc.get("source_refs") or []),
            "reason_bucket": reason_bucket,
            "execution_trace": trace,
            "trace_has_real_runtime_data": trace_has_real_runtime_data,
            "input_metadata": dict(calc.get("input_metadata") or {}),
        }

    def _compute_house_number_basic(
        self,
        calc_key: str,
        context: Mapping[str, Any],
    ) -> tuple[int | None, str, str, dict[str, Any]]:
        apartment_raw = self._read_input(context, "apartment_number")
        apartment_number = self._parse_int_like(apartment_raw)
        if apartment_number is None:
            return (
                None,
                "blocked_missing_input",
                "blocked_missing_input",
                self._non_computable_trace(
                    method="house_number_basic",
                    context=context,
                    reason="Missing required input: apartment_number",
                    missing_inputs=["apartment_number"],
                ),
            )

        reduction = self._reduce_digits_trace(apartment_number)
        trace = self._base_trace(context, "house_number_basic", ["apartment_number"])
        trace["intermediate_values"] = {
            "apartment_number_raw": apartment_raw,
            "apartment_number_numeric": apartment_number,
        }
        trace["reduction_steps"] = reduction["steps"]
        trace["result_before_reduction"] = reduction["before"]
        trace["result_after_reduction"] = reduction["after"]
        trace["final_computed_value"] = reduction["after"]
        trace["runtime_steps"] = [
            {"action": "read_apartment_number", "value": apartment_number},
            {"action": "reduce_digits", "steps_count": len(reduction["steps"]), "result": reduction["after"]},
        ]
        return int(reduction["after"]), "computed", "computed", trace

    def _compute_annual_house_frequency(
        self,
        calc_key: str,
        context: Mapping[str, Any],
    ) -> tuple[int | None, str, str, dict[str, Any]]:
        apartment_raw = self._read_input(context, "apartment_number")
        apartment_number = self._parse_int_like(apartment_raw)
        current_year_raw = self._read_input(context, "current_year")
        current_year = self._parse_int_like(current_year_raw)

        missing_inputs: list[str] = []
        if apartment_number is None:
            missing_inputs.append("apartment_number")
        if current_year is None:
            missing_inputs.append("current_year")
        if missing_inputs:
            return (
                None,
                "blocked_missing_input",
                "blocked_missing_input",
                self._non_computable_trace(
                    method="annual_house_frequency",
                    context=context,
                    reason="Missing required input(s)",
                    missing_inputs=missing_inputs,
                ),
            )

        house_reduction = self._reduce_digits_trace(apartment_number)
        year_reduction = self._reduce_digits_trace(current_year)
        combined_before = int(house_reduction["after"]) + int(year_reduction["after"])
        combined_reduction = self._reduce_digits_trace(combined_before)

        trace = self._base_trace(context, "annual_house_frequency", ["apartment_number", "current_year"])
        trace["intermediate_values"] = {
            "apartment_number_raw": apartment_raw,
            "apartment_number_numeric": apartment_number,
            "house_number_basic": house_reduction["after"],
            "current_year_raw": current_year_raw,
            "current_year_numeric": current_year,
            "year_reduced_value": year_reduction["after"],
            "combined_before_final_reduction": combined_before,
        }
        trace["year_reduction_steps"] = year_reduction["steps"]
        trace["house_reduction_steps"] = house_reduction["steps"]
        trace["reduction_steps"] = combined_reduction["steps"]
        trace["result_before_reduction"] = combined_reduction["before"]
        trace["result_after_reduction"] = combined_reduction["after"]
        trace["final_computed_value"] = combined_reduction["after"]
        trace["runtime_steps"] = [
            {"action": "reduce_year", "result": year_reduction["after"]},
            {"action": "reduce_house_number", "result": house_reduction["after"]},
            {"action": "sum", "lhs": year_reduction["after"], "rhs": house_reduction["after"], "result": combined_before},
            {"action": "reduce_digits", "steps_count": len(combined_reduction["steps"]), "result": combined_reduction["after"]},
        ]
        return int(combined_reduction["after"]), "computed", "computed", trace

    def _read_input(self, context: Mapping[str, Any], key: str) -> Any:
        normalized = context.get("normalized_inputs")
        if isinstance(normalized, Mapping) and key in normalized:
            return normalized.get(key)
        return None

    def _base_trace(self, context: Mapping[str, Any], method: str, input_keys: Sequence[str]) -> dict[str, Any]:
        normalized = context.get("normalized_inputs") if isinstance(context, Mapping) else {}
        if not isinstance(normalized, Mapping):
            normalized = {}
        return {
            "method": method,
            "subject_inputs_used": {key: normalized.get(key) for key in input_keys},
            "normalized_input_values": dict(normalized),
            "intermediate_values": {},
            "reduction_steps": [],
            "result_before_reduction": None,
            "result_after_reduction": None,
            "final_computed_value": None,
            "runtime_steps": [],
        }

    def _non_computable_trace(
        self,
        *,
        method: str | None,
        context: Mapping[str, Any],
        reason: str,
        missing_inputs: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        trace = self._base_trace(context, method or "needs_review", [])
        trace["runtime_steps"] = [{"action": "non_computable", "reason": reason}]
        trace["missing_inputs"] = list(missing_inputs or [])
        return trace

    def _parse_int_like(self, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return int(value)
        if isinstance(value, float):
            return int(value)
        text = str(value).strip()
        digits = [ch for ch in text if ch.isdigit()]
        if not digits:
            return None
        return int("".join(digits))

    def _reduce_digits_trace(self, number: int) -> dict[str, Any]:
        current = abs(int(number))
        steps: list[dict[str, Any]] = []
        while current > 9:
            digits = [int(ch) for ch in str(current)]
            reduced = sum(digits)
            steps.append({"from": current, "digits": digits, "sum": reduced, "to": reduced})
            current = reduced
        return {"before": abs(int(number)), "after": current, "steps": steps}

    def _resolve_interpretation(self, calc: Mapping[str, Any], value: Any) -> str:
        if value is None:
            return ""
        by_value = calc.get("interpretations_by_value")
        if not isinstance(by_value, Mapping):
            return ""
        key = str(value)
        data = by_value.get(key)
        if isinstance(data, Mapping):
            return str(data.get("meaning") or "")
        if isinstance(data, str):
            return data
        return ""

    def _has_real_trace(self, trace: Mapping[str, Any]) -> bool:
        return bool(trace.get("final_computed_value") is not None and trace.get("runtime_steps"))
