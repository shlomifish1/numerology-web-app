"""
validate_extraction_json.py
---------------------------
מאמת פלטי JSON שהופקו על-ידי מודלים מקומיים (Ollama) עבור ספר "מספרי בית".
שימוש בספריות Python סטנדרטיות בלבד.

סכמה צפויה (top-level):
  source_file, topic, number, interpretation, blessing_conditions,
  timing_notes, calculator_rules_from_document, missing_or_unclear, confidence
  tip (אופציונלי, מנוטר)

Exit codes:
  0 = עבר (אין שגיאות קריטיות)
  1 = נכשל (יש שגיאות קריטיות)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# קבועים
# ---------------------------------------------------------------------------

REQUIRED_TOP_LEVEL = [
    "source_file",
    "topic",
    "number",
    "interpretation",
    "blessing_conditions",
    "timing_notes",
    "calculator_rules_from_document",
    "missing_or_unclear",
    "confidence",
]

OPTIONAL_TOP_LEVEL = ["tip"]

KNOWN_TOP_LEVEL = set(REQUIRED_TOP_LEVEL + OPTIONAL_TOP_LEVEL)

INTERPRETATION_LIST_FIELDS = [
    "suitable_for",
    "strengths",
    "warnings",
    "risk_if_unbalanced",
]

BLESSING_LIST_FIELDS = ["lost_when", "returns_when"]

TIMING_FIELDS = ["decade_note", "annual_frequency_example"]

ANNUAL_FREQ_FIELDS = ["year", "year_reduced", "house_number", "result_frequency", "meaning"]

CALC_RULES_FIELDS = [
    "apartment_number_rule",
    "address_plus_apartment_rule",
    "annual_frequency_rule",
    "weights",
]

WEIGHT_FIELDS = ["apartment", "building", "floor"]

CONFIDENCE_VALUES = {"low", "medium", "high"}

# שדות האסורים בקינון בתוך interpretation
FORBIDDEN_IN_INTERPRETATION = [
    "blessing_conditions",
    "timing_notes",
    "calculator_rules_from_document",
]

# תיקיית שמירה בטוחה (נסלל מהסקריפט עצמו)
MODEL_OUTPUTS_ROOT = Path(__file__).parent / "model_outputs"


# ---------------------------------------------------------------------------
# עזרים
# ---------------------------------------------------------------------------

def strip_markdown_fence(text: str) -> str:
    """מסיר גדר markdown אם קיימת, ומחזיר JSON נקי."""
    text = text.strip()
    # ```json ... ``` או ``` ... ```
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # גדר פותחת בלי סוגרת
    match = re.search(r"```(?:json)?\s*(.*)", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip().rstrip("`").strip()
        if candidate.startswith("{"):
            return candidate
    return text


def normalize_weight(value) -> float | None:
    """ממיר ערך משקל (int/float/str/"80%"/null) ל-float או None."""
    if value is None:
        return None
    s = str(value).strip().rstrip("%").strip()
    try:
        return float(s)
    except ValueError:
        return None


def sanitize_filename_part(name: str) -> str:
    """מסיר תווים מסוכנים משם קובץ."""
    name = name.strip()
    name = re.sub(r"[\\/:*?\"<>|.]{1,}", "_", name)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_") or "unknown"


# ---------------------------------------------------------------------------
# מחלקת תוצאת ולידציה
# ---------------------------------------------------------------------------

class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[str] = []    # שגיאות קריטיות — גורמות ל-exit 1
        self.warnings: list[str] = []  # אזהרות — מודפסות, לא גורמות לכישלון

    def error(self, rule: str, msg: str) -> None:
        self.errors.append(f"  [!] {rule}: {msg}")

    def warn(self, rule: str, msg: str) -> None:
        self.warnings.append(f"  [w] {rule}: {msg}")

    def ok(self, msg: str) -> None:
        print(f"  [v] {msg}")

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# פונקציות ולידציה
# ---------------------------------------------------------------------------

def validate_parseable(raw: str) -> tuple[dict | None, ValidationResult]:
    """כלל 1+2: JSON ניתן לפירוס, גדרות markdown מסוננות."""
    result = ValidationResult()
    cleaned = strip_markdown_fence(raw)
    if cleaned != raw.strip():
        result.warn("כלל 2", "הוסרה גדרת markdown מהפלט לפני פירוס")
    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            result.error("כלל 1", f"הפלט הוא {type(data).__name__} ולא object/dict")
            return None, result
        return data, result
    except json.JSONDecodeError as exc:
        result.error("כלל 1", f"JSON לא ניתן לפירוס: {exc}")
        return None, result


def validate_top_level_fields(data: dict, result: ValidationResult, strict: bool) -> None:
    """כלל 2: שדות עליונים נדרשים קיימים."""
    for field in REQUIRED_TOP_LEVEL:
        if field not in data:
            result.error("כלל 2", f"שדה חסר ברמה העליונה: '{field}'")

    # לגלות שגיאת שם נפוצה: house_number במקום number
    if "house_number" in data and "number" not in data:
        result.error("כלל 2", "נמצא 'house_number' — השדה הנכון הוא 'number'")

    # אופציונלי — מנוטר
    if "tip" not in data:
        result.warn("כלל 2", "'tip' חסר (אופציונלי, לא חולץ)")

    # strict: שדות עליונים לא מוכרים
    if strict:
        unknown = set(data.keys()) - KNOWN_TOP_LEVEL
        if unknown:
            result.warn("strict", f"שדות עליונים לא מוכרים: {sorted(unknown)}")


def validate_number(data: dict, expected: int | None, result: ValidationResult) -> None:
    """כלל 3+4: number הוא int 1-9 ותואם ל--expected-number."""
    raw_number = data.get("number")

    if raw_number is None:
        # כבר נתפס בכלל 2
        return

    if not isinstance(raw_number, int) or isinstance(raw_number, bool):
        result.error("כלל 3", f"'number' חייב להיות int — קיבלנו {type(raw_number).__name__}: {raw_number!r}")
        return

    if not (1 <= raw_number <= 9):
        result.error("כלל 3", f"'number' = {raw_number} — חייב להיות בטווח 1–9")
        return

    result.ok(f"number = {raw_number} (int תקין, טווח 1–9)")

    if expected is not None:
        if raw_number != expected:
            result.error("כלל 4", f"number = {raw_number}, אך --expected-number = {expected}")
        else:
            result.ok(f"number תואם --expected-number ({expected})")


def validate_confidence(data: dict, result: ValidationResult) -> None:
    """כלל 5: confidence הוא בדיוק low / medium / high."""
    confidence = data.get("confidence")
    if confidence is None:
        return  # כבר נתפס בכלל 2
    if confidence not in CONFIDENCE_VALUES:
        result.error("כלל 5", f"confidence = {confidence!r} — מותר רק: low / medium / high")
    else:
        result.ok(f"confidence = {confidence!r}")


def validate_interpretation(data: dict, result: ValidationResult) -> None:
    """כלל 6: interpretation הוא dict עם list fields."""
    interp = data.get("interpretation")
    if interp is None:
        return  # כבר נתפס בכלל 2

    if not isinstance(interp, dict):
        result.error("כלל 6", f"'interpretation' חייב להיות dict — קיבלנו {type(interp).__name__}")
        return

    for field in INTERPRETATION_LIST_FIELDS:
        if field not in interp:
            result.error("כלל 6", f"interpretation חסר שדה: '{field}'")
        elif not isinstance(interp[field], list):
            result.error(
                "כלל 6",
                f"interpretation.{field} חייב להיות list — קיבלנו {type(interp[field]).__name__}"
            )
        else:
            result.ok(f"interpretation.{field} ✓ (list)")


def validate_forbidden_nesting(data: dict, result: ValidationResult) -> None:
    """כלל 11: שדות אסורים לא מופיעים בתוך interpretation."""
    interp = data.get("interpretation")
    if not isinstance(interp, dict):
        return
    for forbidden in FORBIDDEN_IN_INTERPRETATION:
        if forbidden in interp:
            result.error(
                "כלל 11",
                f"'{forbidden}' נמצא בתוך interpretation — חייב להיות ברמה עליונה בלבד"
            )


def validate_blessing_conditions(data: dict, result: ValidationResult) -> None:
    """כלל 7: blessing_conditions ברמה עליונה עם list fields."""
    bc = data.get("blessing_conditions")
    if bc is None:
        return  # כבר נתפס בכלל 2

    if not isinstance(bc, dict):
        result.error("כלל 7", f"'blessing_conditions' חייב להיות dict — קיבלנו {type(bc).__name__}")
        return

    for field in BLESSING_LIST_FIELDS:
        if field not in bc:
            result.error("כלל 7", f"blessing_conditions חסר שדה: '{field}'")
        elif not isinstance(bc[field], list):
            result.error(
                "כלל 7",
                f"blessing_conditions.{field} חייב להיות list — קיבלנו {type(bc[field]).__name__}"
            )
        else:
            result.ok(f"blessing_conditions.{field} ✓ (list)")


def validate_timing_notes(data: dict, result: ValidationResult) -> None:
    """כלל 8: timing_notes ברמה עליונה עם כל המפתחות הנדרשים."""
    tn = data.get("timing_notes")
    if tn is None:
        return

    if not isinstance(tn, dict):
        result.error("כלל 8", f"'timing_notes' חייב להיות dict — קיבלנו {type(tn).__name__}")
        return

    if "decade_note" not in tn:
        result.error("כלל 8", "timing_notes חסר 'decade_note'")
    else:
        result.ok("timing_notes.decade_note ✓")

    afe = tn.get("annual_frequency_example")
    if afe is None:
        result.error("כלל 8", "timing_notes חסר 'annual_frequency_example'")
        return

    if not isinstance(afe, dict):
        result.error("כלל 8", f"timing_notes.annual_frequency_example חייב להיות dict — קיבלנו {type(afe).__name__}")
        return

    for field in ANNUAL_FREQ_FIELDS:
        if field not in afe:
            result.error("כלל 8", f"timing_notes.annual_frequency_example חסר שדה: '{field}'")
        else:
            result.ok(f"timing_notes.annual_frequency_example.{field} ✓")


def validate_calculator_rules(data: dict, result: ValidationResult) -> None:
    """כלל 9+10: calculator_rules_from_document ברמה עליונה עם weights."""
    cr = data.get("calculator_rules_from_document")
    if cr is None:
        return

    if not isinstance(cr, dict):
        result.error("כלל 9", f"'calculator_rules_from_document' חייב להיות dict — קיבלנו {type(cr).__name__}")
        return

    for field in CALC_RULES_FIELDS:
        if field == "weights":
            continue  # נבדק בנפרד
        if field not in cr:
            result.error("כלל 9", f"calculator_rules_from_document חסר שדה: '{field}'")
        else:
            result.ok(f"calculator_rules_from_document.{field} ✓")

    # weights
    weights = cr.get("weights")
    if weights is None:
        result.error("כלל 10", "calculator_rules_from_document חסר 'weights'")
        return

    if not isinstance(weights, dict):
        result.error("כלל 10", f"'weights' חייב להיות dict — קיבלנו {type(weights).__name__}")
        return

    for field in WEIGHT_FIELDS:
        if field not in weights:
            result.error("כלל 10", f"weights חסר שדה: '{field}'")

    _validate_weights_sum(weights, result)


def _validate_weights_sum(weights: dict, result: ValidationResult) -> None:
    """בדיקת נרמול וסכום weights."""
    normalized = {}
    has_null = False

    for field in WEIGHT_FIELDS:
        raw = weights.get(field)
        val = normalize_weight(raw)
        if val is None:
            has_null = True
            result.warn("כלל 10", f"weights.{field} = null — לא ניתן לאמת סכום")
        else:
            normalized[field] = val

    if has_null:
        return  # אזהרה כבר הודפסה

    # כל שלושה קיימים ונרמלו בהצלחה
    total = sum(normalized.values())
    parts = ", ".join(f"{k}={v:g}" for k, v in normalized.items())
    if abs(total - 100) <= 1:
        result.ok(f"weights: {parts} — סכום {total:g} ✓")
    else:
        result.warn("כלל 10", f"weights: {parts} — סכום {total:g} ≠ 100 (צפוי 80+15+5=100)")


def validate_missing_or_unclear(data: dict, result: ValidationResult) -> None:
    """בדיקה בסיסית: missing_or_unclear הוא list."""
    mou = data.get("missing_or_unclear")
    if mou is None:
        return
    if not isinstance(mou, list):
        result.error("כלל 2", f"'missing_or_unclear' חייב להיות list — קיבלנו {type(mou).__name__}")
    else:
        result.ok(f"missing_or_unclear ✓ (list, {len(mou)} פריטים)")


# ---------------------------------------------------------------------------
# שמירה בטוחה
# ---------------------------------------------------------------------------

def build_output_path(data: dict, model: str, book: str) -> Path:
    """בונה נתיב שמירה בטוח."""
    number = data.get("number", "unknown")
    safe_model = sanitize_filename_part(model or "unknown_model")
    safe_book = sanitize_filename_part(book or "unknown_book")
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M")
    filename = f"house_{number}__{safe_model}__{timestamp}.json"
    return MODEL_OUTPUTS_ROOT / safe_book / filename


def save_output(data: dict, output_path: Path, result: ValidationResult) -> None:
    """שומר JSON לנתיב בטוח בלבד — לא דורס קובץ קיים."""
    resolved = output_path.resolve()
    root_resolved = MODEL_OUTPUTS_ROOT.resolve()

    # אבטחה: נתיב חייב להיות בתוך model_outputs
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        result.error("כלל 13", f"נתיב שמירה {resolved} נמצא מחוץ ל-model_outputs — שמירה נדחתה")
        return

    # לא דורסים קובץ קיים
    if resolved.exists():
        stem = resolved.stem
        suffix = resolved.suffix
        counter = 1
        while resolved.exists():
            resolved = resolved.parent / f"{stem}__dup{counter}{suffix}"
            counter += 1
        result.warn("כלל 15", f"קובץ קיים, נשמר תחת שם חדש: {resolved.name}")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    with open(resolved, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  [SAVED] {resolved}")


# ---------------------------------------------------------------------------
# תהליך ולידציה ראשי
# ---------------------------------------------------------------------------

def validate(
    raw: str,
    expected_number: int | None,
    strict: bool,
    save: bool,
    model: str,
    book: str,
) -> int:
    """מריץ את כל כללי הולידציה ומחזיר exit code."""

    # שלב 0: כותרת
    print()
    print("=" * 60)

    # כלל 1+2: פירוס JSON
    data, parse_result = validate_parseable(raw)

    if data is None:
        # שגיאה קריטית בפירוס — עצירה מיידית
        print("[FAIL] לא ניתן לפרס את ה-JSON")
        for err in parse_result.errors:
            print(err)
        for warn in parse_result.warnings:
            print(warn)
        print("=" * 60)
        return 1

    # צבירת כל תוצאות הולידציה לאובייקט אחד
    result = ValidationResult()
    # מעביר אזהרות פירוס
    for w in parse_result.warnings:
        result.warnings.append(w)

    number_display = data.get("number", "?")
    print(f"בודק: number={number_display}  |  confidence={data.get('confidence', '?')}")
    print("-" * 60)

    # כלל 2: שדות עליונים
    validate_top_level_fields(data, result, strict)

    # כלל 3+4: number
    validate_number(data, expected_number, result)

    # כלל 5: confidence
    validate_confidence(data, result)

    # כלל 6: interpretation + list fields
    validate_interpretation(data, result)

    # כלל 11: אין קינון אסור
    validate_forbidden_nesting(data, result)

    # כלל 7: blessing_conditions
    validate_blessing_conditions(data, result)

    # כלל 8: timing_notes
    validate_timing_notes(data, result)

    # כלל 9+10: calculator_rules_from_document + weights
    validate_calculator_rules(data, result)

    # missing_or_unclear
    validate_missing_or_unclear(data, result)

    # ---------------------------------------------------------------------------
    # הדפסת שגיאות ואזהרות
    # ---------------------------------------------------------------------------
    print()
    if result.errors:
        for err in result.errors:
            print(err)
    if result.warnings:
        for warn in result.warnings:
            print(warn)

    print()
    error_count = len(result.errors)
    warning_count = len(result.warnings)
    summary_parts = []
    if error_count:
        summary_parts.append(f"{error_count} שגיאות קריטיות")
    if warning_count:
        summary_parts.append(f"{warning_count} אזהרות")

    if result.passed:
        print(f"[PASS] ✓  {' | '.join(summary_parts) or 'ללא שגיאות וללא אזהרות'}")
        if save:
            out_path = build_output_path(data, model, book)
            save_output(data, out_path, result)
    else:
        print(f"[FAIL] ✗  {' | '.join(summary_parts)}")
        print("לא נשמר.")

    print("=" * 60)
    return 0 if result.passed else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_extraction_json",
        description=(
            "מאמת פלטי JSON ממודלים מקומיים עבור ספר 'מספרי בית'.\n"
            "משתמש בסכמה הצפויה של ה-model lab בלבד."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "דוגמאות שימוש:\n"
            "  py -3.12 validate_extraction_json.py --input house_1.json\n"
            "  py -3.12 validate_extraction_json.py --input house_1.json --expected-number 1\n"
            "  py -3.12 validate_extraction_json.py --input house_1.json --expected-number 1 "
            "--save --model gemma4_e4b --book מספרי_בית\n"
            "  py -3.12 validate_extraction_json.py --input house_1.json --strict\n"
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="FILE",
        help="קובץ JSON קלט לבדיקה (פלט של מודל)",
    )
    parser.add_argument(
        "--expected-number",
        type=int,
        metavar="N",
        help="מספר בית צפוי (1–9). אם הועבר, number ב-JSON חייב להתאים.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="שמור את ה-JSON ב-model_outputs אם עבר ולידציה (חובה גם --model ו--book)",
    )
    parser.add_argument(
        "--model",
        default="unknown_model",
        metavar="NAME",
        help="שם המודל לשם הקובץ השמור (למשל: gemma4_e4b)",
    )
    parser.add_argument(
        "--book",
        default="unknown_book",
        metavar="NAME",
        help="שם הספר לתיקיית שמירה (למשל: מספרי_בית)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="אזהרה על שדות עליונים לא-מוכרים",
    )
    return parser


def main() -> None:
    # מאפשר פלט UTF-8 בטרמינל Windows (Python 3.7+)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"שגיאה: קובץ לא נמצא: {input_path}", file=sys.stderr)
        sys.exit(1)

    if not input_path.is_file():
        print(f"שגיאה: הנתיב אינו קובץ: {input_path}", file=sys.stderr)
        sys.exit(1)

    # קריאה לקריאה בלבד — utf-8-sig מטפל אוטומטית ב-BOM אם קיים
    raw = input_path.read_text(encoding="utf-8-sig")

    exit_code = validate(
        raw=raw,
        expected_number=args.expected_number,
        strict=args.strict,
        save=args.save,
        model=args.model,
        book=args.book,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
