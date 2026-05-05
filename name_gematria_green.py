"""Parallel gematria implementation based on the \"Michal Green\" method.

This module is intentionally standalone so the existing ``name.py`` flow stays
untouched. It exposes helper functions and a richer ``NamesDataGreen`` class
for research-only comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


HEBREW_FULL_GEMATRIA: Dict[str, int] = {
    "א": 1,
    "ב": 2,
    "ג": 3,
    "ד": 4,
    "ה": 5,
    "ו": 6,
    "ז": 7,
    "ח": 8,
    "ט": 9,
    "י": 10,
    "כ": 20,
    "ך": 20,
    "ל": 30,
    "מ": 40,
    "ם": 40,
    "נ": 50,
    "ן": 50,
    "ס": 60,
    "ע": 70,
    "פ": 80,
    "ף": 80,
    "צ": 90,
    "ץ": 90,
    "ק": 100,
    "ר": 200,
    "ש": 300,
    "ת": 400,
}

VOWELS_HEBREW = {"א", "ה", "ו", "י", "ע"}
MASTER_NUMBERS_2DIGIT = {11, 22, 33, 44, 55, 66, 77, 88, 99}
MASTER_NUMBERS_3DIGIT = {111, 222, 333, 444, 555, 666, 777, 888, 999}
MASTER_NUMBERS_4DIGIT = {1111, 2222, 3333, 4444, 5555, 6666, 7777, 8888, 9999}
MASTER_NUMBERS_ALL = (
    MASTER_NUMBERS_2DIGIT | MASTER_NUMBERS_3DIGIT | MASTER_NUMBERS_4DIGIT
)

MASTER_MEANINGS: Dict[int, str] = {
    11: "אטלנטיס הראשונה - מורה רוחני, מנחה.",
    22: "בנייה, כוח ומימוש בעולם החומר.",
    33: "מדע, ריפוי ויצירה בתדר גבוה.",
    44: "אחריות ארצית, הנהגה ותיקון.",
    55: "תקשורת עם רבדי מציאות נוספים.",
    66: "הרמוניה, איזון ושירות מיטיב.",
    77: "מיסטיקה עמוקה, ידע נסתר וחניכה.",
    88: "כוח חומרי בשירות ייעוד רוחני.",
    99: "סיום מחזורים והשלמה כוללת.",
}


def _digits_sum(number: int) -> int:
    return sum(int(digit) for digit in str(abs(number)))


def _repeated_digit(number: int) -> bool:
    text = str(abs(number))
    return len(text) > 1 and len(set(text)) == 1


def reduce_number(number: int, keep_masters: bool = True) -> int:
    """Reduce a number to a single digit or to a repeated-digit master."""
    current = abs(int(number))
    while current > 9:
        if keep_masters and (current in MASTER_NUMBERS_ALL or _repeated_digit(current)):
            return current
        current = _digits_sum(current)
    return current


def letter_gematria_full(letter: str) -> int:
    """Return the full gematria value for a single Hebrew letter."""
    return HEBREW_FULL_GEMATRIA.get(letter, 0)


def find_master_in_sum(raw_sum: int) -> Optional[int]:
    """Find a repeated-digit master number while reducing a raw sum."""
    current = abs(int(raw_sum))
    if current in MASTER_NUMBERS_ALL or _repeated_digit(current):
        return current
    while current > 9:
        current = _digits_sum(current)
        if current in MASTER_NUMBERS_ALL or _repeated_digit(current):
            return current
    return None


def calc_name_gematria_full(name_str: str) -> Dict[str, object]:
    """Calculate full gematria for a raw string, preserving master numbers."""
    letters = [letter for letter in name_str if letter in HEBREW_FULL_GEMATRIA]
    values = [letter_gematria_full(letter) for letter in letters]
    raw_sum = sum(values)
    master = find_master_in_sum(raw_sum)
    final = reduce_number(raw_sum, keep_masters=True)
    return {
        "letters": letters,
        "values": values,
        "raw_sum": raw_sum,
        "master": master,
        "final": final,
        "meaning": MASTER_MEANINGS.get(master),
    }


def calc_missing_surplus_beneficial(full_name_str: str) -> Dict[str, object]:
    """Count recurring reduced values 1-9 in the full birth name."""
    counts = {digit: 0 for digit in range(1, 10)}
    for letter in full_name_str:
        value = letter_gematria_full(letter)
        if not value:
            continue
        reduced = reduce_number(value, keep_masters=False)
        counts[reduced] += 1

    missing = [digit for digit, count in counts.items() if count == 0]
    available = [digit for digit, count in counts.items() if count in (1, 2)]
    beneficial = [digit for digit, count in counts.items() if count == 3]
    surplus = [digit for digit, count in counts.items() if count >= 4]
    return {
        "counts": counts,
        "missing": missing,
        "available": available,
        "beneficial": beneficial,
        "surplus": surplus,
    }


def calc_name_change(original_name: str, new_name: str) -> Dict[str, object]:
    """Compare the original name vibration with an added nickname/new name."""
    original = calc_name_gematria_full(original_name)
    new_layer = calc_name_gematria_full(new_name)
    combined = calc_name_gematria_full(f"{original_name}{new_name}")
    return {
        "original": original,
        "new_layer": new_layer,
        "combined": combined,
        "delta_raw_sum": combined["raw_sum"] - original["raw_sum"],
        "delta_final": combined["final"] - original["final"],
    }


def calc_three_life_cycles(
    day: int,
    month: int,
    year: int,
    hebrew_day: Optional[int] = None,
    hebrew_month: Optional[int] = None,
    hebrew_year: Optional[int] = None,
) -> Dict[str, Dict[str, int]]:
    """Return the three life cycles in Gregorian, Hebrew and combined views."""
    gregorian = {
        "cycle_1": reduce_number(day),
        "cycle_2": reduce_number(month),
        "cycle_3": reduce_number(year),
    }
    if hebrew_day is None or hebrew_month is None or hebrew_year is None:
        hebrew = {"cycle_1": 0, "cycle_2": 0, "cycle_3": 0}
    else:
        hebrew = {
            "cycle_1": reduce_number(hebrew_day),
            "cycle_2": reduce_number(hebrew_month),
            "cycle_3": reduce_number(hebrew_year),
        }
    combined = {
        key: reduce_number(gregorian[key] + hebrew[key], keep_masters=False)
        for key in gregorian
    }
    return {"gregorian": gregorian, "hebrew": hebrew, "combined": combined}


@dataclass
class NameBucket:
    letters: List[str]
    values: List[int]
    raw_sum: int
    master: Optional[int]
    final: int
    meaning: Optional[str]

    def as_dict(self) -> Dict[str, object]:
        return {
            "letters": self.letters,
            "values": self.values,
            "raw_sum": self.raw_sum,
            "master": self.master,
            "final": self.final,
            "meaning": self.meaning,
        }


class NamesDataGreen:
    """Research-friendly name analysis for the full gematria method."""

    def letter_value(self, letter: str, vav_as_vowel: bool = True) -> int:
        del vav_as_vowel
        return letter_gematria_full(letter)

    def is_vowel(self, letter: str, vav_as_vowel: bool = True) -> bool:
        if letter == "ו":
            return vav_as_vowel
        return letter in VOWELS_HEBREW

    def is_consonant(self, letter: str, vav_as_vowel: bool = True) -> bool:
        return letter in HEBREW_FULL_GEMATRIA and not self.is_vowel(
            letter, vav_as_vowel=vav_as_vowel
        )

    def _analyze_letters(
        self, letters: Iterable[str], vav_as_vowel: bool = True
    ) -> NameBucket:
        del vav_as_vowel
        letter_list = [letter for letter in letters if letter in HEBREW_FULL_GEMATRIA]
        values = [self.letter_value(letter) for letter in letter_list]
        raw_sum = sum(values)
        master = find_master_in_sum(raw_sum)
        final = reduce_number(raw_sum, keep_masters=True)
        return NameBucket(
            letters=letter_list,
            values=values,
            raw_sum=raw_sum,
            master=master,
            final=final,
            meaning=MASTER_MEANINGS.get(master),
        )

    def analyze_name(self, name_str: str, vav_as_vowel: bool = True) -> Dict[str, object]:
        clean_letters = [letter for letter in name_str if letter in HEBREW_FULL_GEMATRIA]
        vowels = [
            letter
            for letter in clean_letters
            if self.is_vowel(letter, vav_as_vowel=vav_as_vowel)
        ]
        consonants = [
            letter
            for letter in clean_letters
            if self.is_consonant(letter, vav_as_vowel=vav_as_vowel)
        ]
        combined = self._analyze_letters(clean_letters, vav_as_vowel=vav_as_vowel)
        soul = self._analyze_letters(vowels, vav_as_vowel=vav_as_vowel)
        outer = self._analyze_letters(consonants, vav_as_vowel=vav_as_vowel)
        return {
            "input": name_str,
            "letters": clean_letters,
            "soul_expression": soul.as_dict(),
            "outer_behavior": outer.as_dict(),
            "destiny_path": combined.as_dict(),
        }

    def analyze_name_with_vav_options(self, name_str: str) -> Dict[str, object]:
        as_vowel = self.analyze_name(name_str, vav_as_vowel=True)
        as_consonant = self.analyze_name(name_str, vav_as_vowel=False)
        note = None
        if as_vowel["soul_expression"]["final"] != as_consonant["soul_expression"]["final"]:
            note = "ו' משנה את חישוב התנועה מול העיצור ולכן נדרשת ולידציה אנושית."
        return {
            "as_vowel": as_vowel,
            "as_consonant": as_consonant,
            "note": note,
        }

    def analyze_full_name(
        self,
        first_name: str,
        last_name: str,
        day: Optional[int] = None,
        month: Optional[int] = None,
        year: Optional[int] = None,
        hebrew_birthdate: Optional[Dict[str, int]] = None,
    ) -> Dict[str, object]:
        full_name = " ".join(part for part in [first_name.strip(), last_name.strip()] if part)
        name_analysis = self.analyze_name_with_vav_options(full_name)
        missing_info = calc_missing_surplus_beneficial(full_name)

        birthdate_analysis = None
        if day is not None and month is not None and year is not None:
            destiny = reduce_number(day + month + year)
            birthdate_analysis = {
                "day": reduce_number(day),
                "month": reduce_number(month),
                "year": reduce_number(year),
                "destiny": destiny,
                "life_cycles": calc_three_life_cycles(
                    day=day,
                    month=month,
                    year=year,
                    hebrew_day=(hebrew_birthdate or {}).get("day"),
                    hebrew_month=(hebrew_birthdate or {}).get("month"),
                    hebrew_year=(hebrew_birthdate or {}).get("year"),
                ),
            }

        return {
            "full_name": full_name,
            "name_analysis": name_analysis,
            "missing_info": missing_info,
            "birthdate_analysis": birthdate_analysis,
        }
