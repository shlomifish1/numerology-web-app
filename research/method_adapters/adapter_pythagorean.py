"""Read-only adapter for the existing numerology implementation."""

from __future__ import annotations

from typing import Dict, Optional

from numerology_calculator import NumerologyCalculator
from interpretation_layout import runtime_source_label

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

        peak_values = [
            calculator.peak1_reduced,
            calculator.peak2_reduced,
            calculator.peak3_reduced,
            calculator.peak4_reduced,
        ]
        challenge_values = [
            calculator.challenge1_reduced,
            calculator.challenge2_reduced,
            calculator.challenge3_reduced,
            calculator.challenge4_reduced,
        ]
        quarter_values = [
            calculator.first_quarter_reduced,
            calculator.second_quarter_reduced,
            calculator.third_quarter_reduced,
            calculator.forth_quarter_reduced,
        ]

        period_sections = []
        peak_challenge_combinations = []
        for index, (peak_value, challenge_value, quarter_value) in enumerate(
            zip(peak_values, challenge_values, quarter_values),
            start=1,
        ):
            combo_value = ""
            if peak_value is not None and challenge_value is not None:
                combo_value = f"{peak_value}{challenge_value}"
            peak_challenge_combinations.append(combo_value)

            peak_meaning = calculator.get_interpretation("peaks_interpretation", peak_value, gender_key)
            challenge_meaning = calculator.get_interpretation("challenges_interpretation", challenge_value, gender_key)
            combo_meaning = (
                calculator.get_interpretation(
                    "peak_challenge_comb",
                    combo_value,
                    gender_key,
                    is_peak_challenge_comb=True,
                )
                if combo_value
                else "[קובץ פרשנות לא נמצא: peak_challenge_comb/]"
            )
            meaning_parts = [
                f"פסגה {index}: {peak_meaning}",
                f"אתגר {index}: {challenge_meaning}",
                f"שילוב {index}: {combo_meaning}",
            ]

            source_parts = [
                runtime_source_label(gender_key, "peaks_interpretation"),
                runtime_source_label(gender_key, "challenges_interpretation"),
            ]
            if combo_value:
                source_parts.append(runtime_source_label(gender_key, "peak_challenge_comb"))

            period_sections.append(
                {
                    "key": f"peak_challenge_period_{index}",
                    "title": f"פסגה {index} | אתגר {index} | שילוב",
                    "value": " | ".join(
                        [
                            f"פסגה {peak_value if peak_value is not None else '-'}",
                            f"אתגר {challenge_value if challenge_value is not None else '-'}",
                            f"שילוב {combo_value or '-'}",
                        ]
                    ),
                    "meaning": "\n\n".join(part for part in meaning_parts if str(part or "").strip()),
                    "source": " | ".join(source_parts),
                }
            )

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
                "source": runtime_source_label(gender_key, "destiny"),
            },
            {
                "key": "birth_day",
                "title": "יום לידה",
                "value": calculator.p_day,
                "meaning": calculator.get_interpretation("birth_day", calculator.p_day, gender_key),
                "source": runtime_source_label(gender_key, "birth_day"),
            },
            {
                "key": "name_total",
                "title": "???????",
                "value": calculator.full_name_val,
                "meaning": calculator.get_interpretation("human_aspiration", calculator.full_name_val, gender_key),
                "source": runtime_source_label(gender_key, "human_aspiration"),
            },
            {
                "key": "outer",
                "title": "ביטוי חיצוני",
                "value": calculator.itzurim_val,
                "meaning": calculator.get_interpretation("consonants", calculator.itzurim_val, gender_key),
                "source": runtime_source_label(gender_key, "consonants"),
            },
            {
                "key": "soul",
                "title": "ביטוי פנימי",
                "value": calculator.aiv_val,
                "meaning": calculator.get_interpretation("vowels", calculator.aiv_val, gender_key),
                "source": runtime_source_label(gender_key, "vowels"),
            },
            {
                "key": "personal_year",
                "title": "שנה אישית",
                "value": calculator.shana_ishit,
                "meaning": calculator.get_interpretation("personal_year", calculator.shana_ishit, gender_key),
                "source": runtime_source_label(gender_key, "personal_year"),
            },
            {
                "key": "hidden_year",
                "title": "שנה נסתרת",
                "value": calculator.shana_nisteret,
                "meaning": calculator.get_interpretation("hidden_year", str(calculator.shana_nisteret), gender_key, is_hidden_year=True),
                "source": runtime_source_label(gender_key, "hidden_year"),
            },
            *period_sections,
            {
                "key": "next_step",
                "title": "השלב הבא",
                "value": " / ".join(str(item) for item in quarter_values if item is not None) or "-",
                "meaning": " | ".join(
                    filter(
                        None,
                        [
                            calculator.get_interpretation("quarters", quarter_values[0], gender_key),
                            calculator.get_interpretation("quarters", quarter_values[1], gender_key),
                            calculator.get_interpretation("quarters", quarter_values[2], gender_key),
                            calculator.get_interpretation("quarters", quarter_values[3], gender_key),
                        ],
                    )
                ),
                "source": runtime_source_label(gender_key, "quarters"),
            },
        ]

        return {
            "summary": "Base calculation from the existing men/women engine.",
            "metrics": metrics,
            "details": {
                "first_name_value": calculator.first_name_val,
                "full_name_value": calculator.full_name_val,
                "peaks": [
                    *peak_values,
                ],
                "challenges": [
                    *challenge_values,
                ],
                "peak_challenge_combinations": [
                    *peak_challenge_combinations,
                ],
                "quarters": [
                    *quarter_values,
                ],
            },
            "report_sections": report_sections,
            "report_summary": {
                "gender_key": gender_key,
                "destiny": calculator.final_number_destiny,
                "full_name_value": calculator.full_name_val,
                "personal_year": calculator.shana_ishit,
                "hidden_year": calculator.shana_nisteret,
                "peaks": peak_values,
                "challenges": challenge_values,
                "peak_challenge_combinations": peak_challenge_combinations,
                "quarters": quarter_values,
            },
        }
