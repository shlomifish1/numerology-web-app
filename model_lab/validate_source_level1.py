"""
Validator for Level 1 — General Source Understanding.
Schema version: 1.0

Works for any numerology source file.
Does NOT require interpretation text (that is Level 3).
"""

import argparse
import json
import re
import sys
from typing import Any

VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_CONTENT_TYPES = {"formula_only", "interpretations_only", "mixed", "unclear"}

REQUIRED_TOP_LEVEL = [
    "schema_version",
    "level",
    "source_file",
    "source_topic",
    "content_type",
    "formulas_found",
    "interpretation_groups_found",
    "calculator_readiness",
    "missing_or_unclear",
    "level1_confidence",
]

REQUIRED_FORMULA_FIELDS = {
    "formula_candidate_id",
    "description_he",
    "source_evidence",
    "inputs_mentioned",
    "outputs_mentioned",
    "has_example",
    "example_raw",
    "confidence",
}

REQUIRED_GROUP_FIELDS = {
    "group_id",
    "description_he",
    "has_verbatim_content",
    "estimated_entry_count",
}

REQUIRED_READINESS_FIELDS = {
    "has_formulas",
    "has_test_cases_in_source",
    "has_lookup_table",
    "ready_for_level2",
    "ready_for_level3",
    "blockers",
}

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")

SOURCE_EVIDENCE_MIN = 10
SOURCE_EVIDENCE_MAX = 600


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


def parse_json(raw: str, result: ValidationResult) -> dict | None:
    cleaned = strip_markdown_fences(raw)
    if cleaned != raw.strip():
        result.warn("גדרת markdown זוהתה והוסרה לפני פירוס")
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        result.error(f"JSON לא תקין: {exc}")
        return None
    if not isinstance(data, dict):
        result.error(f"JSON חייב להיות אובייקט ברמה העליונה — נמצא: {type(data).__name__}")
        return None
    return data


def validate_top_level(data: dict, result: ValidationResult) -> None:
    for field in REQUIRED_TOP_LEVEL:
        if field not in data:
            result.error(f"שדה חסר ברמה העליונה: '{field}'")


def validate_level(data: dict, result: ValidationResult) -> None:
    lv = data.get("level")
    if lv is None:
        return  # נתפס ב-top_level
    if not isinstance(lv, int) or isinstance(lv, bool):
        result.error(f"'level' חייב להיות מספר שלם (int) — נמצא: {type(lv).__name__} {lv!r}")
        return
    if lv != 1:
        result.error(f"'level' חייב להיות 1 — נמצא: {lv}")


def validate_content_type(data: dict, result: ValidationResult) -> None:
    ct = data.get("content_type")
    if ct is None:
        return
    if ct not in VALID_CONTENT_TYPES:
        result.error(
            f"'content_type' לא חוקי: '{ct}' — מותר: {', '.join(sorted(VALID_CONTENT_TYPES))}"
        )


def validate_formulas(data: dict, result: ValidationResult) -> int:
    """מחזיר את מספר הנוסחאות שנמצאו."""
    formulas = data.get("formulas_found")
    if formulas is None:
        return 0
    if not isinstance(formulas, list):
        result.error("'formulas_found' חייב להיות רשימה (list)")
        return 0

    for i, f in enumerate(formulas):
        if not isinstance(f, dict):
            result.error(f"'formulas_found[{i}]' חייב להיות אובייקט")
            continue

        missing = REQUIRED_FORMULA_FIELDS - f.keys()
        for field in sorted(missing):
            result.error(f"'formulas_found[{i}]' חסר שדה: '{field}'")

        fid = f.get("formula_candidate_id", "")
        if isinstance(fid, str) and fid.strip():
            if not _SNAKE_CASE_RE.match(fid):
                result.warn(
                    f"'formulas_found[{i}].formula_candidate_id' אינו snake_case: '{fid}'"
                )
        elif "formula_candidate_id" in f:
            result.error(f"'formulas_found[{i}].formula_candidate_id' חייב להיות מחרוזת לא ריקה")

        for text_field in ("description_he", "source_evidence"):
            val = f.get(text_field)
            if val is not None and (not isinstance(val, str) or not val.strip()):
                result.error(f"'formulas_found[{i}].{text_field}' חייב להיות מחרוזת לא ריקה")

        ev = f.get("source_evidence", "")
        if isinstance(ev, str):
            if 0 < len(ev) < SOURCE_EVIDENCE_MIN:
                result.warn(
                    f"'formulas_found[{i}].source_evidence' קצר מדי ({len(ev)} תווים) — "
                    "ייתכן שאינו ציטוט ממשי"
                )
            elif len(ev) > SOURCE_EVIDENCE_MAX:
                result.warn(
                    f"'formulas_found[{i}].source_evidence' ארוך מדי ({len(ev)} תווים) — "
                    "שקול לפצל"
                )

        conf = f.get("confidence")
        if conf is not None and conf not in VALID_CONFIDENCE:
            result.error(
                f"'formulas_found[{i}].confidence' לא חוקי: '{conf}' — "
                f"מותר: {', '.join(sorted(VALID_CONFIDENCE))}"
            )

        has_ex = f.get("has_example")
        if has_ex is not None:
            if not isinstance(has_ex, bool):
                result.error(
                    f"'formulas_found[{i}].has_example' חייב להיות boolean — נמצא: {type(has_ex).__name__}"
                )
            elif has_ex is True:
                ex_raw = f.get("example_raw")
                if not isinstance(ex_raw, str) or not ex_raw.strip():
                    result.error(
                        f"'formulas_found[{i}].example_raw' חייב להיות מחרוזת לא ריקה כש-has_example=true"
                    )

        for list_field in ("inputs_mentioned", "outputs_mentioned"):
            val = f.get(list_field)
            if val is not None and not isinstance(val, list):
                result.error(
                    f"'formulas_found[{i}].{list_field}' חייב להיות רשימה — "
                    f"נמצא: {type(val).__name__}"
                )

    return len(formulas)


def validate_interpretation_groups(data: dict, result: ValidationResult) -> int:
    """מחזיר את מספר הקבוצות שנמצאו."""
    groups = data.get("interpretation_groups_found")
    if groups is None:
        return 0
    if not isinstance(groups, list):
        result.error("'interpretation_groups_found' חייב להיות רשימה (list)")
        return 0

    for i, g in enumerate(groups):
        if not isinstance(g, dict):
            result.error(f"'interpretation_groups_found[{i}]' חייב להיות אובייקט")
            continue

        missing = REQUIRED_GROUP_FIELDS - g.keys()
        for field in sorted(missing):
            result.error(f"'interpretation_groups_found[{i}]' חסר שדה: '{field}'")

        for text_field in ("group_id", "description_he"):
            val = g.get(text_field)
            if val is not None and (not isinstance(val, str) or not val.strip()):
                result.error(
                    f"'interpretation_groups_found[{i}].{text_field}' חייב להיות מחרוזת לא ריקה"
                )

        hvb = g.get("has_verbatim_content")
        if hvb is not None and not isinstance(hvb, bool):
            result.error(
                f"'interpretation_groups_found[{i}].has_verbatim_content' חייב להיות boolean"
            )

        ec = g.get("estimated_entry_count")
        if ec is not None:
            if not isinstance(ec, int) or isinstance(ec, bool) or ec < 0:
                result.error(
                    f"'interpretation_groups_found[{i}].estimated_entry_count' "
                    "חייב להיות int לא שלילי"
                )

    return len(groups)


def validate_calculator_readiness(
    data: dict,
    formula_count: int,
    group_count: int,
    result: ValidationResult,
) -> None:
    cr = data.get("calculator_readiness")
    if cr is None:
        return
    if not isinstance(cr, dict):
        result.error("'calculator_readiness' חייב להיות אובייקט")
        return

    missing = REQUIRED_READINESS_FIELDS - cr.keys()
    for field in sorted(missing):
        result.error(f"'calculator_readiness' חסר שדה: '{field}'")

    for bool_field in (
        "has_formulas",
        "has_test_cases_in_source",
        "has_lookup_table",
        "ready_for_level2",
        "ready_for_level3",
    ):
        val = cr.get(bool_field)
        if val is not None and not isinstance(val, bool):
            result.error(
                f"'calculator_readiness.{bool_field}' חייב להיות boolean — נמצא: {type(val).__name__}"
            )

    blockers = cr.get("blockers")
    if blockers is not None and not isinstance(blockers, list):
        result.error("'calculator_readiness.blockers' חייב להיות רשימה (list)")

    # cross-checks
    if cr.get("ready_for_level2") is True and formula_count == 0:
        result.error(
            "'calculator_readiness.ready_for_level2=true' אך 'formulas_found' ריקה — סתירה"
        )

    if cr.get("ready_for_level3") is True and group_count == 0:
        result.error(
            "'calculator_readiness.ready_for_level3=true' אך 'interpretation_groups_found' ריקה — סתירה"
        )


def validate_level1_confidence(data: dict, result: ValidationResult) -> None:
    lc = data.get("level1_confidence")
    if lc is None:
        return
    if lc not in VALID_CONFIDENCE:
        result.error(
            f"'level1_confidence' לא חוקי: '{lc}' — מותר: {', '.join(sorted(VALID_CONFIDENCE))}"
        )


def validate_missing_or_unclear(data: dict, result: ValidationResult) -> None:
    mou = data.get("missing_or_unclear")
    if mou is None:
        return
    if not isinstance(mou, list):
        result.error("'missing_or_unclear' חייב להיות רשימה (list)")


def validate_content_type_consistency(
    data: dict,
    formula_count: int,
    group_count: int,
    result: ValidationResult,
) -> None:
    ct = data.get("content_type")
    if ct is None:
        return
    if ct == "formula_only" and group_count > 0:
        result.warn(
            f"content_type='formula_only' אך נמצאו {group_count} קבוצות פרשנות — שקול 'mixed'"
        )
    if ct == "interpretations_only" and formula_count > 0:
        result.warn(
            f"content_type='interpretations_only' אך נמצאו {formula_count} נוסחאות — שקול 'mixed'"
        )
    if ct == "unclear" and (formula_count > 0 or group_count > 0):
        result.warn(
            "content_type='unclear' אך זוהו נוסחאות/קבוצות — שקול לעדכן content_type"
        )


def run(args: argparse.Namespace) -> int:
    try:
        raw = args.input.read()
    except OSError as exc:
        print(f"שגיאה בקריאת הקובץ: {exc}", file=sys.stderr)
        return 2

    result = ValidationResult()

    data = parse_json(raw, result)
    if data is None:
        for msg in result.errors:
            print(f"[שגיאה] {msg}", file=sys.stderr)
        return 1

    validate_top_level(data, result)
    validate_level(data, result)
    validate_content_type(data, result)

    formula_count = validate_formulas(data, result)
    group_count = validate_interpretation_groups(data, result)

    validate_calculator_readiness(data, formula_count, group_count, result)
    validate_level1_confidence(data, result)
    validate_missing_or_unclear(data, result)
    validate_content_type_consistency(data, formula_count, group_count, result)

    if args.strict:
        sv = data.get("schema_version")
        if not isinstance(sv, str) or not sv.strip():
            result.error("'schema_version' חייב להיות מחרוזת לא ריקה [strict]")
        if "source_author" not in data:
            result.warn("'source_author' חסר (אופציונלי) [strict]")

    for msg in result.warnings:
        print(f"[אזהרה] {msg}")

    if result.ok:
        formula_ids = [
            f.get("formula_candidate_id", "?")
            for f in (data.get("formulas_found") or [])
            if isinstance(f, dict)
        ]
        group_ids = [
            g.get("group_id", "?")
            for g in (data.get("interpretation_groups_found") or [])
            if isinstance(g, dict)
        ]
        print("[תקין] Level 1 — ולידציה עברה בהצלחה.")
        print(f"  source_topic   : {data.get('source_topic', '—')}")
        print(f"  content_type   : {data.get('content_type', '—')}")
        print(f"  נוסחאות        : {formula_count}  → {formula_ids}")
        print(f"  קבוצות פרשנות : {group_count}  → {group_ids}")
        print(f"  level1_confidence: {data.get('level1_confidence', '—')}")
        return 0
    else:
        for msg in result.errors:
            print(f"[שגיאה] {msg}", file=sys.stderr)
        print(f"\nנמצאו {len(result.errors)} שגיאות קריטיות.", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ולידטור Level 1 — General Source Understanding (נומרולוגיה).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
דוגמאות שימוש:
  py -3.12 validate_source_level1.py --input output.json
  py -3.12 validate_source_level1.py --input output.json --strict
  cat output.json | py -3.12 validate_source_level1.py --input -
""",
    )
    parser.add_argument(
        "--input",
        metavar="FILE",
        type=argparse.FileType("r", encoding="utf-8-sig"),
        default="-",
        help="נתיב לקובץ JSON לבדיקה (ברירת מחדל: stdin)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="בדוק גם schema_version ו-source_author",
    )
    return parser


def main() -> None:
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = build_parser()
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
