"""
Validator for Level 2 formula extraction JSON outputs.
Schema version: 1.0
"""

import argparse
import json
import sys
from typing import Any

VALID_CONFIDENCE = {"low", "medium", "high"}
REQUIRED_TOP_LEVEL = [
    "schema_version",
    "source_file",
    "formula_id",
    "label_he",
    "formula_type",
    "source_direct_rule",
    "derived_rule",
    "inputs",
    "calculation_steps",
    "test_cases",
    "missing_or_unclear",
    "formula_confidence",
]
REQUIRED_INPUT_FIELDS = {"name", "type", "label_he", "required"}
REQUIRED_STEP_FIELDS = {"step_number", "description_he"}
REQUIRED_TEST_FIELDS = {"input", "expected_output", "source_provided"}


class ValidationError(Exception):
    pass


class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def strip_markdown_fences(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


def parse_json(raw: str) -> Any:
    cleaned = strip_markdown_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"JSON לא תקין: {exc}") from exc


def validate_top_level(data: dict, result: ValidationResult) -> None:
    for field in REQUIRED_TOP_LEVEL:
        if field not in data:
            result.error(f"שדה חסר ברמה העליונה: '{field}'")


def validate_formula_id(data: dict, expected_id: str | None, result: ValidationResult) -> None:
    fid = data.get("formula_id", "")
    if not isinstance(fid, str) or not fid.strip():
        result.error("'formula_id' חייב להיות מחרוזת לא ריקה")
        return
    if expected_id and fid != expected_id:
        result.error(f"'formula_id' לא תואם: נמצא '{fid}', צפוי '{expected_id}'")


def validate_source_direct_rule(data: dict, result: ValidationResult) -> None:
    sdr = data.get("source_direct_rule")
    if not isinstance(sdr, dict):
        result.error("'source_direct_rule' חייב להיות אובייקט")
        return
    for field in ("source_evidence", "calculation_shown"):
        val = sdr.get(field, "")
        if not isinstance(val, str) or not val.strip():
            result.error(f"'source_direct_rule.{field}' חייב להיות מחרוזת לא ריקה")


def validate_derived_rule(data: dict, result: ValidationResult) -> None:
    dr = data.get("derived_rule")
    if not isinstance(dr, dict):
        result.error("'derived_rule' חייב להיות אובייקט")
        return

    op = dr.get("operation", "")
    if not isinstance(op, str) or not op.strip():
        result.error("'derived_rule.operation' חייב להיות מחרוזת לא ריקה")

    conf = dr.get("derivation_confidence", "")
    if conf not in VALID_CONFIDENCE:
        result.error(
            f"'derived_rule.derivation_confidence' חייב להיות אחד מ: {', '.join(sorted(VALID_CONFIDENCE))}. נמצא: '{conf}'"
        )

    target = dr.get("target_range")
    if target is not None:
        if not (isinstance(target, list) and len(target) == 2 and all(isinstance(x, (int, float)) for x in target)):
            result.error("'derived_rule.target_range' חייב להיות רשימה של 2 מספרים")


def validate_inputs(data: dict, result: ValidationResult) -> None:
    inputs = data.get("inputs")
    if not isinstance(inputs, list) or len(inputs) == 0:
        result.error("'inputs' חייב להיות רשימה לא ריקה")
        return
    for i, inp in enumerate(inputs):
        if not isinstance(inp, dict):
            result.error(f"'inputs[{i}]' חייב להיות אובייקט")
            continue
        missing = REQUIRED_INPUT_FIELDS - inp.keys()
        for field in sorted(missing):
            result.error(f"'inputs[{i}]' חסר שדה: '{field}'")


def validate_calculation_steps(data: dict, result: ValidationResult) -> None:
    steps = data.get("calculation_steps")
    if not isinstance(steps, list) or len(steps) == 0:
        result.error("'calculation_steps' חייב להיות רשימה לא ריקה")
        return
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            result.error(f"'calculation_steps[{i}]' חייב להיות אובייקט")
            continue
        missing = REQUIRED_STEP_FIELDS - step.keys()
        for field in sorted(missing):
            result.error(f"'calculation_steps[{i}]' חסר שדה: '{field}'")


def validate_test_cases(data: dict, result: ValidationResult) -> None:
    cases = data.get("test_cases")
    if not isinstance(cases, list):
        result.error("'test_cases' חייב להיות רשימה")
        return

    source_provided_count = 0
    derived_count = 0

    for i, tc in enumerate(cases):
        if not isinstance(tc, dict):
            result.error(f"'test_cases[{i}]' חייב להיות אובייקט")
            continue

        missing = REQUIRED_TEST_FIELDS - tc.keys()
        for field in sorted(missing):
            result.error(f"'test_cases[{i}]' חסר שדה: '{field}'")

        sp = tc.get("source_provided")
        if sp is True:
            source_provided_count += 1
            evidence = tc.get("source_evidence", "")
            if not isinstance(evidence, str) or not evidence.strip():
                result.error(
                    f"'test_cases[{i}]' עם source_provided=true חייב לכלול 'source_evidence' לא ריק"
                )
        elif sp is False:
            derived_count += 1

    if source_provided_count < 1:
        result.error("'test_cases' חייב לכלול לפחות מקרה אחד עם source_provided=true")
    if derived_count < 2:
        result.error(
            f"'test_cases' חייב לכלול לפחות 2 מקרים עם source_provided=false (נמצאו {derived_count})"
        )


def validate_formula_confidence(data: dict, result: ValidationResult) -> None:
    fc = data.get("formula_confidence", "")
    if fc not in VALID_CONFIDENCE:
        result.error(
            f"'formula_confidence' חייב להיות אחד מ: {', '.join(sorted(VALID_CONFIDENCE))}. נמצא: '{fc}'"
        )
        return

    if fc == "high":
        dr = data.get("derived_rule", {})
        op = dr.get("operation", "").lower() if isinstance(dr, dict) else ""
        inferred_keywords = ("infer", "derive", "estimated", "assumed", "unclear")
        if any(kw in op for kw in inferred_keywords):
            result.warn(
                "'formula_confidence' הוגדר כ-high אך 'derived_rule.operation' מכיל רמז לנגזרת/הסקה"
            )
        desc = dr.get("description_he", "").lower() if isinstance(dr, dict) else ""
        if any(kw in desc for kw in inferred_keywords):
            result.warn(
                "'formula_confidence' הוגדר כ-high אך 'derived_rule.description_he' מכיל רמז לנגזרת/הסקה"
            )


def validate(data: dict, expected_id: str | None, result: ValidationResult) -> None:
    validate_top_level(data, result)
    validate_formula_id(data, expected_id, result)
    validate_source_direct_rule(data, result)
    validate_derived_rule(data, result)
    validate_inputs(data, result)
    validate_calculation_steps(data, result)
    validate_test_cases(data, result)
    validate_formula_confidence(data, result)


def run(args: argparse.Namespace) -> int:
    try:
        raw = args.input.read()
    except OSError as exc:
        print(f"שגיאה בקריאת הקובץ: {exc}", file=sys.stderr)
        return 2

    result = ValidationResult()

    try:
        data = parse_json(raw)
    except ValidationError as exc:
        print(f"[שגיאה] {exc}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print("[שגיאה] JSON חייב להיות אובייקט ברמה העליונה", file=sys.stderr)
        return 1

    validate(data, args.expected_formula_id, result)

    for msg in result.warnings:
        print(f"[אזהרה] {msg}")

    if result.ok:
        print("[תקין] הולידציה עברה בהצלחה.")
        return 0
    else:
        for msg in result.errors:
            print(f"[שגיאה] {msg}", file=sys.stderr)
        if args.strict:
            print(f"\nנמצאו {len(result.errors)} שגיאות. עצירה במצב --strict.", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ולידטור לפלט חילוץ נוסחאות Level 2 (numerology formula extraction JSON).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
דוגמאות שימוש:
  py -3.12 validate_formula_extraction.py --input output.json
  py -3.12 validate_formula_extraction.py --input output.json --expected-formula-id house_number_basic
  py -3.12 validate_formula_extraction.py --input output.json --strict
  cat output.json | py -3.12 validate_formula_extraction.py --input -
""",
    )
    parser.add_argument(
        "--input",
        metavar="FILE",
        type=argparse.FileType("r", encoding="utf-8"),
        default="-",
        help="נתיב לקובץ JSON לבדיקה (ברירת מחדל: stdin)",
    )
    parser.add_argument(
        "--expected-formula-id",
        metavar="ID",
        default=None,
        help="אם סופק, formula_id חייב להתאים לערך זה בדיוק",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="החזר קוד יציאה שאינו אפס אפילו על אזהרות (לא פועל כרגע — שגיאות תמיד מחזירות 1)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
