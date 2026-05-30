"""
Validator for Book Intake Analyzer — book_intake_profile.json
Schema version: intake/1.0

Validates a draft book_intake_profile.json produced by the Book Intake Analyzer.
No model calls. No API calls. No OCR. No file writes.
"""

import argparse
import json
import sys

REQUIRED_TOP_LEVEL = [
    "$schema_version",
    "book_id",
    "book_title",
    "intake_status",
    "intake_generated_at",
    "intake_generated_by",
    "corpus_source",
    "corpus_quality",
    "safety_flags",
]

REQUIRED_SAFETY_FLAGS = [
    "corpus_empty",
    "corpus_low_quality",
    "model_hallucination_risk",
    "manual_review_required",
    "blocked_from_definition_write",
    "blocked_from_runtime_promote",
]

REQUIRED_CORPUS_QUALITY_FIELDS = ["total_chars", "extraction_method"]

VALID_INTAKE_STATUSES = {"draft", "validated", "approved", "rejected"}
VALID_EXTRACTION_METHODS = {"fitz-native-full", "ocr", "ocr_pending", "unknown"}

LOW_QUALITY_CHARS_THRESHOLD = 500
LOW_QUALITY_HEBREW_RATIO = 0.15


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

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


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


def validate_intake_status(data: dict, result: ValidationResult) -> None:
    """S1: model output is always a draft."""
    status = data.get("intake_status")
    if status is None:
        return
    if status not in VALID_INTAKE_STATUSES:
        result.error(
            f"'intake_status' לא חוקי: '{status}' — "
            f"מותר: {', '.join(sorted(VALID_INTAKE_STATUSES))}"
        )
    elif status != "draft":
        result.error(
            f"'intake_status' חייב להיות 'draft' בפלט מודל (S1) — נמצא: '{status}'"
        )


def validate_safety_flags(
    data: dict,
    result: ValidationResult,
) -> dict | None:
    """Validates all 6 mandatory safety flags and their invariants."""
    flags = data.get("safety_flags")
    if flags is None:
        return None
    if not isinstance(flags, dict):
        result.error("'safety_flags' חייב להיות אובייקט")
        return None

    for field in REQUIRED_SAFETY_FLAGS:
        if field not in flags:
            result.error(f"'safety_flags.{field}' חסר — כל 6 הדגלים חובה")
        elif not isinstance(flags[field], bool):
            result.error(
                f"'safety_flags.{field}' חייב להיות boolean — "
                f"נמצא: {type(flags[field]).__name__}"
            )

    # Invariants that can never be false at model output
    if flags.get("manual_review_required") is False:
        result.error(
            "'safety_flags.manual_review_required' חייב תמיד להיות true — "
            "לא ניתן לסמן false על ידי מודל (S4)"
        )
    if flags.get("blocked_from_runtime_promote") is False:
        result.error(
            "'safety_flags.blocked_from_runtime_promote' חייב תמיד להיות true בפלט מודל — "
            "רק בן אדם יכול לשנות זאת ב-learning_profile.json (S5)"
        )

    return flags


def validate_corpus_quality(
    data: dict,
    flags: dict | None,
    result: ValidationResult,
) -> None:
    """Validates corpus_quality fields and cross-checks against safety_flags."""
    cq = data.get("corpus_quality")
    if cq is None:
        return
    if not isinstance(cq, dict):
        result.error("'corpus_quality' חייב להיות אובייקט")
        return

    for field in REQUIRED_CORPUS_QUALITY_FIELDS:
        if field not in cq:
            result.error(f"'corpus_quality.{field}' חסר")

    total_chars = cq.get("total_chars")
    extraction_method = cq.get("extraction_method")
    hebrew_ratio = cq.get("estimated_hebrew_ratio")

    # total_chars type check
    if total_chars is not None:
        if not isinstance(total_chars, int) or isinstance(total_chars, bool) or total_chars < 0:
            result.error(
                "'corpus_quality.total_chars' חייב להיות int לא שלילי — "
                f"נמצא: {total_chars!r}"
            )
            total_chars = None

    # extraction_method enum check
    if extraction_method is not None and extraction_method not in VALID_EXTRACTION_METHODS:
        result.error(
            f"'corpus_quality.extraction_method' לא חוקי: '{extraction_method}' — "
            f"מותר: {', '.join(sorted(VALID_EXTRACTION_METHODS))}"
        )

    # hebrew_ratio type check
    if hebrew_ratio is not None:
        if not isinstance(hebrew_ratio, (int, float)) or isinstance(hebrew_ratio, bool):
            result.error(
                "'corpus_quality.estimated_hebrew_ratio' חייב להיות float 0–1 או null — "
                f"נמצא: {hebrew_ratio!r}"
            )
            hebrew_ratio = None
        elif not (0.0 <= hebrew_ratio <= 1.0):
            result.error(
                f"'corpus_quality.estimated_hebrew_ratio' מחוץ לטווח 0–1: {hebrew_ratio}"
            )
            hebrew_ratio = None

    if flags is None:
        return

    # Derive expected flag states from corpus_quality values
    corpus_empty_expected = isinstance(total_chars, int) and total_chars == 0
    corpus_low_quality_expected = (
        (isinstance(total_chars, int) and 0 < total_chars < LOW_QUALITY_CHARS_THRESHOLD)
        or extraction_method == "ocr_pending"
        or (hebrew_ratio is not None and hebrew_ratio < LOW_QUALITY_HEBREW_RATIO)
    )
    block_expected = corpus_empty_expected or corpus_low_quality_expected

    if corpus_empty_expected and flags.get("corpus_empty") is not True:
        result.error(
            f"'corpus_quality.total_chars={total_chars}' → "
            "'safety_flags.corpus_empty' חייב להיות true (S6)"
        )

    if corpus_low_quality_expected and flags.get("corpus_low_quality") is not True:
        result.error(
            "corpus נמוך-איכות זוהה → 'safety_flags.corpus_low_quality' חייב להיות true (S6)"
        )

    if block_expected and flags.get("blocked_from_definition_write") is not True:
        result.error(
            "corpus ריק/נמוך-איכות → "
            "'safety_flags.blocked_from_definition_write' חייב להיות true (S6)"
        )

    # Warn if hallucination risk flag seems inconsistent
    if (
        corpus_low_quality_expected
        and flags.get("model_hallucination_risk") is False
    ):
        result.warn(
            "corpus נמוך-איכות אך 'safety_flags.model_hallucination_risk=false' — "
            "שקול לסמן true"
        )


def validate_suggested_definition_updates(data: dict, result: ValidationResult) -> None:
    """S3+S4: every suggested_definition_updates item must be draft-only and human-approved."""
    updates = data.get("suggested_definition_updates")
    if updates is None:
        return
    if not isinstance(updates, list):
        result.error("'suggested_definition_updates' חייב להיות רשימה (list)")
        return

    for i, item in enumerate(updates):
        if not isinstance(item, dict):
            result.error(f"'suggested_definition_updates[{i}]' חייב להיות אובייקט")
            continue

        if item.get("model_draft_only") is not True:
            result.error(
                f"'suggested_definition_updates[{i}].model_draft_only' חייב להיות true (S3)"
            )

        if item.get("requires_human_approval") is not True:
            result.error(
                f"'suggested_definition_updates[{i}].requires_human_approval' חייב להיות true (S4)"
            )

        conf = item.get("confidence")
        if conf is not None:
            if not isinstance(conf, (int, float)) or isinstance(conf, bool):
                result.error(
                    f"'suggested_definition_updates[{i}].confidence' חייב להיות float — "
                    f"נמצא: {conf!r}"
                )
            elif not (0.0 <= conf <= 1.0):
                result.error(
                    f"'suggested_definition_updates[{i}].confidence' מחוץ לטווח 0–1: {conf}"
                )


def validate(data: dict) -> ValidationResult:
    """Main entry point — validate a parsed book_intake_profile dict."""
    result = ValidationResult()
    validate_top_level(data, result)
    validate_intake_status(data, result)
    flags = validate_safety_flags(data, result)
    validate_corpus_quality(data, flags, result)
    validate_suggested_definition_updates(data, result)
    return result


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

    vr = validate(data)
    # merge parse warnings into validate result
    for w in result.warnings:
        vr.warn(w)

    for msg in vr.warnings:
        print(f"[אזהרה] {msg}")

    if vr.ok:
        print("[תקין] Book Intake Profile — ולידציה עברה בהצלחה.")
        print(f"  book_id        : {data.get('book_id', '—')}")
        print(f"  intake_status  : {data.get('intake_status', '—')}")
        cq = data.get("corpus_quality") or {}
        print(f"  total_chars    : {cq.get('total_chars', '—')}")
        print(f"  extraction     : {cq.get('extraction_method', '—')}")
        flags = data.get("safety_flags") or {}
        print(f"  corpus_empty   : {flags.get('corpus_empty', '—')}")
        print(f"  corpus_low_q   : {flags.get('corpus_low_quality', '—')}")
        print(f"  blocked_def    : {flags.get('blocked_from_definition_write', '—')}")
        updates = data.get("suggested_definition_updates") or []
        print(f"  suggested_upd  : {len(updates)} פריטים")
        return 0
    else:
        for msg in vr.errors:
            print(f"[שגיאה] {msg}", file=sys.stderr)
        print(f"\nנמצאו {len(vr.errors)} שגיאות קריטיות.", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ולידטור Book Intake Profile — book_intake_profile.json (intake/1.0).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
דוגמאות שימוש:
  py -3.12 intake_validator.py --input profile.json
  cat profile.json | py -3.12 intake_validator.py --input -
""",
    )
    parser.add_argument(
        "--input",
        metavar="FILE",
        type=argparse.FileType("r", encoding="utf-8-sig"),
        default="-",
        help="נתיב לקובץ JSON לבדיקה (ברירת מחדל: stdin)",
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
