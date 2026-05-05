from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import json
import re

from name_gematria_green import (
    NamesDataGreen,
    calc_name_change,
    calc_missing_surplus_beneficial,
    letter_gematria_full,
)


class SeferHanumerologiaHashalemCalculator:
    """Definition-driven calculator for ספר הנומרולוגיה השלם."""

    _BOOK_ID = "sefer_hanumerologia_hashalem"
    _VERSION = "1.2.0"

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
                value, status, reason, trace = self._compute_method(method, context, calc)
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
        for key, value in subject_payload.items():
            if key in normalized_inputs:
                continue
            if value is None:
                continue
            normalized_inputs[key] = value

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
            "raw_subject_payload": dict(subject_payload),
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

    def _execution_config(self, calc: Mapping[str, Any]) -> dict[str, Any]:
        execution = calc.get("execution") if isinstance(calc, Mapping) else None
        if isinstance(execution, Mapping):
            return dict(execution)
        return {}

    def _collect_input_keys(self, execution: Mapping[str, Any], fallback: Sequence[str] | None = None) -> list[str]:
        keys: list[str] = []
        single_key = execution.get("input_key")
        if isinstance(single_key, str) and single_key.strip():
            keys.append(single_key.strip())
        many_keys = execution.get("input_keys")
        if isinstance(many_keys, Sequence) and not isinstance(many_keys, (str, bytes)):
            for key in many_keys:
                if isinstance(key, str) and key.strip():
                    keys.append(key.strip())
        aliases = execution.get("input_aliases")
        if isinstance(aliases, Sequence) and not isinstance(aliases, (str, bytes)):
            for key in aliases:
                if isinstance(key, str) and key.strip():
                    keys.append(key.strip())
        if fallback:
            for key in fallback:
                if isinstance(key, str) and key.strip():
                    keys.append(key.strip())
        seen: set[str] = set()
        deduped: list[str] = []
        for key in keys:
            if key in seen:
                continue
            seen.add(key)
            deduped.append(key)
        return deduped

    def _lookup_input_value(
        self,
        context: Mapping[str, Any],
        keys: Sequence[str],
    ) -> tuple[str | None, Any]:
        normalized = context.get("normalized_inputs") if isinstance(context, Mapping) else {}
        if not isinstance(normalized, Mapping):
            normalized = {}
        raw_payload = context.get("raw_subject_payload") if isinstance(context, Mapping) else {}
        if not isinstance(raw_payload, Mapping):
            raw_payload = {}
        for key in keys:
            if key in normalized and normalized.get(key) not in (None, ""):
                return key, normalized.get(key)
            if key in raw_payload and raw_payload.get(key) not in (None, ""):
                return key, raw_payload.get(key)
        return None, None

    def _extract_digits(self, value: Any) -> list[int]:
        if value is None:
            return []
        if isinstance(value, int):
            return [int(ch) for ch in str(abs(value))]
        if isinstance(value, float):
            clean = str(value).replace(".", "")
            return [int(ch) for ch in clean if ch.isdigit()]
        text = str(value)
        return [int(ch) for ch in text if ch.isdigit()]

    def _parse_int_like(self, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return int(value)
        if isinstance(value, float):
            return int(value)
        digits = self._extract_digits(value)
        if not digits:
            return None
        try:
            return int("".join(str(d) for d in digits))
        except Exception:
            return None

    def _extract_fixed_number(self, calc: Mapping[str, Any]) -> int | None:
        for candidate in (
            str(calc.get("calc_key") or ""),
            str(calc.get("label_he") or ""),
            str(calc.get("formula_text") or ""),
        ):
            matches = re.findall(r"\d+", candidate)
            if not matches:
                continue
            try:
                return int(matches[0])
            except Exception:
                continue
        return None

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

    def _compute_method(
        self,
        method: str,
        context: dict[str, Any],
        calc: Mapping[str, Any] | None = None,
    ) -> tuple[Any, str, str, dict[str, Any]]:
        calc = calc or {}
        if method == "name_destiny_path":
            return self._compute_name_bucket(method, context, "destiny_path")
        if method == "name_soul_expression":
            return self._compute_name_bucket(method, context, "soul_expression")
        if method == "name_outer_behavior":
            return self._compute_name_bucket(method, context, "outer_behavior")
        if method == "fixed_number_from_calc_key":
            fixed = self._extract_fixed_number(calc)
            if fixed is None:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Could not extract fixed number from calc metadata",
                    ["calc_key", "label_he"],
                )
            reduction = self._reduce_with_trace(int(fixed), keep_masters=True)
            final_value = int(reduction["result_after_reduction"])
            if reduction.get("master_number_preservation_decisions"):
                final_value = int(fixed)
            trace = self._base_trace(method, context, [])
            trace["intermediate_sums"] = {"fixed_number": int(fixed)}
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend(
                [
                    {"action": "sum_values", "raw_sum": int(fixed)},
                    {"action": "reduce_number", "keep_masters": True, "result": int(final_value)},
                ]
            )
            trace["final_computed_value"] = int(final_value)
            return int(final_value), "computed", "Computed as fixed number defined by calculation metadata", trace

        if method == "constant_signature":
            execution = self._execution_config(calc)
            raw_constants = execution.get("constants")
            constants: list[int] = []
            if isinstance(raw_constants, Sequence) and not isinstance(raw_constants, (str, bytes)):
                for value in raw_constants:
                    parsed = self._parse_int_like(value)
                    if parsed is None:
                        continue
                    constants.append(parsed)
            if not constants:
                parsed_single = self._parse_int_like(execution.get("constant"))
                if parsed_single is not None:
                    constants = [parsed_single]
            if not constants:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing constants for signature executor",
                    ["constants"],
                )
            signature = "/".join(str(value) for value in constants)
            output_value: Any = execution.get("return_value_constant")
            if output_value is None:
                output_value = signature
            trace = self._base_trace(method, context, [])
            trace["intermediate_sums"] = {
                "constants": constants,
                "signature": signature,
            }
            trace["runtime_steps"].append({"action": "build_signature", "constants": constants, "signature": signature})
            trace["result_before_reduction"] = constants[0] if len(constants) == 1 else signature
            trace["result_after_reduction"] = output_value
            trace["final_computed_value"] = output_value
            return output_value, "computed", "Computed from explicit constant signature in source formula", trace

        if method == "digit_sum_reduce_input":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(execution, fallback=calc.get("input_dependencies") or [])
            selected_key, raw_value = self._lookup_input_value(context, input_keys)
            if raw_value in (None, ""):
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing numeric input for digit-sum reduction",
                    input_keys or ["numeric_input"],
                )
            digits = self._extract_digits(raw_value)
            if not digits:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Input does not contain digits for reduction",
                    [selected_key or "numeric_input"],
                )
            raw_sum = sum(digits)
            keep_masters = bool(execution.get("keep_masters", False))
            reduction = self._reduce_with_trace(raw_sum, keep_masters=keep_masters)
            reduced = int(reduction["result_after_reduction"])
            value_override = execution.get("return_value_constant")
            output_value = value_override if value_override is not None else reduced
            trace = self._base_trace(method, context, [selected_key] if selected_key else [])
            trace["intermediate_sums"] = {
                "selected_input_key": selected_key,
                "input_value": raw_value,
                "digits": digits,
                "digit_sum": raw_sum,
            }
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend(
                [
                    {"action": "extract_digits", "input_key": selected_key, "digits": digits},
                    {"action": "sum_digits", "result": raw_sum},
                    {"action": "reduce_number", "keep_masters": keep_masters, "result": reduced},
                ]
            )
            trace["final_computed_value"] = output_value
            return output_value, "computed", "Computed from input digit-sum reduction", trace

        if method == "letter_sum_reduce_input":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(execution, fallback=calc.get("input_dependencies") or [])
            selected_key, raw_value = self._lookup_input_value(context, input_keys)
            text_value = str(raw_value or "").strip()
            if not text_value:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing textual input for letter-value reduction",
                    input_keys or ["text_input"],
                )
            mapped = self._build_letter_mapping(text_value)
            if not mapped:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Input does not include supported Hebrew letters",
                    [selected_key or "text_input"],
                )
            raw_sum = sum(int(item.get("value", 0)) for item in mapped)
            keep_masters = bool(execution.get("keep_masters", True))
            reduction = self._reduce_with_trace(raw_sum, keep_masters=keep_masters)
            reduced = int(reduction["result_after_reduction"])
            value_override = execution.get("return_value_constant")
            output_value = value_override if value_override is not None else reduced
            trace = self._base_trace(method, context, [selected_key] if selected_key else [], include_name_mapping=False)
            trace["letter_to_number_mapping_used"] = mapped
            trace["intermediate_sums"] = {
                "selected_input_key": selected_key,
                "input_value": text_value,
                "letters_count": len(mapped),
                "raw_sum": raw_sum,
            }
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend(
                [
                    {"action": "extract_relevant_letters", "count": len(mapped), "letters": [item.get("letter") for item in mapped]},
                    {"action": "map_letters_to_values", "mapped_count": len(mapped)},
                    {"action": "sum_values", "raw_sum": raw_sum},
                    {"action": "reduce_number", "keep_masters": keep_masters, "result": reduced},
                ]
            )
            trace["final_computed_value"] = output_value
            return output_value, "computed", "Computed from letter-to-number mapping reduction", trace

        if method == "name_change_delta_reduced":
            execution = self._execution_config(calc)
            original_keys = self._collect_input_keys(
                {
                    "input_key": execution.get("original_input_key"),
                    "input_keys": execution.get("original_input_keys"),
                    "input_aliases": execution.get("original_input_aliases"),
                },
                fallback=["original_name", "שם קיים", "שם לפני שינוי", "שם משפחה לפני נישואין"],
            )
            new_keys = self._collect_input_keys(
                {
                    "input_key": execution.get("new_input_key"),
                    "input_keys": execution.get("new_input_keys"),
                    "input_aliases": execution.get("new_input_aliases"),
                },
                fallback=["new_name", "שם חדש", "שם אחרי שינוי", "שם משפחה אחרי נישואין"],
            )
            original_key, original_name = self._lookup_input_value(context, original_keys)
            new_key, new_name = self._lookup_input_value(context, new_keys)
            original_name = str(original_name or "").strip()
            new_name = str(new_name or "").strip()
            if not original_name or not new_name:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing original/new name inputs for change-impact calculation",
                    original_keys + new_keys,
                )
            profile = calc_name_change(original_name, new_name)
            combined = profile.get("combined") if isinstance(profile, Mapping) else {}
            combined_raw = int((combined or {}).get("raw_sum") or 0)
            combined_final = int((combined or {}).get("final") or 0)
            value_mode = str(execution.get("value_mode") or "combined_final")
            if value_mode == "delta_final":
                output_value: Any = int(profile.get("delta_final") or 0)
            elif value_mode == "delta_raw_sum":
                output_value = int(profile.get("delta_raw_sum") or 0)
            elif value_mode == "source":
                output_value = "source"
            else:
                output_value = combined_final
            value_override = execution.get("return_value_constant")
            if value_override is not None:
                output_value = value_override

            trace = self._base_trace(method, context, [original_key, new_key] if original_key and new_key else [])
            trace["intermediate_sums"] = {
                "original_input_key": original_key,
                "new_input_key": new_key,
                "original_name": original_name,
                "new_name": new_name,
                "original_raw_sum": int((profile.get("original") or {}).get("raw_sum") or 0),
                "new_layer_raw_sum": int((profile.get("new_layer") or {}).get("raw_sum") or 0),
                "combined_raw_sum": combined_raw,
                "combined_final": combined_final,
                "delta_raw_sum": int(profile.get("delta_raw_sum") or 0),
                "delta_final": int(profile.get("delta_final") or 0),
            }
            reduction = self._reduce_with_trace(combined_raw, keep_masters=True)
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend(
                [
                    {"action": "extract_relevant_letters", "input_key": original_key, "letters": list(original_name)},
                    {"action": "extract_relevant_letters", "input_key": new_key, "letters": list(new_name)},
                    {"action": "map_letters_to_values", "mapped_count": len((profile.get("combined") or {}).get("letters") or [])},
                    {"action": "sum_values", "raw_sum": combined_raw},
                    {"action": "reduce_number", "keep_masters": True, "result": combined_final},
                ]
            )
            trace["final_computed_value"] = output_value
            return output_value, "computed", "Computed from name-change profile comparison", trace

        if method == "divide_input":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(execution, fallback=calc.get("input_dependencies") or [])
            selected_key, raw_value = self._lookup_input_value(context, input_keys)
            parsed = self._parse_int_like(raw_value)
            if parsed is None:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing numeric input for division calculation",
                    input_keys or ["numeric_input"],
                )
            divisor = execution.get("divisor")
            try:
                divisor_value = float(divisor)
            except Exception:
                divisor_value = 0.0
            if divisor_value == 0:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Division divisor is missing or zero",
                    ["divisor"],
                )
            raw_result = float(parsed) / divisor_value
            if abs(raw_result - round(raw_result)) < 1e-9:
                output_value: Any = int(round(raw_result))
            else:
                output_value = round(raw_result, 6)
            value_override = execution.get("return_value_constant")
            if value_override is not None:
                output_value = value_override
            trace = self._base_trace(method, context, [selected_key] if selected_key else [])
            trace["intermediate_sums"] = {
                "selected_input_key": selected_key,
                "input_value": parsed,
                "divisor": divisor_value,
                "division_result": raw_result,
            }
            trace["runtime_steps"].extend(
                [
                    {"action": "read_input_value", "input_key": selected_key, "value": parsed},
                    {"action": "divide", "dividend": parsed, "divisor": divisor_value, "result": raw_result},
                ]
            )
            trace["result_before_reduction"] = raw_result
            trace["result_after_reduction"] = output_value
            trace["final_computed_value"] = output_value
            return output_value, "computed", "Computed from division executor", trace

        if method == "base_plus_factor_times_input":
            execution = self._execution_config(calc)
            base_keys = self._collect_input_keys(
                {
                    "input_key": execution.get("base_input_key"),
                    "input_keys": execution.get("base_input_keys"),
                    "input_aliases": execution.get("base_input_aliases"),
                },
                fallback=["base_value"],
            )
            index_keys = self._collect_input_keys(
                {
                    "input_key": execution.get("index_input_key"),
                    "input_keys": execution.get("index_input_keys"),
                    "input_aliases": execution.get("index_input_aliases"),
                },
                fallback=["index_value"],
            )
            base_key, base_raw = self._lookup_input_value(context, base_keys)
            index_key, index_raw = self._lookup_input_value(context, index_keys)
            base_value = self._parse_int_like(base_raw)
            index_value = self._parse_int_like(index_raw)
            if base_value is None or index_value is None:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing base/index numeric inputs for linear executor",
                    base_keys + index_keys,
                )
            factor = execution.get("factor")
            try:
                factor_value = float(factor)
            except Exception:
                factor_value = 1.0
            raw_result = float(base_value) + (factor_value * float(index_value))
            if abs(raw_result - round(raw_result)) < 1e-9:
                output_value: Any = int(round(raw_result))
            else:
                output_value = round(raw_result, 6)
            value_override = execution.get("return_value_constant")
            if value_override is not None:
                output_value = value_override
            trace = self._base_trace(method, context, [base_key, index_key] if base_key and index_key else [])
            trace["intermediate_sums"] = {
                "base_input_key": base_key,
                "base_value": base_value,
                "index_input_key": index_key,
                "index_value": index_value,
                "factor": factor_value,
                "result": raw_result,
            }
            trace["runtime_steps"].extend(
                [
                    {"action": "read_input_value", "input_key": base_key, "value": base_value},
                    {"action": "read_input_value", "input_key": index_key, "value": index_value},
                    {"action": "multiply", "lhs": factor_value, "rhs": index_value, "result": factor_value * float(index_value)},
                    {"action": "sum", "lhs": base_value, "rhs": factor_value * float(index_value), "result": raw_result},
                ]
            )
            trace["result_before_reduction"] = raw_result
            trace["result_after_reduction"] = output_value
            trace["final_computed_value"] = output_value
            return output_value, "computed", "Computed from linear base+factor*index executor", trace

        if method == "sum_inputs_reduce":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(execution, fallback=calc.get("input_dependencies") or [])
            values: list[int] = []
            used_keys: list[str] = []
            for key in input_keys:
                selected_key, raw_value = self._lookup_input_value(context, [key])
                parsed = self._parse_int_like(raw_value)
                if parsed is None:
                    continue
                values.append(parsed)
                used_keys.append(selected_key or key)
            expected_min = int(execution.get("min_inputs") or len(input_keys) or 2)
            if len(values) < expected_min:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing required numeric inputs for summed calculation",
                    list(input_keys),
                )
            before = sum(values)
            apply_reduction = bool(execution.get("apply_reduction", True))
            keep_masters = bool(execution.get("keep_masters", False))
            if apply_reduction:
                reduction = self._reduce_with_trace(before, keep_masters=keep_masters)
                final_value: Any = int(reduction["result_after_reduction"])
            else:
                reduction = {
                    "result_before_reduction": before,
                    "result_after_reduction": before,
                    "steps": [],
                    "master_number_preservation_decisions": [],
                }
                final_value = int(before)
            value_override = execution.get("return_value_constant")
            if value_override is not None:
                final_value = value_override
            trace = self._base_trace(method, context, used_keys)
            trace["intermediate_sums"] = {
                "used_inputs": dict(zip(used_keys, values)),
                "sum_before_reduction": before,
            }
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend(
                [
                    {"action": "collect_numeric_inputs", "used_keys": used_keys, "values": values},
                    {"action": "sum_values", "raw_sum": before},
                ]
            )
            if apply_reduction:
                trace["runtime_steps"].append(
                    {"action": "reduce_number", "keep_masters": keep_masters, "result": reduction["result_after_reduction"]}
                )
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from summed inputs executor", trace

        if method == "digit_sums_of_inputs_reduce":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(execution, fallback=calc.get("input_dependencies") or [])
            per_input: list[dict[str, Any]] = []
            for key in input_keys:
                selected_key, raw_value = self._lookup_input_value(context, [key])
                digits = self._extract_digits(raw_value)
                if not digits:
                    continue
                per_input.append(
                    {
                        "key": selected_key or key,
                        "raw_value": raw_value,
                        "digits": digits,
                        "digit_sum": sum(digits),
                    }
                )
            expected_min = int(execution.get("min_inputs") or len(input_keys) or 2)
            if len(per_input) < expected_min:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing required date/input values for digit-sum aggregation",
                    list(input_keys),
                )
            before = sum(int(item["digit_sum"]) for item in per_input)
            keep_masters = bool(execution.get("keep_masters", True))
            reduction = self._reduce_with_trace(before, keep_masters=keep_masters)
            reduced = int(reduction["result_after_reduction"])
            value_override = execution.get("return_value_constant")
            final_value: Any = value_override if value_override is not None else reduced
            used_keys = [str(item["key"]) for item in per_input]
            trace = self._base_trace(method, context, used_keys)
            trace["intermediate_sums"] = {
                "per_input_digit_sums": [
                    {
                        "key": item["key"],
                        "raw_value": item["raw_value"],
                        "digits": item["digits"],
                        "digit_sum": item["digit_sum"],
                    }
                    for item in per_input
                ],
                "sum_before_reduction": before,
            }
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend(
                [
                    {
                        "action": "sum_digits",
                        "inputs": [
                            {"key": item["key"], "digits": item["digits"], "digit_sum": item["digit_sum"]}
                            for item in per_input
                        ],
                        "result": before,
                    },
                    {"action": "reduce_number", "keep_masters": keep_masters, "result": reduced},
                ]
            )
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed by summing digit-sums of multiple inputs", trace

        if method == "input_as_integer":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(execution, fallback=calc.get("input_dependencies") or [])
            selected_key, raw_value = self._lookup_input_value(context, input_keys)
            parsed = self._parse_int_like(raw_value)
            if parsed is None:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing numeric input for integer extraction",
                    input_keys or ["numeric_input"],
                )
            value_override = execution.get("return_value_constant")
            output_value = value_override if value_override is not None else parsed
            trace = self._base_trace(method, context, [selected_key] if selected_key else [])
            trace["intermediate_sums"] = {"selected_input_key": selected_key, "input_value": raw_value, "parsed_integer": parsed}
            trace["runtime_steps"].append({"action": "parse_integer", "input_key": selected_key, "result": parsed})
            trace["result_before_reduction"] = parsed
            trace["result_after_reduction"] = output_value
            trace["final_computed_value"] = output_value
            return output_value, "computed", "Computed as parsed integer input", trace

        if method == "hebrew_month_name_to_number":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(
                execution,
                fallback=["hebrew_birth_month_name", "שם חודש עברי", "חודש לידה עברי"],
            )
            selected_key, raw_value = self._lookup_input_value(context, input_keys)
            month_name = str(raw_value or "").strip()
            if not month_name:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing Hebrew month-name input",
                    input_keys,
                )
            normalized = month_name.replace("\"", "").replace("'", "").replace("־", "-").replace(" ", "")
            month_map = {
                "ניסן": 1,
                "אייר": 2,
                "איר": 2,
                "סיון": 3,
                "סיוון": 3,
                "תמוז": 4,
                "אב": 5,
                "אלול": 6,
                "תשרי": 7,
                "חשון": 8,
                "חשוון": 8,
                "כסלו": 9,
                "טבת": 10,
                "שבט": 11,
                "אדר": 12,
                "אדרא": 12,
                "אדר1": 12,
                "אדר-א": 12,
                "אדרא'": 12,
                "אדרב": 13,
                "אדר2": 13,
                "אדר-ב": 13,
                "אדרב'": 13,
            }
            value = month_map.get(normalized)
            if value is None:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Unsupported Hebrew month name",
                    [selected_key or "hebrew_birth_month_name"],
                )
            value_override = execution.get("return_value_constant")
            output_value = value_override if value_override is not None else value
            trace = self._base_trace(method, context, [selected_key] if selected_key else [])
            trace["intermediate_sums"] = {
                "input_month_name": month_name,
                "normalized_month_name": normalized,
                "month_number": value,
            }
            trace["runtime_steps"].append(
                {"action": "map_hebrew_month_name", "input": month_name, "normalized": normalized, "result": value}
            )
            trace["result_before_reduction"] = value
            trace["result_after_reduction"] = output_value
            trace["final_computed_value"] = output_value
            return output_value, "computed", "Computed by mapping Hebrew month name to numeric index", trace

        if method == "classify_name_letter_ranges":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(execution, fallback=["full_name", "אותיות השם"])
            selected_key, raw_value = self._lookup_input_value(context, input_keys)
            text_value = str(raw_value or context.get("full_name") or "").strip()
            if not text_value:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing name input for letter-range classification",
                    input_keys,
                )
            mapped = self._build_letter_mapping(text_value)
            if not mapped:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Input does not include supported Hebrew letters",
                    [selected_key or "full_name"],
                )
            units = [item for item in mapped if int(item.get("value", 0)) < 10]
            tens = [item for item in mapped if 10 <= int(item.get("value", 0)) < 100]
            hundreds = [item for item in mapped if int(item.get("value", 0)) >= 100]
            result = {
                "units": [item.get("letter") for item in units],
                "tens": [item.get("letter") for item in tens],
                "hundreds": [item.get("letter") for item in hundreds],
                "counts": {"units": len(units), "tens": len(tens), "hundreds": len(hundreds)},
            }
            trace = self._base_trace(method, context, [selected_key] if selected_key else [], include_name_mapping=False)
            trace["letter_to_number_mapping_used"] = mapped
            trace["intermediate_sums"] = {"counts": result["counts"]}
            trace["runtime_steps"].extend(
                [
                    {"action": "extract_relevant_letters", "count": len(mapped), "letters": [item.get("letter") for item in mapped]},
                    {"action": "map_letters_to_values", "mapped_count": len(mapped)},
                    {"action": "classify_ranges", "counts": result["counts"]},
                ]
            )
            trace["final_computed_value"] = result
            return result, "computed", "Computed from unit/tens/hundreds letter classification", trace

        if method == "missing_numbers_profile":
            execution = self._execution_config(calc)
            name_keys = self._collect_input_keys(
                {
                    "input_key": execution.get("name_input_key"),
                    "input_keys": execution.get("name_input_keys"),
                    "input_aliases": execution.get("name_input_aliases"),
                },
                fallback=["birth_name_full", "שם לידה מלא", "full_name", "שם מלא"],
            )
            date_keys = self._collect_input_keys(
                {
                    "input_key": execution.get("date_input_key"),
                    "input_keys": execution.get("date_input_keys"),
                    "input_aliases": execution.get("date_input_aliases"),
                },
                fallback=["birth_date", "תאריך לידה"],
            )
            selected_name_key, name_value = self._lookup_input_value(context, name_keys)
            selected_date_key, date_value = self._lookup_input_value(context, date_keys)
            full_name = str(name_value or "").strip()
            birth_date_text = str(date_value or "").strip()
            if not full_name or not birth_date_text:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing required name or birth-date input for missing-numbers profile",
                    name_keys + date_keys,
                )
            name_profile = calc_missing_surplus_beneficial(full_name)
            date_digits = self._extract_digits(birth_date_text)
            present_in_date = sorted({digit for digit in date_digits if 1 <= digit <= 9})
            missing_in_date = [n for n in range(1, 10) if n not in present_in_date]
            missing_in_name = list(name_profile.get("missing") or [])
            missing_in_either = sorted(set(missing_in_name) | set(missing_in_date))
            missing_in_both = sorted(set(missing_in_name) & set(missing_in_date))
            result = {
                "missing_in_name": missing_in_name,
                "missing_in_birth_date": missing_in_date,
                "missing_in_either": missing_in_either,
                "missing_in_both": missing_in_both,
            }
            trace = self._base_trace(
                method,
                context,
                [selected_name_key, selected_date_key] if selected_name_key and selected_date_key else [],
            )
            trace["intermediate_sums"] = {
                "name_input_key": selected_name_key,
                "date_input_key": selected_date_key,
                "name_missing_numbers": missing_in_name,
                "date_digits": date_digits,
                "missing_in_either": missing_in_either,
                "missing_in_both": missing_in_both,
            }
            trace["runtime_steps"].extend(
                [
                    {"action": "calc_missing_surplus_beneficial", "missing": missing_in_name},
                    {"action": "sum_digits", "digits": date_digits},
                    {"action": "merge_missing_sets", "missing_in_either": missing_in_either, "missing_in_both": missing_in_both},
                ]
            )
            trace["final_computed_value"] = result
            return result, "computed", "Computed missing-numbers profile from full name and birth date", trace

        if method == "hidden_master_number_in_name":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(execution, fallback=["full_name", "שם"])
            selected_key, raw_value = self._lookup_input_value(context, input_keys)
            text_value = str(raw_value or context.get("full_name") or "").strip()
            if not text_value:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing name input for hidden-master detection",
                    input_keys,
                )
            mapped = self._build_letter_mapping(text_value)
            if not mapped:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Input does not include supported Hebrew letters",
                    [selected_key or "full_name"],
                )
            vowels = [item for item in mapped if bool(item.get("is_vowel"))]
            consonants = [item for item in mapped if bool(item.get("is_consonant"))]
            total_raw = sum(int(item.get("value", 0)) for item in mapped)
            vowels_raw = sum(int(item.get("value", 0)) for item in vowels)
            consonants_raw = sum(int(item.get("value", 0)) for item in consonants)

            def _master_or_none(value: int) -> int | None:
                return int(value) if self._is_master_candidate(int(value)) else None

            result = {
                "total_raw_sum": total_raw,
                "vowels_raw_sum": vowels_raw,
                "consonants_raw_sum": consonants_raw,
                "total_master": _master_or_none(total_raw),
                "vowels_master": _master_or_none(vowels_raw),
                "consonants_master": _master_or_none(consonants_raw),
            }
            masters = [value for key, value in result.items() if key.endswith("_master") and value is not None]
            result["masters_found"] = masters
            result["has_hidden_master"] = bool(masters)

            reduction = self._reduce_with_trace(total_raw, keep_masters=True)
            trace = self._base_trace(method, context, [selected_key] if selected_key else [], include_name_mapping=False)
            trace["letter_to_number_mapping_used"] = mapped
            trace["intermediate_sums"] = {
                "input_name": text_value,
                "total_raw_sum": total_raw,
                "vowels_raw_sum": vowels_raw,
                "consonants_raw_sum": consonants_raw,
                "masters_found": masters,
            }
            self._attach_reduction(trace, reduction)
            trace["runtime_steps"].extend(
                [
                    {"action": "extract_relevant_letters", "count": len(mapped), "letters": [item.get("letter") for item in mapped]},
                    {"action": "map_letters_to_values", "mapped_count": len(mapped)},
                    {"action": "sum_values", "raw_sum": total_raw},
                    {"action": "detect_master_numbers", "masters_found": masters},
                ]
            )
            trace["final_computed_value"] = result
            return result, "computed", "Computed hidden-master profile from vowel/consonant/full-name sums", trace

        if method == "life_path_combined_dual_method":
            execution = self._execution_config(calc)
            components = [
                ("hebrew_birth_day", ["יום לידה עברי"]),
                ("civil_birth_day", ["יום לידה אזרחי"]),
                ("hebrew_birth_month", ["חודש לידה עברי"]),
                ("civil_birth_month", ["חודש לידה אזרחי"]),
                ("hebrew_birth_year", ["שנת לידה עברית"]),
                ("civil_birth_year", ["שנת לידה אזרחית"]),
            ]
            values: dict[str, int] = {}
            used_keys: list[str] = []
            for canonical_key, aliases in components:
                selected_key, raw_value = self._lookup_input_value(context, [canonical_key, *aliases])
                parsed = self._parse_int_like(raw_value)
                if parsed is None:
                    continue
                values[canonical_key] = parsed
                used_keys.append(selected_key or canonical_key)

            life_path_keys = [("hebrew_life_path", ["שיעור חיים עברי"]), ("civil_life_path", ["שיעור חיים אזרחי"])]
            life_values: dict[str, int] = {}
            for canonical_key, aliases in life_path_keys:
                selected_key, raw_value = self._lookup_input_value(context, [canonical_key, *aliases])
                parsed = self._parse_int_like(raw_value)
                if parsed is None:
                    continue
                life_values[canonical_key] = parsed
                used_keys.append(selected_key or canonical_key)

            if len(values) < 6 and len(life_values) < 2:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing Hebrew/civil date components and life-path inputs for combined calculation",
                    [name for name, _aliases in components] + [name for name, _aliases in life_path_keys],
                )

            option_a = None
            if len(values) == 6:
                option_a_raw = sum(values.values())
                option_a = int(self._reduce_with_trace(option_a_raw, keep_masters=True)["result_after_reduction"])
            option_b = None
            if len(life_values) == 2:
                option_b_raw = sum(life_values.values())
                option_b = int(self._reduce_with_trace(option_b_raw, keep_masters=True)["result_after_reduction"])

            if option_a is not None and option_b is not None:
                final_value: Any = option_a if option_a == option_b else {"option_a": option_a, "option_b": option_b}
            elif option_a is not None:
                final_value = option_a
            else:
                final_value = option_b

            trace = self._base_trace(method, context, used_keys)
            trace["intermediate_sums"] = {
                "option_a_components": values,
                "option_a_result": option_a,
                "option_b_components": life_values,
                "option_b_result": option_b,
            }
            trace["runtime_steps"].extend(
                [
                    {"action": "collect_numeric_inputs", "option_a_components": values, "option_b_components": life_values},
                    {"action": "reduce_number", "keep_masters": True, "result": option_a, "label": "option_a"} if option_a is not None else {"action": "skip_option_a"},
                    {"action": "reduce_number", "keep_masters": True, "result": option_b, "label": "option_b"} if option_b is not None else {"action": "skip_option_b"},
                ]
            )
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed life-path combined value from dual-source methods", trace

        if method == "semi_annual_influence":
            execution = self._execution_config(calc)
            universal_key, universal_raw = self._lookup_input_value(context, ["universal_year", "שנה אוניברסאלית"])
            personal_key, personal_raw = self._lookup_input_value(context, ["personal_year", "שנה אישית"])
            life_key, life_raw = self._lookup_input_value(context, ["life_path", "שיעור חיים", "civil_life_path"])
            universal_year = self._parse_int_like(universal_raw)
            personal_year = self._parse_int_like(personal_raw)
            life_path = self._parse_int_like(life_raw)
            if None in (universal_year, personal_year, life_path):
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing universal/personal/life-path inputs for semi-annual influence",
                    ["universal_year", "personal_year", "life_path"],
                )
            first_raw = int(universal_year) + int(life_path)
            second_raw = int(life_path) - int(personal_year)
            reduce_outputs = bool(execution.get("reduce_outputs", True))
            if reduce_outputs:
                first = int(self._reduce_with_trace(first_raw, keep_masters=True)["result_after_reduction"])
                second = int(self._reduce_with_trace(abs(second_raw), keep_masters=True)["result_after_reduction"])
            else:
                first = first_raw
                second = second_raw
            result = {
                "first_half": first,
                "second_half": second,
                "first_half_raw": first_raw,
                "second_half_raw": second_raw,
            }
            trace = self._base_trace(method, context, [universal_key, personal_key, life_key] if universal_key and personal_key and life_key else [])
            trace["intermediate_sums"] = {
                "universal_year": universal_year,
                "personal_year": personal_year,
                "life_path": life_path,
                "first_half_raw": first_raw,
                "second_half_raw": second_raw,
            }
            trace["runtime_steps"].extend(
                [
                    {"action": "sum", "lhs": universal_year, "rhs": life_path, "result": first_raw, "label": "first_half_raw"},
                    {"action": "subtract", "lhs": life_path, "rhs": personal_year, "result": second_raw, "label": "second_half_raw"},
                ]
            )
            trace["final_computed_value"] = result
            return result, "computed", "Computed semi-annual influence using explicit chapter formula", trace

        if method == "letter_value_span_from_name":
            execution = self._execution_config(calc)
            input_keys = self._collect_input_keys(execution, fallback=["first_name", "שם פרטי"])
            selected_key, raw_value = self._lookup_input_value(context, input_keys)
            text_value = str(raw_value or "").strip()
            if not text_value:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing name input for letter-span placement",
                    input_keys,
                )
            mapped = self._build_letter_mapping(text_value)
            if not mapped:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Input does not include supported Hebrew letters",
                    [selected_key or "first_name"],
                )
            spans: list[dict[str, Any]] = []
            cursor = 1
            for item in mapped:
                value = int(item.get("value", 0))
                if value <= 0:
                    continue
                start = cursor
                end = cursor + value - 1
                spans.append({"letter": item.get("letter"), "value": value, "start": start, "end": end})
                cursor = end + 1
            result: Any = {
                "name": text_value,
                "spans": spans,
                "covered_positions": cursor - 1,
            }
            value_override = execution.get("return_value_constant")
            if value_override is not None:
                result = value_override
            trace = self._base_trace(method, context, [selected_key] if selected_key else [])
            trace["letter_to_number_mapping_used"] = mapped
            trace["intermediate_sums"] = {"spans": spans, "covered_positions": cursor - 1}
            trace["runtime_steps"].extend(
                [
                    {"action": "extract_relevant_letters", "count": len(mapped), "letters": [item.get("letter") for item in mapped]},
                    {"action": "map_letters_to_values", "mapped_count": len(mapped)},
                    {"action": "build_position_spans", "covered_positions": cursor - 1},
                ]
            )
            trace["final_computed_value"] = result
            return result, "computed", "Computed letter-span allocation from name letter values", trace

        if method == "common_letters_between_names":
            execution = self._execution_config(calc)
            left_keys = self._collect_input_keys(
                {
                    "input_key": execution.get("left_input_key"),
                    "input_keys": execution.get("left_input_keys"),
                    "input_aliases": execution.get("left_input_aliases"),
                },
                fallback=["first_name", "שם פרטי"],
            )
            right_keys = self._collect_input_keys(
                {
                    "input_key": execution.get("right_input_key"),
                    "input_keys": execution.get("right_input_keys"),
                    "input_aliases": execution.get("right_input_aliases"),
                },
                fallback=["last_name", "שם משפחה"],
            )
            left_key, left_raw = self._lookup_input_value(context, left_keys)
            right_key, right_raw = self._lookup_input_value(context, right_keys)
            left_name = str(left_raw or "").strip()
            right_name = str(right_raw or "").strip()
            if not left_name or not right_name:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing two names for common-letter analysis",
                    left_keys + right_keys,
                )
            left_letters = [item.get("letter") for item in self._build_letter_mapping(left_name)]
            right_letters = [item.get("letter") for item in self._build_letter_mapping(right_name)]
            common = sorted(set(left_letters) & set(right_letters))
            result = {
                "left_name": left_name,
                "right_name": right_name,
                "common_letters": common,
                "common_count": len(common),
            }
            trace = self._base_trace(method, context, [left_key, right_key] if left_key and right_key else [])
            trace["intermediate_sums"] = {
                "left_letters": left_letters,
                "right_letters": right_letters,
                "common_letters": common,
            }
            trace["runtime_steps"].append({"action": "intersect_letter_sets", "common_count": len(common)})
            trace["final_computed_value"] = result
            return result, "computed", "Computed common letters between the two names", trace

        if method == "parent_child_name_overlap":
            execution = self._execution_config(calc)
            child_key, child_raw = self._lookup_input_value(context, ["child_name", "שם הילד"])
            mother_key, mother_raw = self._lookup_input_value(context, ["mother_name", "שם האם"])
            father_key, father_raw = self._lookup_input_value(context, ["father_name", "שם האב"])
            child_name = str(child_raw or "").strip()
            mother_name = str(mother_raw or "").strip()
            father_name = str(father_raw or "").strip()
            if not child_name or not mother_name or not father_name:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing child/mother/father names for overlap comparison",
                    ["child_name", "mother_name", "father_name"],
                )
            child_profile = calc_missing_surplus_beneficial(child_name)
            mother_profile = calc_missing_surplus_beneficial(mother_name)
            father_profile = calc_missing_surplus_beneficial(father_name)
            child_present = {digit for digit in range(1, 10) if (child_profile.get("counts") or {}).get(digit, 0) > 0}
            mother_present = {digit for digit in range(1, 10) if (mother_profile.get("counts") or {}).get(digit, 0) > 0}
            father_present = {digit for digit in range(1, 10) if (father_profile.get("counts") or {}).get(digit, 0) > 0}
            parent_union = mother_present | father_present
            shared = sorted(child_present & parent_union)
            result = {
                "child_present_digits": sorted(child_present),
                "parent_present_digits": sorted(parent_union),
                "shared_digits": shared,
                "shared_count": len(shared),
            }
            trace = self._base_trace(
                method,
                context,
                [child_key, mother_key, father_key] if child_key and mother_key and father_key else [],
            )
            trace["intermediate_sums"] = {
                "child_present_digits": sorted(child_present),
                "mother_present_digits": sorted(mother_present),
                "father_present_digits": sorted(father_present),
                "shared_digits": shared,
            }
            trace["runtime_steps"].append({"action": "compare_digit_profiles", "shared_count": len(shared)})
            trace["final_computed_value"] = result
            return result, "computed", "Computed overlap of child digits with parental digit profiles", trace

        if method == "leap_year_adjustment":
            execution = self._execution_config(calc)
            year_type_key, year_type_raw = self._lookup_input_value(context, ["year_type", "סוג השנה (מעוברת/רגילה)"])
            year_key, year_raw = self._lookup_input_value(context, ["year_value", "year", "שנת לידה"])
            year_type_text = str(year_type_raw or "").strip().lower()
            year_value = self._parse_int_like(year_raw)
            if not year_type_text and year_value is None:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing year-type or numeric year input for leap-year adjustment",
                    ["year_type", "year_value"],
                )
            is_leap = False
            if year_type_text:
                if "מעובר" in year_type_text or "leap" in year_type_text:
                    is_leap = True
                elif "רגיל" in year_type_text or "regular" in year_type_text:
                    is_leap = False
            elif year_value is not None:
                is_leap = (year_value % 400 == 0) or (year_value % 4 == 0 and year_value % 100 != 0)
            result = {
                "is_leap_year": bool(is_leap),
                "adjustment_factor": 1 if is_leap else 0,
            }
            trace = self._base_trace(
                method,
                context,
                [year_type_key, year_key] if year_type_key or year_key else [],
            )
            trace["intermediate_sums"] = {
                "year_type_input": year_type_text,
                "year_value": year_value,
                "is_leap_year": bool(is_leap),
            }
            trace["runtime_steps"].append({"action": "detect_leap_year", "is_leap_year": bool(is_leap)})
            trace["final_computed_value"] = result
            return result, "computed", "Computed leap-year adjustment from year-type/year inputs", trace

        if method == "parent_role_gate":
            execution = self._execution_config(calc)
            role_key, role_raw = self._lookup_input_value(context, ["caregiver_role", "הורה מגדל"])
            age_key, age_raw = self._lookup_input_value(context, ["child_age", "גיל הילד"])
            role = str(role_raw or "").strip()
            child_age = self._parse_int_like(age_raw)
            if not role or child_age is None:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing caregiver role or child age for parent-role gate",
                    ["caregiver_role", "child_age"],
                )
            active_before_7 = int(child_age) < 7
            result = {
                "caregiver_role": role,
                "child_age": int(child_age),
                "active_before_age_7": active_before_7,
            }
            trace = self._base_trace(method, context, [role_key, age_key] if role_key and age_key else [])
            trace["intermediate_sums"] = {"caregiver_role": role, "child_age": int(child_age)}
            trace["runtime_steps"].append({"action": "age_gate", "threshold": 7, "active": active_before_7})
            trace["final_computed_value"] = result
            return result, "computed", "Computed caregiver relevance gate for ages below 7", trace

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

        if method == "letter_repetition_count":
            full_name = str(context.get("full_name") or "").strip()
            letter = str(context.get("letter") or "").strip()
            if not full_name or not letter:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing required full_name or letter input",
                    ["full_name", "letter"],
                )
            selected = letter[0]
            compact = "".join(ch for ch in full_name if not ch.isspace())
            count = sum(1 for ch in compact if ch == selected)
            is_repeated = count > 3
            final_value = {"letter": selected, "count": count, "is_repeated_over_3": is_repeated}
            trace = self._base_trace(method, context, ["full_name", "letter"], include_name_mapping=True)
            trace["intermediate_sums"] = {
                "selected_letter": selected,
                "name_length_without_spaces": len(compact),
                "occurrences": count,
                "threshold": 3,
            }
            trace["runtime_steps"].extend(
                [
                    {"action": "extract_relevant_letters", "count": len(compact), "letters": list(compact)},
                    {"action": "sum_values", "raw_sum": count},
                ]
            )
            trace["result_before_reduction"] = count
            trace["result_after_reduction"] = count
            trace["final_computed_value"] = final_value
            return final_value, "computed", "Computed from counting selected letter repetitions in full name", trace

        if method == "life_cycle_position_9_year":
            if year is None:
                return self._unsupported_with_trace(
                    method,
                    context,
                    "Missing birth year",
                    ["birth_date", "year", "current_year"],
                )
            current_year = int(context.get("current_year") or datetime.now().year)
            age = current_year - int(year)
            if age < 0:
                age = 0
            cycles_elapsed = age // 9
            position_in_cycle = (age % 9) + 1
            trace = self._base_trace(method, context, ["birth_date", "year", "current_year"], include_date_parts=True)
            trace["intermediate_sums"] = {
                "age": age,
                "cycles_elapsed_9_year_blocks": cycles_elapsed,
                "position_in_current_cycle_1_9": position_in_cycle,
            }
            trace["runtime_steps"].extend(
                [
                    {"action": "compute_age", "current_year": current_year, "birth_year": int(year), "result": age},
                    {"action": "sum", "lhs": cycles_elapsed, "rhs": 1, "result": position_in_cycle},
                ]
            )
            trace["result_before_reduction"] = position_in_cycle
            trace["result_after_reduction"] = position_in_cycle
            trace["final_computed_value"] = position_in_cycle
            return position_in_cycle, "computed", "Computed as 9-year cycle position from age", trace

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
