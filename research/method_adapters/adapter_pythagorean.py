"""Read-only adapter for the existing numerology implementation."""

from __future__ import annotations

from typing import Dict, Optional

from numerology_calculator import NumerologyCalculator

from .adapter_base import MethodAdapter


class PythagoreanMethodAdapter(MethodAdapter):
    def analyze(
        self,
        *,
        first_name: str,
        last_name: str,
        day: int,
        month: int,
        year: int,
        gender: str,
        hebrew_birthdate: Optional[Dict[str, int]] = None,
    ) -> Dict[str, object]:
        del hebrew_birthdate
        calculator = NumerologyCalculator()
        calculator.calculate(
            str(day).zfill(2),
            str(month).zfill(2),
            str(year),
            first_name,
            last_name,
            gender,
        )
        metrics = {
            "destiny": calculator.final_number_destiny,
            "name_total": calculator.full_name_val,
            "soul": calculator.aiv_val,
            "outer": calculator.itzurim_val,
            "personal_year": calculator.shana_ishit,
            "hidden_year": calculator.shana_nisteret,
            "missing": "לא מחושב",
            "beneficial": "לא מחושב",
            "surplus": "לא מחושב",
        }
        return {
            "summary": "חישוב פיתגוראי מחזורי מתוך המערכת הקיימת.",
            "metrics": metrics,
            "details": {
                "first_name_value": calculator.first_name_val,
                "full_name_value": calculator.full_name_val,
                "peaks": [
                    calculator.peak1_reduced,
                    calculator.peak2_reduced,
                    calculator.peak3_reduced,
                    calculator.peak4_reduced,
                ],
                "challenges": [
                    calculator.challenge1_reduced,
                    calculator.challenge2_reduced,
                    calculator.challenge3_reduced,
                    calculator.challenge4_reduced,
                ],
                "quarters": [
                    calculator.first_quarter_reduced,
                    calculator.second_quarter_reduced,
                    calculator.third_quarter_reduced,
                    calculator.forth_quarter_reduced,
                ],
            },
        }
