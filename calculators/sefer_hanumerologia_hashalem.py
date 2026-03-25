from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import json

from name_gematria_green import (
    NamesDataGreen,
    calc_missing_surplus_beneficial,
    letter_gematria_full,
)


class SeferHanumerologiaHashalemCalculator:
    """Definition-driven calculator for ספר הנומרולוגיה השלם."""

    _BOOK_ID = "sefer_hanumerologia_hashalem"
    _VERSION = "1.1.0"

    def __init__(self, definition_path: str | None = None):
        self._definition_path = Path(definition_path) if definition_path else (
            Path(__file__).resolve().parent.parent
            / "book_calculations"
            / "sefer_hanumerologia_hashalem.definition.json"
        )
        self._definition = json.loads(self._definition_path.read_text(encoding="utf-8"))

    def calculate(self, subject_payload: Mapping[str, Any]) -> dict[str, Any]:
        context = self._build_context(subject_payload)
        results: list[dict[str, Any]] = []

        computed_count = 0
        needs_review_count = 0
        unsupported_count = 0

        for calc in self._definition.get("calculations", []):
            calc_key = str(calc.get("calc_key", ""))
            execution = calc.get("execution") or {}
            method = execution.get("method") if isinstance(execution, dict) else None

            if method:
                value, status, reason, trace = self._compute_method(method, context)
                if status == "computed":
                    computed_count += 1
                elif status in {"needs_review", "missing_formula"}:
                    needs_review_count += 1
                else:
                    unsupported_count += 1
            else:
                formula_text = str(calc.get("formula_text") or "").strip()
                if formula_text:
                    value, status, reason = None, "missing_formula", "Formula exists but no executable rule is defined yet"
                else:
                    value, status, reason = None, "needs_review", "Calculation metadata is incomplete"
                trace = self._non_computable_trace(method=None, context=context, reason=reason)
                needs_review_count += 1

            interpretation_data = self._resolve_interpretation_details(calc, value)
            if isinstance(trace, dict):
                trace["source_refs_used"] = calc.get("source_refs") or []
                trace["matched_interpretation"] = interpretation_data
                trace["trace_has_real_runtime_data"] = self._has_real_trace(trace)

            results.append(
                {
                    "calc_key": calc_key,
                    "status": status,
                    "value": value,
                    "reason": reason,
                    "interpretation": interpretation_data.get("meaning", ""),
                    "source_refs": calc.get("source_refs", []),
                    "needs_review": calc.get("needs_review", {}),
                    "execution_method": method,
                    "execution_trace": trace,
                }
            )

        return {
            "book_id": self.get_book_id(),
            "version": self.get_version(),
            "definition_version": self._definition.get("definition_version"),
            "summary": {
                "total": len(results),
                "computed": computed_count,
                "needs_review": needs_review_count,
                "unsupported_inputs": unsupported_count,
            },
            "results": results,
        }

    def get_interpretation(self, calc_key: str, value: Any, context: Mapping[str, Any] | None = None) -> str:
        context = context or {}
        definitions = {c.get("calc_key"): c for c in self._definition.get("calculations", [])}
        calc = definitions.get(calc_key)
        if not calc:
            return ""
        interpretation_data = self._resolve_interpretation_details(calc, value)
        interpretation = interpretation_data.get("meaning", "")
        if interpretation:
            return interpretation
        return str(context.get("fallback", ""))

    def get_supported_calculations(self) -> list[dict[str, Any]]:
        return [
            {
                "calc_key": calc.get("calc_key"),
                "label_he": calc.get("label_he"),
                "status": calc.get("status"),
                "execution_method": (calc.get("execution") or {}).get("method"),
            }
            for calc in self._definition.get("calculations", [])
        ]

    def get_book_id(self) -> str:
        return self._BOOK_ID

    def get_version(self) -> str:
        return self._VERSION

    def _extract_birth_parts(self, subject_payload: Mapping[str, Any]) -> tuple[int | None, int | None, int | None]:
        if all(k in subject_payload for k in ("day", "month", "year")):
            return int(subject_payload["day"]), int(subject_payload["month"]), int(subject_payload["year"])

        birth_date = str(subject_payload.get("birth_date") or "").strip()
        if birth_date:
            if "-" in birth_date:
                year, month, day = birth_date.split("-")
                return int(day), int(month), int(year)
            if "/" in birth_date:
                day, month, year = birth_date.split("/")
                return int(day), int(month), int(year)
        return None, None, None

    def _extract_full_name(self, subject_payload: Mapping[str, Any]) -> str:
        full_name = str(subject_payload.get("full_name") or "").strip()
        if full_name:
            return full_name
        first = str(subject_payload.get("first_name") or "").strip()
        last = str(subject_payload.get("last_name") or "").strip()
        return f"{first} {last}".strip()

    def _build_letter_mapping(self, text: str) -> list[dict[str, Any]]:
        analyzer = NamesDataGreen()
        result: list[dict[str, Any]] = []
        position = 0
        for raw in str(text or ""):
            if raw.isspace():
                continue
            value = letter_gematria_full(raw)
            if value <= 0:
                continue
            position += 1
            result.append(
                {
                    "position": position,
                    "letter": raw,
                    "value": value,
                    "is_vowel": analyzer.is_vowel(raw),
                    "is_consonant": analyzer.is_consonant(raw),
                }
            )
        return result

    def _build_context(self, subject_payload: Mapping[str, Any]) -> dict[str, Any]:
        day, month, year = self._extract_birth_parts(subject_payload)
        first_name = str(subject_payload.get("first_name") or "").strip()
        last_name = str(subject_payload.get("last_name") or "").strip()
        full_name = self._extract_full_name(subject_payload)
        if not first_name and full_name:
            first_name = full_name.split()[0]
        current_year = int(subject_payload.get("current_year") or datetime.now().year)
        letter = str(subject_payload.get("letter") or "").strip()

        green = NamesDataGreen()
        name_data = green.analyze_name(full_name) if full_name else {
            "letters": [],
            "destiny_path": {"letters": [], "values": [], "final": None, "raw_sum": None},
            "soul_expression": {"letters": [], "values": [], "final": None, "raw_sum": None},
            "outer_behavior": {"letters": [], "values": [], "final": None, "raw_sum": None},
        }

        normalized_inputs = {
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "birth_date": str(subject_payload.get("birth_date") or "").strip(),
            "day": day,
            "month": month,
            "year": year,
            "current_year": current_year,
            "letter": letter,
        }

        return {
            "day": day,
            "month": month,
            "year": year,
            "current_year": current_year,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "letter": letter,
            "name_data": name_data,
            "digit_profile": calc_missing_surplus_beneficial(full_name) if full_name else None,
            "full_name_letter_mapping": self._build_letter_mapping(full_name),
            "first_name_letter_mapping": self._build_letter_mapping(first_name),
            "normalized_inputs": normalized_inputs,
            "date_parts": {"day": day, "month": month, "year": year},
        }
    def _base_trace(
        self,
        method: str,
        context: dict[str, Any],
        input_keys: list[str],
        *,
        include_name_mapping: bool = False,
        include_date_parts: bool = False,
    ) -> dict[str, Any]:
        subject_inputs = context.get("normalized_inputs", {})
        inputs_used = {key: subject_inputs.get(key) for key in input_keys}
        return {
            "method": method,
            "subject_inputs_used": inputs_used,
            "normalized_input_values": dict(subject_inputs),
            "date_parts_used": context.get("date_parts") if include_date_parts else {},
            "letter_to_number_mapping_used": context.get("full_name_letter_mapping", []) if include_name_mapping else [],
            "intermediate_sums": {},
            "reduction_steps": [],
            "master_number_preservation_decisions": [],
            "result_before_reduction": None,
            "result_after_reduction": None,
            "final_computed_value": None,
            "runtime_steps": [],
        }

    def _is_master_candidate(self, number: int) -> bool:
        text = str(abs(int(number)))
        return len(text) > 1 and len(set(text)) == 1

    def _reduce_with_trace(self, number: int, keep_masters: bool) -> dict[str, Any]:
        current = abs(int(number))
        steps: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        while current > 9:
            if keep_masters and self._is_master_candidate(current):
                decisions.append(
                    {
                        "value": current,
                        "decision": "preserve_master",
                        "reason": "Repeated-digit master value preserved",
                    }
                )
                break
            digits = [int(d) for d in str(current)]
            summed = sum(digits)
            steps.append({"from": current, "digits": digits, "sum": summed, "to": summed})
            current = summed
        return {
            "result_before_reduction": abs(int(number)),
            "result_after_reduction": current,
            "keep_masters": bool(keep_masters),
            "steps": steps,
            "master_number_preservation_decisions": decisions,
        }

    def _attach_reduction(self, trace: dict[str, Any], reduction: dict[str, Any]) -> None:
        trace["result_before_reduction"] = reduction.get("result_before_reduction")
        trace["result_after_reduction"] = reduction.get("result_after_reduction")
        trace["reduction_steps"] = reduction.get("steps", [])
        trace["master_number_preservation_decisions"] = reduction.get("master_number_preservation_decisions", [])

    def _non_computable_trace(self, *, method: str | None, context: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "method": method,
            "subject_inputs_used": {},
            "normalized_input_values": dict(context.get("normalized_inputs", {})),
            "date_parts_used": {},
            "letter_to_number_mapping_used": [],
            "intermediate_sums": {},
            "reduction_steps": [],
            "master_number_preservation_decisions": [],
            "result_before_reduction": None,
            "result_after_reduction": None,
            "final_computed_value": None,
            "runtime_steps": [{"action": "non_computable", "reason": reason}],
        }

    def _unsupported_with_trace(
        self,
        method: str,
        context: dict[str, Any],
        reason: str,
        missing_inputs: list[str],
    ) -> tuple[Any, str, str, dict[str, Any]]:
        trace = self._non_computable_trace(method=method, context=context, reason=reason)
        trace["missing_inputs"] = missing_inputs
        return None, "unsupported_inputs", reason, trace

    def _resolve_interpretation_details(self, calc: Mapping[str, Any], value: Any) -> dict[str, str]:
        if value is None:
            return {"key": "", "meaning": ""}
        by_value = calc.get("interpretations_by_value") or {}
        key = str(value)
        item = by_value.get(key)
        if isinstance(item, dict):
            return {"key": key, "meaning": str(item.get("meaning") or "")}
        return {"key": key, "meaning": ""}

    def _has_real_trace(self, trace: Mapping[str, Any]) -> bool:
        if not isinstance(trace, Mapping):
            return False
        runtime_steps = trace.get("runtime_steps")
        return trace.get("final_computed_value") is not None and isinstance(runtime_steps, list) and len(runtime_steps) > 0

    def _compute_name_bucket(
        self,
        method: str,
        context: dict[str, Any],
        bucket_key: str,
    ) -> tuple[Any, str, str, dict[str, Any]]:
        bucket = context["name_data"].get(bucket_key, {})
        final_value = bucket.get("final")
        raw_sum = bucket.get("raw_sum")
        letters = list(bucket.get("letters") or [])
        values = list(bucket.get("values") or [])
        if final_value is None or raw_sum is None:
            return self._unsupported_with_trace(method, context, "Missing required name inputs", ["full_name"])

        mapped = []
        analyzer = NamesDataGreen()
        for idx, (letter, value) in enumerate(zip(letters, values), start=1):
            mapped.append(
                {
                    "position": idx,
                    "letter": letter,
                    "value": int(value),
                    "is_vowel": analyzer.is_vowel(letter),
                    "is_consonant": analyzer.is_consonant(letter),
                }
            )

        reduction = self._reduce_with_trace(int(raw_sum), keep_masters=True)
        trace = self._base_trace(method, context, ["full_name"], include_name_mapping=False)
        trace["letter_to_number_mapping_used"] = mapped
        trace["intermediate_sums"] = {"raw_sum": int(raw_sum), "letters_count": len(mapped)}
        self._attach_reduction(trace, reduction)
        trace["runtime_steps"].extend(
            [
                {"action": "extract_relevant_letters", "count": len(mapped), "letters": [item["letter"] for item in mapped]},
                {"action": "map_letters_to_values", "mapped_count": len(mapped)},
                {"action": "sum_values", "raw_sum": int(raw_sum)},
                {"action": "reduce_number", "keep_masters": True, "result": int(reduction["result_after_reduction"])},
            ]
        )
        trace["final_computed_value"] = int(final_value)
        reason_map = {
            "destiny_path": "Computed from full-name gematria",
            "soul_expression": "Computed from vowel letters in full name",
            "outer_behavior": "Computed from consonant letters in full name",
        }
        return int(final_value), "computed", reason_map.get(bucket_key, "Computed from name analysis"), trace

    def _compute_method(self, method: str, context: dict[str, Any]) -> tuple[Any, str, str, dict[str, Any]]:
        if method == "name_destiny_path":
            return self._compute_name_bucket(method, context, "destiny_path")
        if method == "name_soul_expression":
            return self._compute_name_bucket(method, context, "soul_expression")
        if method == "name_outer_behavior":
            return self._compute_name_bucket(method, context, "outer_behavior")

        day, month, year = context.get("day"), context.get("month"), context.get("year")

        if method == "soul_plus_behavior_reduced":
            soul = context["name_data"].get("soul_expression", {}).get("final")
            outer = context["name_data"].get("outer_behavior", {}).get("final")
            if soul is None or outer is None:
                return self._unsupported_with_trace(method, context, "Missing required name inputs", ["full_name"])
            before = int(soul) + int(outer)
            reduction = self._reduce_with_trace(before, keep_masters=True)
            final_value = int(reduction["result_after_reduction"])
            trace = self._base_trace(method, context, ["full_name"])
            trace["intermediate_sums"] = {"soul_expression_final": int(soul), "outer_behavior_final": int(outer), "sum_before_reduction": before}
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend([
                {"action": "read_soul_expression", "value": int(soul)},
                {"action": "read_outer_behavior", "value": int(outer)},
                {"action": "sum", "lhs": int(soul), "rhs": int(outer), "result": before},
                {"action": "reduce_number", "keep_masters": True, "result": final_value},
            ])
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from soul-expression + outer-behavior reduction", trace

        if method == "name_full_raw_sum":
            raw_sum = context["name_data"].get("destiny_path", {}).get("raw_sum")
            if raw_sum is None:
                return self._unsupported_with_trace(method, context, "Missing required name inputs", ["full_name"])
            value = int(raw_sum)
            trace = self._base_trace(method, context, ["full_name"], include_name_mapping=True)
            trace["intermediate_sums"] = {"raw_sum": value}
            trace["result_before_reduction"] = value
            trace["result_after_reduction"] = value
            trace["runtime_steps"].append({"action": "sum_values", "raw_sum": value})
            trace["final_computed_value"] = value
            return value, "computed", "Computed from full-name letter-value sum", trace

        if method == "name_digit_profile":
            profile = context.get("digit_profile")
            if profile is None:
                return self._unsupported_with_trace(method, context, "Missing required name inputs", ["full_name"])
            trace = self._base_trace(method, context, ["full_name"], include_name_mapping=True)
            trace["runtime_steps"].append({"action": "calc_missing_surplus_beneficial", "letters_count": len(trace["letter_to_number_mapping_used"])})
            trace["intermediate_sums"] = {
                "reduced_letter_values": [
                    {
                        "letter": item["letter"],
                        "value": item["value"],
                        "reduced_value": self._reduce_with_trace(int(item["value"]), keep_masters=False)["result_after_reduction"],
                    }
                    for item in trace["letter_to_number_mapping_used"]
                ]
            }
            trace["final_computed_value"] = profile
            return profile, "computed", "Computed from digit appearance profile in full name", trace
        if method == "birth_date_component_sum_reduced":
            if None in (day, month, year):
                return self._unsupported_with_trace(method, context, "Missing birth day/month/year", ["birth_date", "day", "month", "year"])
            before = int(day) + int(month) + int(year)
            reduction = self._reduce_with_trace(before, keep_masters=True)
            final_value = int(reduction["result_after_reduction"])
            trace = self._base_trace(method, context, ["birth_date", "day", "month", "year"], include_date_parts=True)
            trace["intermediate_sums"] = {"day_plus_month_plus_year": before}
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend([
                {"action": "extract_date_parts", "day": int(day), "month": int(month), "year": int(year)},
                {"action": "sum", "formula": "day+month+year", "result": before},
                {"action": "reduce_number", "keep_masters": True, "result": final_value},
            ])
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from day+month+year reduction", trace

        if method == "birth_date_digit_sum_reduced":
            if None in (day, month, year):
                return self._unsupported_with_trace(method, context, "Missing birth day/month/year", ["birth_date", "day", "month", "year"])
            raw = f"{int(day):02d}{int(month):02d}{int(year):04d}"
            digits = [int(ch) for ch in raw]
            before = sum(digits)
            reduction = self._reduce_with_trace(before, keep_masters=True)
            final_value = int(reduction["result_after_reduction"])
            trace = self._base_trace(method, context, ["birth_date", "day", "month", "year"], include_date_parts=True)
            trace["intermediate_sums"] = {"digits": digits, "digit_sum": before}
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend([
                {"action": "format_birth_date_digits", "raw_digits": raw},
                {"action": "sum_digits", "digits": digits, "result": before},
                {"action": "reduce_number", "keep_masters": True, "result": final_value},
            ])
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from summed birth-date digits", trace

        if method == "birth_month_minus_day_reduced":
            if None in (day, month):
                return self._unsupported_with_trace(method, context, "Missing birth day/month", ["birth_date", "day", "month"])
            before = abs(int(month) - int(day))
            reduction = self._reduce_with_trace(before, keep_masters=False)
            final_value = int(reduction["result_after_reduction"])
            trace = self._base_trace(method, context, ["birth_date", "day", "month"], include_date_parts=True)
            trace["intermediate_sums"] = {"absolute_month_minus_day": before}
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].append({"action": "subtract_absolute", "lhs": int(month), "rhs": int(day), "result": before})
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from |month-day| reduction", trace

        if method == "birth_year_minus_day_reduced":
            if None in (day, year):
                return self._unsupported_with_trace(method, context, "Missing birth day/year", ["birth_date", "day", "year"])
            before = abs(int(year) - int(day))
            reduction = self._reduce_with_trace(before, keep_masters=False)
            final_value = int(reduction["result_after_reduction"])
            trace = self._base_trace(method, context, ["birth_date", "day", "year"], include_date_parts=True)
            trace["intermediate_sums"] = {"absolute_year_minus_day": before}
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].append({"action": "subtract_absolute", "lhs": int(year), "rhs": int(day), "result": before})
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from |year-day| reduction", trace

        if method == "age_from_current_year":
            if year is None:
                return self._unsupported_with_trace(method, context, "Missing birth year", ["birth_date", "year", "current_year"])
            final_value = int(context["current_year"]) - int(year)
            trace = self._base_trace(method, context, ["birth_date", "year", "current_year"], include_date_parts=True)
            trace["intermediate_sums"] = {"current_year_minus_birth_year": final_value}
            trace["runtime_steps"].append({"action": "subtract", "lhs": int(context["current_year"]), "rhs": int(year), "result": final_value})
            trace["result_before_reduction"] = final_value
            trace["result_after_reduction"] = final_value
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from current_year - birth_year", trace

        if method == "letter_numeric_value":
            letter = str(context.get("letter") or "").strip()
            if not letter:
                return self._unsupported_with_trace(method, context, "Missing 'letter' input", ["letter"])
            selected = letter[0]
            final_value = int(letter_gematria_full(selected))
            trace = self._base_trace(method, context, ["letter"])
            trace["letter_to_number_mapping_used"] = [{"position": 1, "letter": selected, "value": final_value}]
            trace["runtime_steps"].append({"action": "map_letter_to_value", "letter": selected, "value": final_value})
            trace["result_before_reduction"] = final_value
            trace["result_after_reduction"] = final_value
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from Hebrew letter numeric value", trace

        if method in {"first_letter", "last_letter", "name_middle_letter"}:
            full_name = str(context.get("full_name") or "").strip()
            compact = "".join(ch for ch in full_name if not ch.isspace())
            if not compact:
                return self._unsupported_with_trace(method, context, "Missing full_name input", ["full_name"])
            if method == "first_letter":
                final_value = compact[0]
                action = "take_first_letter"
                reason = "Computed as first letter of full name"
            elif method == "last_letter":
                final_value = compact[-1]
                action = "take_last_letter"
                reason = "Computed as last letter of full name"
            else:
                mid = (len(compact) - 1) // 2
                final_value = compact[mid]
                action = "take_middle_letter"
                reason = "Computed as middle letter of full name"
            trace = self._base_trace(method, context, ["full_name"], include_name_mapping=True)
            trace["runtime_steps"].append({"action": action, "compact_name": compact, "result": final_value})
            trace["final_computed_value"] = final_value
            return final_value, "computed", reason, trace

        if method == "month_of_birth":
            if month is None:
                return self._unsupported_with_trace(method, context, "Missing birth month", ["birth_date", "month"])
            final_value = int(month)
            trace = self._base_trace(method, context, ["birth_date", "month"], include_date_parts=True)
            trace["runtime_steps"].append({"action": "select_month", "result": final_value})
            trace["result_before_reduction"] = final_value
            trace["result_after_reduction"] = final_value
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from birth month", trace

        if method == "year_of_birth_last_two_digits":
            if year is None:
                return self._unsupported_with_trace(method, context, "Missing birth year", ["birth_date", "year"])
            final_value = int(year) % 100
            trace = self._base_trace(method, context, ["birth_date", "year"], include_date_parts=True)
            trace["runtime_steps"].append({"action": "modulo_100", "year": int(year), "result": final_value})
            trace["result_before_reduction"] = int(year)
            trace["result_after_reduction"] = final_value
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from last two digits of birth year", trace

        if method == "birth_date_civil":
            if None in (day, month, year):
                return self._unsupported_with_trace(method, context, "Missing birth day/month/year", ["birth_date", "day", "month", "year"])
            final_value = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            trace = self._base_trace(method, context, ["birth_date", "day", "month", "year"], include_date_parts=True)
            trace["runtime_steps"].append({"action": "format_civil_date", "result": final_value})
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed in civil YYYY-MM-DD format", trace

        if method == "first_name_raw_sum":
            first_name = str(context.get("first_name") or "").strip()
            if not first_name:
                return self._unsupported_with_trace(method, context, "Missing first_name input", ["first_name"])
            first_data = NamesDataGreen().analyze_name(first_name)
            raw_sum = first_data.get("destiny_path", {}).get("raw_sum")
            if raw_sum is None:
                return self._unsupported_with_trace(method, context, "Missing first_name input", ["first_name"])
            value = int(raw_sum)
            trace = self._base_trace(method, context, ["first_name"])
            trace["letter_to_number_mapping_used"] = context.get("first_name_letter_mapping", [])
            trace["intermediate_sums"] = {"first_name_raw_sum": value}
            trace["runtime_steps"].append({"action": "sum_first_name_values", "raw_sum": value})
            trace["result_before_reduction"] = value
            trace["result_after_reduction"] = value
            trace["final_computed_value"] = value
            return value, "computed", "Computed from first-name letter-value sum", trace

        if method == "birth_day_reduced":
            if day is None:
                return self._unsupported_with_trace(method, context, "Missing birth day", ["birth_date", "day"])
            reduction = self._reduce_with_trace(int(day), keep_masters=False)
            final_value = int(reduction["result_after_reduction"])
            trace = self._base_trace(method, context, ["birth_date", "day"], include_date_parts=True)
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].append({"action": "reduce_birth_day", "day": int(day), "result": final_value})
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from reduced birth day", trace

        if method in {"annual_influence_from_life_path_age", "period_end_plus_28_from_life_path", "season_end_36_minus_life_path"}:
            if None in (day, month, year):
                return self._unsupported_with_trace(method, context, "Missing birth day/month/year", ["birth_date", "day", "month", "year"])
            raw_digits = f"{int(day):02d}{int(month):02d}{int(year):04d}"
            digit_sum = sum(int(ch) for ch in raw_digits)
            life_path_reduction = self._reduce_with_trace(digit_sum, keep_masters=True)
            life_path = int(life_path_reduction["result_after_reduction"])
            trace = self._base_trace(method, context, ["birth_date", "day", "month", "year", "current_year"], include_date_parts=True)
            trace["life_path_reduction"] = life_path_reduction
            trace["intermediate_sums"] = {"birth_digit_sum": digit_sum, "life_path": life_path}
            trace["runtime_steps"].extend([
                {"action": "sum_birth_digits", "raw_digits": raw_digits, "result": digit_sum},
                {"action": "reduce_to_life_path", "keep_masters": True, "result": life_path},
            ])

            if method == "annual_influence_from_life_path_age":
                age = int(context["current_year"]) - int(year)
                before = life_path + age
                final_reduction = self._reduce_with_trace(before, keep_masters=True)
                final_value = int(final_reduction["result_after_reduction"])
                trace["intermediate_sums"].update({"age": age, "life_path_plus_age": before})
                self._attach_reduction(trace, final_reduction)
                trace["runtime_steps"].extend([
                    {"action": "compute_age", "current_year": int(context["current_year"]), "birth_year": int(year), "result": age},
                    {"action": "sum", "lhs": life_path, "rhs": age, "result": before},
                    {"action": "reduce_number", "keep_masters": True, "result": final_value},
                ])
                trace["final_computed_value"] = final_value
                return final_value, "computed", "Computed from life-path + age", trace

            if method == "period_end_plus_28_from_life_path":
                final_value = life_path + 28
                trace["intermediate_sums"].update({"plus_28": final_value})
                trace["runtime_steps"].append({"action": "add_constant", "constant": 28, "result": final_value})
                trace["result_before_reduction"] = final_value
                trace["result_after_reduction"] = final_value
                trace["final_computed_value"] = final_value
                return final_value, "computed", "Computed as life-path + 28", trace

            final_value = 36 - life_path
            trace["intermediate_sums"].update({"36_minus_life_path": final_value})
            trace["runtime_steps"].append({"action": "subtract_from_constant", "constant": 36, "result": final_value})
            trace["result_before_reduction"] = final_value
            trace["result_after_reduction"] = final_value
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed as 36 - life-path", trace

        trace = self._non_computable_trace(method=method, context=context, reason=f"Unknown execution method '{method}'")
        return None, "missing_formula", f"Unknown execution method '{method}'", trace
