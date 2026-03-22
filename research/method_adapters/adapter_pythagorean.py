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

        gender_key = "women" if str(gender or "").strip().lower() in {"female", "women", "woman", "f", "נקבה"} else "men"

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

        report_sections = [
            {
                "key": "profile",
                "title": "פרופיל",
                "value": f"{first_name} {last_name}".strip() or "-",
                "meaning": f"תאריך הלידה: {day:02d}/{month:02d}/{year} · מין: {'נקבה' if gender_key == 'women' else 'זכר'}",
                "source": "קלט המשתמש",
            },
            {
                "key": "destiny",
                "title": "שביל גורל",
                "value": calculator.final_number_destiny,
                "meaning": calculator.get_interpretation("destiny", calculator.final_number_destiny, gender_key),
                "source": f"interpretations/{gender_key}/destiny",
            },
            {
                "key": "birth_day",
                "title": "יום לידה",
                "value": calculator.p_day,
                "meaning": calculator.get_interpretation("birth_day", calculator.p_day, gender_key),
                "source": f"interpretations/{gender_key}/birth_day",
            },
            {
                "key": "name_total",
                "title": "מספר שם מלא",
                "value": calculator.full_name_val,
                "meaning": calculator.get_interpretation("human_aspiration", calculator.full_name_val, gender_key),
                "source": f"interpretations/{gender_key}/human_aspiration",
            },
            {
                "key": "outer",
                "title": "ביטוי חיצוני",
                "value": calculator.itzurim_val,
                "meaning": calculator.get_interpretation("consonants", calculator.itzurim_val, gender_key),
                "source": f"interpretations/{gender_key}/consonants",
            },
            {
                "key": "soul",
                "title": "ביטוי פנימי",
                "value": calculator.aiv_val,
                "meaning": calculator.get_interpretation("vowels", calculator.aiv_val, gender_key),
                "source": f"interpretations/{gender_key}/vowels",
            },
            {
                "key": "personal_year",
                "title": "שנה אישית",
                "value": calculator.shana_ishit,
                "meaning": calculator.get_interpretation("personal_year", calculator.shana_ishit, gender_key),
                "source": f"interpretations/{gender_key}/personal_year",
            },
            {
                "key": "hidden_year",
                "title": "שנה נסתרת",
                "value": calculator.shana_nisteret,
                "meaning": calculator.get_interpretation("hidden_year", str(calculator.shana_nisteret), gender_key, is_hidden_year=True),
                "source": f"interpretations/{gender_key}/hidden_year",
            },
            {
                "key": "peaks",
                "title": "פסגות",
                "value": " / ".join(
                    str(item)
                    for item in [
                        calculator.peak1_reduced,
                        calculator.peak2_reduced,
                        calculator.peak3_reduced,
                        calculator.peak4_reduced,
                    ]
                    if item is not None
                ) or "-",
                "meaning": " | ".join(
                    filter(
                        None,
                        [
                            calculator.get_interpretation("peaks_interpretation", calculator.peak1_reduced, gender_key),
                            calculator.get_interpretation("peaks_interpretation", calculator.peak2_reduced, gender_key),
                            calculator.get_interpretation("peaks_interpretation", calculator.peak3_reduced, gender_key),
                            calculator.get_interpretation("peaks_interpretation", calculator.peak4_reduced, gender_key),
                        ],
                    )
                ),
                "source": f"interpretations/{gender_key}/peaks_interpretation",
            },
            {
                "key": "challenges",
                "title": "אתגרים",
                "value": " / ".join(
                    str(item)
                    for item in [
                        calculator.challenge1_reduced,
                        calculator.challenge2_reduced,
                        calculator.challenge3_reduced,
                        calculator.challenge4_reduced,
                    ]
                    if item is not None
                ) or "-",
                "meaning": " | ".join(
                    filter(
                        None,
                        [
                            calculator.get_interpretation("challenges_interpretation", calculator.challenge1_reduced, gender_key),
                            calculator.get_interpretation("challenges_interpretation", calculator.challenge2_reduced, gender_key),
                            calculator.get_interpretation("challenges_interpretation", calculator.challenge3_reduced, gender_key),
                            calculator.get_interpretation("challenges_interpretation", calculator.challenge4_reduced, gender_key),
                        ],
                    )
                ),
                "source": f"interpretations/{gender_key}/challenges_interpretation",
            },
            {
                "key": "next_step",
                "title": "השלב הבא",
                "value": " / ".join(
                    str(item)
                    for item in [
                        calculator.first_quarter_reduced,
                        calculator.second_quarter_reduced,
                        calculator.third_quarter_reduced,
                        calculator.forth_quarter_reduced,
                    ]
                    if item is not None
                ) or "-",
                "meaning": " | ".join(
                    filter(
                        None,
                        [
                            calculator.get_interpretation("quarters", calculator.first_quarter_reduced, gender_key),
                            calculator.get_interpretation("quarters", calculator.second_quarter_reduced, gender_key),
                            calculator.get_interpretation("quarters", calculator.third_quarter_reduced, gender_key),
                            calculator.get_interpretation("quarters", calculator.forth_quarter_reduced, gender_key),
                        ],
                    )
                ),
                "source": f"interpretations/{gender_key}/quarters",
            },
        ]

        return {
            "summary": "חישוב פיתגורי מחזורי מתוך המערכת הקיימת.",
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
            "report_sections": report_sections,
            "report_summary": {
                "gender_key": gender_key,
                "destiny": calculator.final_number_destiny,
                "full_name_value": calculator.full_name_val,
                "personal_year": calculator.shana_ishit,
                "hidden_year": calculator.shana_nisteret,
            },
        }
