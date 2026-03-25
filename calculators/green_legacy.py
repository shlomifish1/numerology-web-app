from __future__ import annotations

from typing import Any, Mapping

from numerology_calculator import NumerologyCalculator


class GreenLegacyCalculator:
    """Contract wrapper around the current production NumerologyCalculator."""

    _BOOK_ID = "green_legacy"
    _VERSION = "1.0.0"

    def __init__(self):
        self._calc = NumerologyCalculator()

    def calculate(self, subject_payload: Mapping[str, Any]) -> dict[str, Any]:
        day = str(subject_payload["day"]).zfill(2)
        month = str(subject_payload["month"]).zfill(2)
        year = str(subject_payload["year"]).strip()
        first_name = str(subject_payload["first_name"])
        last_name = str(subject_payload.get("last_name", ""))
        gender = str(subject_payload.get("gender", "female"))

        self._calc.calculate(
            day=day,
            month=month,
            year=year,
            first_name=first_name,
            last_name=last_name,
            gender=gender,
        )
        return self._normalized_result()

    def get_interpretation(self, calc_key: str, value: Any, context: Mapping[str, Any] | None = None) -> str:
        context = context or {}
        gender = str(context.get("gender", "female"))
        is_hidden_year = bool(context.get("is_hidden_year", False))
        is_peak_challenge_comb = bool(context.get("is_peak_challenge_comb", False))
        return self._calc.get_interpretation(
            calc_key,
            value,
            gender,
            is_hidden_year=is_hidden_year,
            is_peak_challenge_comb=is_peak_challenge_comb,
        )

    def get_supported_calculations(self) -> list[dict[str, Any]]:
        return [
            {"key": "destiny", "label": "Destiny Number"},
            {"key": "personal_year", "label": "Personal Year"},
            {"key": "hidden_year", "label": "Hidden Year"},
            {"key": "vowels", "label": "Soul Expression"},
            {"key": "consonants", "label": "Personality Number"},
        ]

    def get_book_id(self) -> str:
        return self._BOOK_ID

    def get_version(self) -> str:
        return self._VERSION

    def get_legacy_calculator(self) -> NumerologyCalculator:
        """Compatibility accessor for existing runtime paths expecting NumerologyCalculator."""
        return self._calc

    def _normalized_result(self) -> dict[str, Any]:
        return {
            "book_id": self.get_book_id(),
            "version": self.get_version(),
            "results": {
                "destiny": self._calc.final_number_destiny,
                "personal_year": self._calc.shana_ishit,
                "hidden_year": self._calc.shana_nisteret,
                "birth_day": self._calc.p_day,
                "name_value": self._calc.full_name_val,
                "soul_expression": self._calc.aiv_val,
                "personality": self._calc.itzurim_val,
            },
        }
