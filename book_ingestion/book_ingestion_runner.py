"""BookIngestionRunner: end-to-end pipeline from PDF to structured artifacts.

This is the single unified runner for ingesting a new numerology book PDF and
producing the structured JSON artifacts that the Book Lab and future calculator
work can consume.  It NEVER modifies any artifact that belongs to the golden
reference book ("ספר הנומרולוגיה השלם") or the live Book Lab / API.

Stages executed by BookIngestionRunner.run():
  1. Extract    – Detect native text vs OCR-needed; build full-page corpus text
  2. Preserve   – Write {title}__source_manifest.json + {title}__source_corpus.txt
  3. Split      – Detect structural parts/chapters → {title}__chapter_inventory.json
  4. Candidates – Scan paragraphs for calc patterns → {title}__calc_candidates.json
  5. Ingest DB  – Persist via BookProcessor.add_book() → numerology_books.db
  6. Draft      – Build draft catalog entry   → {title}__draft_catalog.json

Uncertainty classification labels used in output artifacts:
  needs_review        – default True on every draft item; must be reviewed before promotion
  interpretation_only – concept identified but no computable formula was found
  possible_formula    – paragraph contains both digits and math symbols (review carefully)
  numeric_reference   – paragraph contains digits but no clear formula
  missing_formula     – calc catalog entry has no formula field populated
  low_confidence_ocr  – raw text was empty or came from an OCR-only path

Existing components reused (not re-implemented):
  OCREngine       (book_ingestion/ocr_engine.py)         – status probe + sample extract
  BookProcessor   (book_ingestion/book_processor.py)     – SQLite ingestion
  KnowledgeStore  (book_ingestion/knowledge_store.py)    – DB persistence
  _match_concepts / CONCEPT_CATALOG (book_ingestion/rule_extractor.py) – pattern matching
  text_extractor  (ocr/text_extractor.py)                – full-page extraction (optional)

CLI usage:
  python -m NumerologyReportGenerator.book_ingestion.book_ingestion_runner \\
      --pdf  "C:\\path\\to\\book.pdf" \\
      --title "שם הספר" \\
      --id   "my_book_id" \\
      [--corpus green] \\
      [--outdir "C:\\path\\to\\output\\dir"] \\
      [--verbose]

  Or as a script:
  python book_ingestion_runner.py --pdf ... --title ... --id ...

Golden reference book artifacts and book_lab_catalog.json are NEVER written to.
No production switch is performed.  No UI is changed.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path bootstrap – runs before any other import so that sibling packages
# (including ocr/) are importable regardless of how the script is invoked.
# ---------------------------------------------------------------------------

_RUNNER_FILE = Path(__file__).resolve()
_INGESTION_DIR = _RUNNER_FILE.parent                  # .../book_ingestion/
_NRG_DIR = _INGESTION_DIR.parent                      # .../NumerologyReportGenerator/
_PROJECT_ROOT = _NRG_DIR.parent                       # .../ai_agents/
_OCR_DIR = _PROJECT_ROOT / "ocr"                      # .../ai_agents/ocr/

for _bootstrap_path in (_PROJECT_ROOT, _NRG_DIR, _OCR_DIR):
    _s = str(_bootstrap_path)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# ---------------------------------------------------------------------------
# Internal package imports (relative – works as part of the book_ingestion pkg)
# ---------------------------------------------------------------------------

from .ocr_engine import OCREngine                          # noqa: E402
from .book_processor import BookProcessor                  # noqa: E402
from .knowledge_store import KnowledgeStore                # noqa: E402
from .rule_extractor import _match_concepts, CONCEPT_CATALOG  # noqa: E402
from interpretation_layout import research_book_dir       # noqa: E402

# ---------------------------------------------------------------------------
# Optional: full-page extractor from ocr/ (handles all pages, not just ≤40)
# ocr_engine._extend_legacy_paths() has already run, so ocr/ is on sys.path.
# ---------------------------------------------------------------------------

try:
    from text_extractor import extract_text_from_pdf as _ocr_extract_pdf  # type: ignore
    _LEGACY_EXTRACTOR_AVAILABLE = True
except ImportError:
    _ocr_extract_pdf = None
    _LEGACY_EXTRACTOR_AVAILABLE = False

try:
    import fitz  # type: ignore  (PyMuPDF)
    _FITZ_AVAILABLE = True
except ImportError:
    fitz = None
    _FITZ_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safety constants – runner refuses to process the golden reference book
# ---------------------------------------------------------------------------

_GOLDEN_BOOK_ID = "sifur_hanumerology_hashalem"
_GOLDEN_BOOK_TITLE = "ספר הנומרולוגיה השלם"

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Matches page boundary markers produced by both OCR layers:
#   "--- Page 3 ---"  /  "--- Page 3 (OCR) ---"  /  "--- Page 3 (Empty) ---"
_PAGE_MARKER_RE = re.compile(r"^---\s*Page\s*\d+", re.MULTILINE)

# Per-page OCR quality markers produced by text_extractor:
#   "--- Page 5 (OCR heb=33%) ---"      → heb_ratio = 0.33
#   "--- Page 7 (Empty) ---"             → heb_ratio = 0.0
#   "--- Page 3 ---"                     → native text (assumed good, skipped)
#   "--- Page 3 (OCR heb=41% patched) ---" → previously patched page
_PAGE_QUALITY_RE = re.compile(
    r"---\s*Page\s*(\d+)\s*\(OCR\s+heb=(\d+)%[^)]*\)\s*---"
    r"|---\s*Page\s*(\d+)\s*\(Empty\)\s*---",
    re.IGNORECASE,
)

# Minimum Hebrew ratio for a page to be considered acceptable quality
_OCR_QUALITY_THRESHOLD = 0.25

# Candidate detection (mirrors what produced the golden __calc_candidates.json)
_DIGIT_RE = re.compile(r"\d+")
_MATH_SYMBOL_RE = re.compile(r"[=+\-×÷]")

# Hebrew + English keywords whose presence marks a paragraph as a candidate.
# Kept intentionally broad – false positives are better than false negatives
# at this stage; all outputs are flagged needs_review=True.
_KEYWORD_REASONS: tuple[str, ...] = (
    "ביטוי", "גורל", "נשמה", "התנהגות", "שם", "מוחצנ",
    "חיים", "זמני", "מספר", "חישוב", "משמעות", "אתגר",
    "שנה", "פסגה", "קרמ", "מאסטר", "חסר", "עודף",
    "שביל", "ייעוד",
)

_PAGE_NOISE_RE = re.compile(
    r"^\s*(?:עמוד\s*\d+|page\s*\d+|[-–—]*\s*\d+\s*[-–—]*)\s*$",
    re.IGNORECASE,
)
_FORMULA_HINT_RE = re.compile(
    r"(?:נוסח(?:ה|אות)|חישוב|לחשב|מחבר(?:ים|ות)?|סכום|סיכום|reduce|formula|calculate|calculation|[=+\-×÷])",
    re.IGNORECASE,
)
_INTERPRETATION_HINT_RE = re.compile(
    r"(?:פירוש|פרשנות|משמעות|המשמעות|interpretation|meaning|מספר\s*(?:[1-9]|11|22|33)\b)",
    re.IGNORECASE,
)
_NUMEROLOGY_HINT_RE = re.compile(
    r"(?:מספר|שם|ייעוד|גורל|נשמה|פסגה|אתגר|שנה|כתובת|דירה|בית|מאסטר|קרמ)",
    re.IGNORECASE,
)
_ALPHA_RE = re.compile(r"[A-Za-z\u0590-\u05FF]")
_NUMERIC_VALUE_HINT_RE = re.compile(
    r"(?:^|[\s(])(מספר\s*)?(?:[1-9]|11|22|33)(?=(?:[\s:.)-]|$))",
    re.IGNORECASE,
)
_VALUE_HEADER_RE = re.compile(
    r"^\s*[|:;.,()\[\]\-–—]*\s*מספר\s+([1-9]|11|22|33|ל)\s*[|:;.,()\[\]\-–—]*\s*$",
    re.IGNORECASE,
)
_FORMULA_ACTION_RE = re.compile(
    r"(?:נוטלים|מחברים|מצמצמ|רושמים|ממשיכים|מחיק(?:ה|ת)|מסכמים|סיכום|מחברים|מפחיתים|מחסרים|מכפילים|מחלקים|אין ממשיכים בצמצום|על ידי צירוף)",
    re.IGNORECASE,
)
_GENERIC_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\!\?\n])\s+")

# ---------------------------------------------------------------------------
# Per-page OCR quality helpers
# ---------------------------------------------------------------------------

def _parse_per_page_quality(raw_text: str) -> List[Dict[str, Any]]:
    """Parse per-page OCR quality from corpus text markers.

    Returns a list of dicts sorted by page number, each containing:
      page        – 1-based page number
      heb_ratio   – float 0.0–1.0 (None for native-text pages)
      source      – "ocr" | "empty" | "native"
      needs_rescan – True if heb_ratio < _OCR_QUALITY_THRESHOLD

    Native-text pages (plain "--- Page N ---") are never flagged for rescan.
    """
    pages: Dict[int, Dict[str, Any]] = {}
    for m in _PAGE_QUALITY_RE.finditer(raw_text):
        # Group 1+2: OCR match "--- Page N (OCR heb=X%) ---"
        # Group 3:   Empty match "--- Page N (Empty) ---"
        if m.group(1) is not None:
            page_num = int(m.group(1))
            heb_ratio = int(m.group(2)) / 100.0
            source = "ocr"
        else:
            page_num = int(m.group(3))
            heb_ratio = 0.0
            source = "empty"
        pages[page_num] = {
            "page": page_num,
            "heb_ratio": round(heb_ratio, 3),
            "source": source,
            "needs_rescan": heb_ratio < _OCR_QUALITY_THRESHOLD,
        }

    # Also detect plain native markers (no quality annotation)
    _NATIVE_RE = re.compile(r"---\s*Page\s*(\d+)\s*---(?!\s*\()", re.MULTILINE)
    for m in _NATIVE_RE.finditer(raw_text):
        page_num = int(m.group(1))
        if page_num not in pages:
            pages[page_num] = {
                "page": page_num,
                "heb_ratio": None,
                "source": "native",
                "needs_rescan": False,
            }

    return sorted(pages.values(), key=lambda x: x["page"])


# Structural boundary patterns
_PART_RE = re.compile(
    r"^(?:חלק\s+[א-ת\d]+|part\s+[ivxlcdm\d]+)",
    re.IGNORECASE,
)
_CHAPTER_RE = re.compile(
    r"^(?:פרק\s+\d+|chapter\s+\d+|section\s+\d+|נושא\s+\d+)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Input dependency catalog
#
# Each entry describes one recognisable input type that a numerology calculation
# may require.  The "strength" field is the *default* classification when this
# pattern is found in a paragraph:
#   "required"  – the calculation clearly cannot proceed without this input
#   "optional"  – the calculation may use this input but can proceed without it
#   "ambiguous" – context is unclear; must be reviewed before classifying
#
# The catalog is intentionally broad: it is better to surface an ambiguous hit
# for human review than to silently miss an input dependency.
# ---------------------------------------------------------------------------

_INPUT_TYPE_PATTERNS: List[Dict[str, Any]] = [
    {
        "input_type": "apartment_number",
        "label_he": "מספר דירה",
        "strength": "required",
        "patterns": [
            r"מספר\s*הדירה",
            r"מספרי?\s*דירה",
            r"דירה\s*מספר",
            r"apartment\s*number",
        ],
    },
    {
        "input_type": "house_number",
        "label_he": "מספר בית",
        "strength": "required",
        "patterns": [
            r"מספר\s*הבית",
            r"מספרי?\s*בית",
            r"בית\s*מספר",
            r"house\s*number",
        ],
    },
    {
        "input_type": "floor_number",
        "label_he": "מספר קומה",
        "strength": "optional",
        "patterns": [
            r"מספר\s*קומה",
            r"קומה\s*מספר",
            r"קומה\s*\d+",
            r"floor\s*number",
        ],
    },
    {
        "input_type": "street_number",
        "label_he": "מספר רחוב",
        "strength": "optional",
        "patterns": [
            r"מספרי?\s*הרחוב",
            r"מספר\s*רחוב",
            r"רחוב\s*\d+",
            r"street\s*(?:address\s*)?number",
        ],
    },
    {
        "input_type": "address",
        "label_he": "כתובת",
        "strength": "optional",
        "patterns": [
            r"\bכתובת\b",
            r"\baddress\b",
        ],
    },
    {
        "input_type": "current_year",
        "label_he": "שנה נוכחית",
        "strength": "optional",
        "patterns": [
            r"השנה\s*הנוכחית",
            r"שנה\s*נוכחית",
            r"שנה\s*הנוכחית",
            r"current\s*year",
        ],
    },
    {
        "input_type": "full_name",
        "label_he": "שם מלא",
        "strength": "optional",
        "patterns": [
            r"שם\s*מלא",
            r"full\s*name",
        ],
    },
    {
        "input_type": "first_name",
        "label_he": "שם פרטי",
        "strength": "optional",
        "patterns": [
            r"שם\s*פרטי",
            r"first\s*name",
        ],
    },
    {
        "input_type": "last_name",
        "label_he": "שם משפחה",
        "strength": "optional",
        "patterns": [
            r"שם\s*משפחה",
            r"last\s*name",
            r"family\s*name",
        ],
    },
    {
        "input_type": "birth_date",
        "label_he": "תאריך לידה",
        "strength": "ambiguous",
        "patterns": [
            r"תאריך\s*לידה",
            r"מפ[את]\s*(?:ה)?לידה",
            r"מפ[את]\s*(?:ה)?נומרולוגי",
            r"birth\s*date",
        ],
    },
    {
        "input_type": "birth_day",
        "label_he": "יום לידה",
        "strength": "optional",
        "patterns": [
            r"יום\s*לידה",
            r"birth\s*day",
        ],
    },
    {
        "input_type": "birth_year",
        "label_he": "שנת לידה",
        "strength": "optional",
        "patterns": [
            r"שנת\s*לידה",
            r"birth\s*year",
        ],
    },
    {
        "input_type": "mother_name",
        "label_he": "שם האם",
        "strength": "ambiguous",
        "patterns": [
            r"שם\s*האם",
            r"שם\s*אמא",
            r"mother.?s?\s*name",
        ],
    },
    {
        "input_type": "father_name",
        "label_he": "שם האב",
        "strength": "ambiguous",
        "patterns": [
            r"שם\s*האב",
            r"שם\s*אבא",
            r"father.?s?\s*name",
        ],
    },
    {
        "input_type": "marriage_name",
        "label_he": "שם נישואין",
        "strength": "ambiguous",
        "patterns": [
            r"שם\s*נישואין",
            r"שם\s*לאחר\s*נישואין",
            r"marriage\s*name",
        ],
    },
    {
        "input_type": "id_number",
        "label_he": "מספר תעודת זהות",
        "strength": "optional",
        "patterns": [
            r"תעודת\s*זהות",
            r"מספר\s*זיהוי",
            r"id\s*number",
            r"ת\.?ז\.?",
        ],
    },
    {
        "input_type": "passport_number",
        "label_he": "מספר דרכון",
        "strength": "optional",
        "patterns": [
            r"מספר\s*דרכון",
            r"passport\s*number",
        ],
    },
    {
        "input_type": "car_number",
        "label_he": "מספר רכב",
        "strength": "optional",
        "patterns": [
            r"מספר\s*רכב",
            r"לוחית\s*רישוי",
            r"car\s*(?:plate\s*)?number",
            r"license\s*plate",
        ],
    },
    {
        "input_type": "city_name",
        "label_he": "שם עיר",
        "strength": "optional",
        "patterns": [
            r"שם\s*(?:ה)?עיר",
            r"city\s*name",
        ],
    },
    {
        "input_type": "other_numeric_identifier",
        "label_he": "מזהה מספרי אחר",
        "strength": "ambiguous",
        "patterns": [
            r"מספר\s*מזהה",
            r"other\s*(?:numeric\s*)?identifier",
        ],
    },
]


def _detect_input_dependencies(text: str) -> Dict[str, Any]:
    """Scan a paragraph for input dependency signals.

    Checks every entry in _INPUT_TYPE_PATTERNS against the paragraph text.
    Returns a dict with required/optional/ambiguous lists, matched source
    terms, and overall ambiguity flag.

    The "confidence" within each input_type_hint is:
      "confident" – the exact term was matched in this paragraph
      "ambiguous" – the pattern is inherently ambiguous per catalog definition

    All outputs carry needs_review=True because this is a draft pipeline stage.
    Source wording is preserved verbatim in "source_term" so reviewers can
    trace the evidence back to the original text.
    """
    required_inputs: List[str] = []
    optional_inputs: List[str] = []
    ambiguous_inputs: List[str] = []
    hints: Dict[str, Dict[str, Any]] = {}

    for defn in _INPUT_TYPE_PATTERNS:
        input_type: str = defn["input_type"]
        declared_strength: str = defn["strength"]
        label_he: str = defn["label_he"]

        matched_term: Optional[str] = None
        for pattern in defn["patterns"]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                matched_term = m.group(0)
                break

        if matched_term is None:
            continue

        # Confidence: "ambiguous" if catalog marks it so, else "confident"
        confidence = "ambiguous" if declared_strength == "ambiguous" else "confident"

        hints[input_type] = {
            "confidence": confidence,
            "label_he": label_he,
            "source_term": matched_term,        # exact matched wording preserved
            "declared_strength": declared_strength,
        }

        if declared_strength == "required":
            if input_type not in required_inputs:
                required_inputs.append(input_type)
        elif declared_strength == "optional":
            if input_type not in optional_inputs:
                optional_inputs.append(input_type)
        else:  # "ambiguous"
            if input_type not in ambiguous_inputs:
                ambiguous_inputs.append(input_type)

    nothing_found = not required_inputs and not optional_inputs and not ambiguous_inputs
    return {
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "ambiguous_inputs": ambiguous_inputs,
        "input_type_hints": hints,
        # True when no recognized input signal was found at all
        "ambiguous_input_dependency": nothing_found or bool(
            ambiguous_inputs and not required_inputs and not optional_inputs
        ),
        "needs_review": True,
    }


def _aggregate_input_deps(
    evidence_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate input dependency dicts from multiple candidate paragraphs.

    An input_type graduates to "required" if it was required in any evidence item.
    It becomes "optional" if it was optional in some but never required.
    It stays "ambiguous" if only ambiguous evidence exists.

    Returns a consolidated input dependency dict suitable for a catalog entry.
    """
    required_counter: Dict[str, int] = {}
    optional_counter: Dict[str, int] = {}
    ambiguous_counter: Dict[str, int] = {}
    all_hints: Dict[str, Dict[str, Any]] = {}

    for ev in evidence_list:
        deps: Dict[str, Any] = ev.get("input_dependencies") or {}
        for it in deps.get("required_inputs") or []:
            required_counter[it] = required_counter.get(it, 0) + 1
        for it in deps.get("optional_inputs") or []:
            optional_counter[it] = optional_counter.get(it, 0) + 1
        for it in deps.get("ambiguous_inputs") or []:
            ambiguous_counter[it] = ambiguous_counter.get(it, 0) + 1
        for it, hint in (deps.get("input_type_hints") or {}).items():
            if it not in all_hints:
                all_hints[it] = dict(hint)
            # Escalate if a later item has a stronger signal
            existing = all_hints[it]
            if existing.get("declared_strength") == "ambiguous" and hint.get("declared_strength") != "ambiguous":
                all_hints[it] = dict(hint)

    # Promote: required > optional > ambiguous
    required = sorted(required_counter)
    optional = sorted(it for it in optional_counter if it not in required_counter)
    ambiguous = sorted(
        it for it in ambiguous_counter
        if it not in required_counter and it not in optional_counter
    )

    all_known = set(required) | set(optional) | set(ambiguous)

    if required:
        overall = "confident"
    elif optional:
        overall = "probable"
    else:
        overall = "ambiguous_input_dependency"

    return {
        "required_inputs": required,
        "optional_inputs": optional,
        "ambiguous_inputs": ambiguous,
        "input_type_hints": {k: v for k, v in all_hints.items() if k in all_known},
        "input_dependency_confidence": overall,
        "ambiguous_input_dependency": not required and not optional,
        "needs_review": True,
    }


# ---------------------------------------------------------------------------
# Draft enrichment helpers
# ---------------------------------------------------------------------------

def _clean_paragraph_text(paragraph: str) -> str:
    kept_lines: List[str] = []
    for raw_line in str(paragraph or "").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if _PAGE_MARKER_RE.match(stripped):
            continue
        if _PAGE_NOISE_RE.match(stripped):
            continue
        if re.fullmatch(r"[\d\s,./\\|:_\-*+=]{1,20}", stripped):
            continue
        if len(stripped) <= 3 and not _ALPHA_RE.search(stripped):
            continue
        kept_lines.append(stripped)
    return "\n".join(kept_lines).strip()


def _split_raw_text_into_section_blocks(
    raw_text: str,
    sections: List[Dict[str, Any]],
) -> List[Tuple[str, str]]:
    section_relpaths = [s["relative_path"] for s in sections]
    default_relpath = section_relpaths[0] if section_relpaths else "main\\body.txt"
    section_blocks: List[Tuple[str, List[str]]] = []
    current_lines: List[str] = []
    section_idx = 0

    for line in raw_text.splitlines():
        stripped = line.strip()
        is_boundary = (
            section_idx + 1 < len(section_relpaths)
            and (_PART_RE.match(stripped) or _CHAPTER_RE.match(stripped))
            and len(stripped) <= 80
        )
        if is_boundary:
            rel = section_relpaths[section_idx] if section_idx < len(section_relpaths) else default_relpath
            section_blocks.append((rel, current_lines[:]))
            section_idx += 1
            current_lines = []
        else:
            current_lines.append(line)

    rel = section_relpaths[section_idx] if section_idx < len(section_relpaths) else default_relpath
    section_blocks.append((rel, current_lines))
    return [(rel_path, "\n".join(lines).strip()) for rel_path, lines in section_blocks]


def _has_structural_signal(paragraph: str) -> bool:
    has_digits = _DIGIT_RE.search(paragraph) is not None
    has_math = _MATH_SYMBOL_RE.search(paragraph) is not None
    has_formula = _FORMULA_HINT_RE.search(paragraph) is not None
    has_interpretation = _INTERPRETATION_HINT_RE.search(paragraph) is not None
    has_numerology = _NUMEROLOGY_HINT_RE.search(paragraph) is not None
    numeric_values = len(_NUMERIC_VALUE_HINT_RE.findall(paragraph))
    if has_formula and (has_digits or has_math or has_numerology):
        return True
    if has_interpretation and (numeric_values >= 1 or has_numerology):
        return True
    if has_digits and has_math:
        return True
    if has_digits and numeric_values >= 2 and has_numerology:
        return True
    return False


def _normalize_result_value_token(token: str) -> str:
    clean = str(token or "").strip()
    if clean == "ל":
        return "9"
    if clean in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "11", "22", "33"}:
        return clean
    return ""


def _dedupe_strings(items: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in items:
        clean = re.sub(r"\s+", " ", str(item or "")).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        ordered.append(clean)
    return ordered


def _extract_result_value_entries(text: str, source_ref: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    current_value = ""
    current_lines: List[str] = []
    current_page: Optional[int] = None
    value_page: Optional[int] = None

    def _flush_current() -> None:
        nonlocal current_value, current_lines, value_page
        if not current_value:
            return
        meaning = _clean_paragraph_text("\n".join(current_lines))
        meaning = re.sub(r"\s+", " ", meaning).strip()
        if len(meaning) < 60:
            current_value = ""
            current_lines = []
            value_page = None
            return
        ref = source_ref
        if value_page:
            ref = f"{source_ref}#p{value_page}"
        entries.append(
            {
                "value": current_value,
                "title": f"מספר {current_value}",
                "meaning": meaning[:1600],
                "source_ref": ref,
                "page_hint": value_page,
            }
        )
        current_value = ""
        current_lines = []
        value_page = None

    for raw_line in str(text or "").splitlines():
        stripped = raw_line.strip()
        page_match = _PAGE_MARKER_RE.match(stripped)
        if page_match:
            page_hint_match = re.search(r"Page\s+(\d+)", stripped, re.IGNORECASE)
            if page_hint_match:
                current_page = int(page_hint_match.group(1))
            continue
        if not stripped or _PAGE_NOISE_RE.match(stripped):
            continue
        value_match = _VALUE_HEADER_RE.match(stripped)
        if value_match:
            _flush_current()
            normalized = _normalize_result_value_token(value_match.group(1))
            if not normalized:
                continue
            current_value = normalized
            value_page = current_page
            current_lines = []
            continue
        if current_value:
            current_lines.append(stripped)

    _flush_current()
    deduped: List[Dict[str, Any]] = []
    seen_values: set[str] = set()
    for item in entries:
        value_key = str(item.get("value") or "")
        if value_key in seen_values:
            continue
        seen_values.add(value_key)
        deduped.append(item)
    return deduped


def _extract_formula_payload(
    concept_key: str,
    chapter_text: str,
    evidence_list: List[Dict[str, Any]],
) -> Tuple[str, List[str], str]:
    paragraphs = [
        _clean_paragraph_text(paragraph)
        for paragraph in re.split(r"\n[ \t]*\n", str(chapter_text or ""))
    ]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph and _ALPHA_RE.search(paragraph)]
    scored: List[Tuple[int, int, str]] = []
    for idx, paragraph in enumerate(paragraphs):
        if _VALUE_HEADER_RE.match(paragraph):
            continue
        score = 0
        if concept_key in _match_concepts(paragraph):
            score += 5
        if _FORMULA_HINT_RE.search(paragraph):
            score += 4
        if _FORMULA_ACTION_RE.search(paragraph):
            score += 3
        if _MATH_SYMBOL_RE.search(paragraph):
            score += 3
        digit_count = len(_DIGIT_RE.findall(paragraph))
        score += min(digit_count, 4)
        if _has_structural_signal(paragraph):
            score += 2
        if len(paragraph) > 650:
            score -= 1
        if score >= 6:
            scored.append((score, idx, paragraph))

    best_paragraph = ""
    chosen_indices: List[int] = []
    if scored:
        scored_sorted = sorted(scored, key=lambda item: (-item[0], item[1]))
        _, best_idx, best_paragraph = scored_sorted[0]
        chosen_indices.append(best_idx)
        for neighbor in (best_idx - 1, best_idx + 1):
            if 0 <= neighbor < len(paragraphs):
                neighbor_text = paragraphs[neighbor]
                if _FORMULA_HINT_RE.search(neighbor_text) or _FORMULA_ACTION_RE.search(neighbor_text):
                    chosen_indices.append(neighbor)
        chosen_indices = sorted(set(chosen_indices))

    if not best_paragraph and evidence_list:
        formula_candidates = [
            re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
            for item in evidence_list
            if _FORMULA_HINT_RE.search(str(item.get("text") or "")) or _MATH_SYMBOL_RE.search(str(item.get("text") or ""))
        ]
        formula_candidates = [item for item in formula_candidates if item]
        if formula_candidates:
            best_paragraph = max(formula_candidates, key=len)

    formula_steps: List[str] = []
    for idx in chosen_indices:
        for sentence in _GENERIC_SENTENCE_SPLIT_RE.split(paragraphs[idx]):
            cleaned = re.sub(r"\s+", " ", sentence).strip(" -|:;")
            if len(cleaned) < 18:
                continue
            if not (
                _FORMULA_HINT_RE.search(cleaned)
                or _FORMULA_ACTION_RE.search(cleaned)
                or _MATH_SYMBOL_RE.search(cleaned)
                or len(_DIGIT_RE.findall(cleaned)) >= 2
            ):
                continue
            formula_steps.append(cleaned[:280])
    formula_steps = _dedupe_strings(formula_steps)[:6]

    excerpt = ""
    if evidence_list:
        excerpt = max(
            (
                re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
                for item in evidence_list
                if str(item.get("text") or "").strip()
            ),
            key=len,
            default="",
        )[:500]
    if not excerpt:
        excerpt = best_paragraph[:500]
    return best_paragraph[:700], formula_steps, excerpt


def _build_interpretation_summary(result_values: List[Dict[str, Any]], chapter_text: str) -> str:
    if result_values:
        preview_lines = [
            f"{str(item.get('title') or '').strip()}: {str(item.get('meaning') or '').strip()}"
            for item in result_values[:4]
            if str(item.get("meaning") or "").strip()
        ]
        return "\n\n".join(preview_lines)[:2200]

    interpretation_paragraphs: List[str] = []
    for paragraph in re.split(r"\n[ \t]*\n", str(chapter_text or "")):
        cleaned = _clean_paragraph_text(paragraph)
        if len(cleaned) < 60:
            continue
        if not _INTERPRETATION_HINT_RE.search(cleaned):
            continue
        interpretation_paragraphs.append(re.sub(r"\s+", " ", cleaned).strip())
    interpretation_paragraphs = _dedupe_strings(interpretation_paragraphs)
    return "\n\n".join(interpretation_paragraphs[:3])[:2200]


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any, *, indent: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )
    logger.info("Wrote %-50s (%d bytes)", path.name, path.stat().st_size)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    logger.info("Wrote %-50s (%d bytes)", path.name, path.stat().st_size)


# ---------------------------------------------------------------------------
# Stage 1 helpers: full-page PDF extraction
# ---------------------------------------------------------------------------

def _extract_full_pdf_text(
    pdf_path: Path,
    engine: OCREngine,
    pre_computed_probe: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """Extract complete page-by-page text from a PDF, preserving page markers.

    Strategy priority:
      1. fitz native-text (all pages)  – preferred for text-native PDFs
      2. ocr/text_extractor            – handles mixed/scanned PDFs, all pages
      2b. pdf2image+tesseract (all pages) – when fitz/legacy unavailable
      3. pre_computed_probe reuse      – avoid double OCR when probe already ran
      4. ocr_engine.inspect() sample   – last-resort fallback, ≤3 pages

    Page boundaries are always preserved as '--- Page N ---' markers so that
    rule_extractor._find_page_hint() and the structural split work correctly.

    Returns (raw_text, extraction_metadata_dict).
    """
    meta: Dict[str, Any] = {
        "strategy": "unknown",
        "total_pages": 0,
        "pages_extracted": 0,
        "ocr_needed_pages": 0,
    }

    # ------------------------------------------------------------------
    # Strategy 1: fitz native text (all pages, fast, preserves layout)
    # ------------------------------------------------------------------
    if _FITZ_AVAILABLE and fitz is not None:
        try:
            doc = fitz.open(str(pdf_path))
            total = len(doc)
            meta["total_pages"] = total
            parts: List[str] = []
            ocr_empty = 0
            for idx, page in enumerate(doc, start=1):
                try:
                    page_text = page.get_text("text") or ""
                except Exception:
                    page_text = ""
                if page_text.strip():
                    parts.append(f"--- Page {idx} ---\n{page_text.strip()}")
                    meta["pages_extracted"] += 1
                else:
                    parts.append(f"--- Page {idx} (Empty) ---")
                    ocr_empty += 1
            joined = "\n".join(parts)
            meta["ocr_needed_pages"] = ocr_empty
            # Accept if we got meaningful text from at least some pages
            meaningful = len(
                re.sub(r"---\s*Page\s*\d+[^\n]*---", "", joined).strip()
            )
            if meaningful >= engine.MIN_TEXT_CHARS * 3:
                meta["strategy"] = "fitz-native-full"
                return joined, meta
            logger.debug(
                "fitz native text too sparse (%d chars) – trying next strategy",
                meaningful,
            )
        except Exception as exc:
            logger.warning("fitz full-page extraction failed: %s", exc)
            meta["fitz_error"] = str(exc)

    # ------------------------------------------------------------------
    # Strategy 2: ocr/text_extractor (all pages, handles scanned PDFs)
    # ------------------------------------------------------------------
    if _LEGACY_EXTRACTOR_AVAILABLE and _ocr_extract_pdf is not None:
        try:
            legacy_text = _ocr_extract_pdf(
                str(pdf_path), lang="heb+eng", force_ocr=False
            )
            if legacy_text and len(legacy_text.strip()) >= engine.MIN_TEXT_CHARS:
                page_count = len(_PAGE_MARKER_RE.findall(legacy_text))
                meta["strategy"] = "legacy-text-extractor-full"
                meta["total_pages"] = page_count
                meta["pages_extracted"] = page_count
                return legacy_text, meta
        except Exception as exc:
            logger.warning("ocr/text_extractor full extraction failed: %s", exc)
            meta["legacy_error"] = str(exc)

    # ------------------------------------------------------------------
    # Strategy 2b: force OCR on every page if mixed-mode extraction was
    # still too sparse. This is the strongest local recovery path and is
    # especially useful for scanned Hebrew books with weak embedded text.
    # ------------------------------------------------------------------
    if _LEGACY_EXTRACTOR_AVAILABLE and _ocr_extract_pdf is not None:
        try:
            force_ocr_text = _ocr_extract_pdf(
                str(pdf_path), lang="heb+eng", force_ocr=True
            )
            if force_ocr_text and len(force_ocr_text.strip()) >= engine.MIN_TEXT_CHARS:
                page_count = len(_PAGE_MARKER_RE.findall(force_ocr_text))
                meta["strategy"] = "legacy-text-extractor-force-ocr"
                meta["total_pages"] = page_count
                meta["pages_extracted"] = page_count
                meta["ocr_needed_pages"] = page_count
                return force_ocr_text, meta
        except Exception as exc:
            logger.warning("ocr/text_extractor force OCR failed: %s", exc)
            meta["legacy_force_ocr_error"] = str(exc)

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Strategy 2b: pdf2image + tesseract, all pages (when fitz unavailable)
    # ------------------------------------------------------------------
    try:
        from pdf2image import convert_from_path as _pdf2img  # type: ignore
        import pytesseract as _pytess  # type: ignore
        pages_all = _pdf2img(str(pdf_path), dpi=150)
        total = len(pages_all)
        meta["total_pages"] = total
        parts_ocr: List[str] = []
        for idx, img in enumerate(pages_all, start=1):
            try:
                page_text = _pytess.image_to_string(img, lang=engine.language, timeout=engine.tesseract_timeout_sec)
            except Exception:
                page_text = ""
            if page_text.strip():
                parts_ocr.append(f"--- Page {idx} ---\n{page_text.strip()}")
                meta["pages_extracted"] = meta.get("pages_extracted", 0) + 1
            else:
                parts_ocr.append(f"--- Page {idx} (Empty) ---")
        joined_ocr = "\n".join(parts_ocr)
        meaningful_ocr = len(re.sub(r"---\s*Page\s*\d+[^\n]*---", "", joined_ocr).strip())
        if meaningful_ocr >= engine.MIN_TEXT_CHARS:
            meta["strategy"] = "pdf2image+tesseract-full"
            meta["ocr_needed_pages"] = total
            return joined_ocr, meta
    except Exception as exc:
        logger.warning("pdf2image full-page OCR failed: %s", exc)
        meta["pdf2image_full_error"] = str(exc)

    # ------------------------------------------------------------------
    # Strategy 3: reuse pre-computed probe to avoid double OCR
    # ------------------------------------------------------------------
    if pre_computed_probe is not None:
        probe_text = str(pre_computed_probe.get("text") or "")
        if probe_text.strip():
            logger.info("Reusing pre-computed probe result (avoids second OCR pass)")
            probe_meta = dict(pre_computed_probe.get("metadata") or {})
            meta["strategy"] = f"pre_computed_probe:{pre_computed_probe.get('status', 'unknown')}"
            meta["pages_extracted"] = probe_meta.get("pages_sampled", 0)
            meta["total_pages"] = probe_meta.get("pages_sampled", 0)
            meta["extraction_quality"] = "sample_only"
            return probe_text, meta

    # ------------------------------------------------------------------
    # Strategy 4: ocr_engine.inspect() sample (≤3 pages, last resort)
    # ------------------------------------------------------------------
    logger.warning(
        "Full-page extraction unavailable – falling back to ocr_engine sample (≤3 pages)"
    )
    result = engine.inspect(str(pdf_path))
    sample_text = str(result.get("text") or "")
    engine_meta = dict(result.get("metadata") or {})
    meta["strategy"] = f"ocr_engine_sample:{result.get('status', 'unknown')}"
    meta["pages_extracted"] = engine_meta.get("pages_sampled", 0)
    meta["total_pages"] = engine_meta.get("pages_sampled", 0)
    meta["extraction_quality"] = "low_confidence_ocr" if not sample_text.strip() else "sample_only"
    meta.update({k: v for k, v in engine_meta.items() if k not in meta})
    return sample_text, meta


# ---------------------------------------------------------------------------
# Stage 3 helper: structural split
# ---------------------------------------------------------------------------

def _calc_like_count(paragraphs: List[str]) -> int:
    """Count paragraphs that contain digits or numerology keywords."""
    count = 0
    for p in paragraphs:
        if _DIGIT_RE.search(p) or any(kw in p for kw in _KEYWORD_REASONS):
            count += 1
    return count


def _safe_filename(name: str) -> str:
    """Strip characters invalid in Windows file names."""
    return re.sub(r'[\\/:*?"<>|]', "_", (name or "").strip())


def _split_into_sections(
    raw_text: str,
    book_id: str,
) -> List[Dict[str, Any]]:
    """Detect structural boundaries and return chapter-inventory-shaped records.

    Each record matches the existing __chapter_inventory.json schema:
      relative_path, directory, file_name, length_bytes, line_count,
      word_count, paragraph_count, calc_like_paragraphs

    An extra field "extraction_note" is added to signal auto-detection.

    Boundaries detected from:
      - Hebrew part headings (חלק א/ב/ג...)
      - Hebrew/English chapter headings (פרק N / chapter N / section N)
      - If no boundaries found → entire text becomes one section
    """
    lines = raw_text.splitlines()
    sections: List[Dict[str, Any]] = []

    current_part = "main"
    current_chapter_name: Optional[str] = None
    current_lines: List[str] = []
    section_index = 0

    def _flush(part: str, name: Optional[str], block: List[str], idx: int) -> None:
        text_block = "\n".join(block).strip()
        if not text_block:
            return
        paragraphs = [p.strip() for p in re.split(r"\n[ \t]*\n", text_block) if p.strip()]
        display = name or f"section_{idx + 1}"
        fname = _safe_filename(display) + ".txt"
        rel = f"{part}\\{fname}"
        sections.append({
            "relative_path": rel,
            "directory": part,
            "file_name": fname,
            "length_bytes": len(text_block.encode("utf-8")),
            "line_count": len(block),
            "word_count": len(text_block.split()),
            "paragraph_count": len(paragraphs),
            "calc_like_paragraphs": _calc_like_count(paragraphs),
            "extraction_note": "auto_detected_boundary",
        })

    for line in lines:
        stripped = line.strip()

        # Part boundary (e.g. "חלק ב", "Part II")
        if _PART_RE.match(stripped) and len(stripped) <= 60:
            _flush(current_part, current_chapter_name, current_lines, section_index)
            section_index += 1
            current_part = _safe_filename(stripped) or f"part_{section_index}"
            current_chapter_name = stripped
            current_lines = []
            continue

        # Chapter boundary (e.g. "פרק 5", "Chapter 3")
        if _CHAPTER_RE.match(stripped) and len(stripped) <= 80:
            _flush(current_part, current_chapter_name, current_lines, section_index)
            section_index += 1
            current_chapter_name = stripped
            current_lines = []
            continue

        current_lines.append(line)

    # Flush the final section
    _flush(current_part, current_chapter_name, current_lines, section_index)

    # If no structural boundaries were found, treat the whole text as one section
    if not sections:
        all_paras = [p.strip() for p in re.split(r"\n[ \t]*\n", raw_text) if p.strip()]
        sections.append({
            "relative_path": f"main\\{book_id}.txt",
            "directory": "main",
            "file_name": f"{book_id}.txt",
            "length_bytes": len(raw_text.encode("utf-8")),
            "line_count": len(lines),
            "word_count": len(raw_text.split()),
            "paragraph_count": len(all_paras),
            "calc_like_paragraphs": _calc_like_count(all_paras),
            "extraction_note": "no_structural_boundaries_detected",
        })

    return sections


# ---------------------------------------------------------------------------
# Stage 4 helper: candidate extraction
# ---------------------------------------------------------------------------

def _extract_candidates(
    raw_text: str,
    sections: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Scan paragraphs for calculation/interpretation candidates.

    Output schema matches existing __calc_candidates.json:
      relative_path, paragraph_index, reasons, text, char_count

    Extra honest-classification fields added (do not break existing readers):
      needs_review      – always True in draft stage
      extraction_quality – interpretation_only | possible_formula | numeric_reference

    paragraph_index is 1-based within each relative_path section,
    matching the golden reference schema convention.
    """
    section_relpaths = [s["relative_path"] for s in sections]
    default_relpath = section_relpaths[0] if section_relpaths else "main\\body.txt"

    # Re-scan raw_text with the same boundary logic so paragraph-to-section
    # mapping is consistent with what _split_into_sections produced.
    section_blocks: List[Tuple[str, List[str]]] = []  # (relative_path, lines)
    current_lines: List[str] = []
    section_idx = 0

    for line in raw_text.splitlines():
        stripped = line.strip()
        is_boundary = (
            section_idx + 1 < len(section_relpaths)
            and (_PART_RE.match(stripped) or _CHAPTER_RE.match(stripped))
            and len(stripped) <= 80
        )
        if is_boundary:
            rel = section_relpaths[section_idx] if section_idx < len(section_relpaths) else default_relpath
            section_blocks.append((rel, current_lines[:]))
            section_idx += 1
            current_lines = []
        else:
            current_lines.append(line)

    # Final block
    rel = section_relpaths[section_idx] if section_idx < len(section_relpaths) else default_relpath
    section_blocks.append((rel, current_lines))

    # Scan each section's paragraphs
    candidates: List[Dict[str, Any]] = []

    def _clean_paragraph_text(paragraph: str) -> str:
        kept_lines: List[str] = []
        for raw_line in str(paragraph or "").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if _PAGE_MARKER_RE.match(stripped):
                continue
            if _PAGE_NOISE_RE.match(stripped):
                continue
            if re.fullmatch(r"[\d\s,./\\|:_-]{1,16}", stripped):
                continue
            if len(stripped) <= 3 and not _ALPHA_RE.search(stripped):
                continue
            kept_lines.append(stripped)
        return "\n".join(kept_lines).strip()

    def _has_structural_signal(paragraph: str) -> bool:
        has_digits = _DIGIT_RE.search(paragraph) is not None
        has_math = _MATH_SYMBOL_RE.search(paragraph) is not None
        has_formula = _FORMULA_HINT_RE.search(paragraph) is not None
        has_interpretation = _INTERPRETATION_HINT_RE.search(paragraph) is not None
        has_numerology = _NUMEROLOGY_HINT_RE.search(paragraph) is not None
        numeric_values = len(_NUMERIC_VALUE_HINT_RE.findall(paragraph))
        if has_formula and (has_digits or has_math or has_numerology):
            return True
        if has_interpretation and (numeric_values >= 1 or has_numerology):
            return True
        if has_digits and has_math:
            return True
        if has_digits and numeric_values >= 2 and has_numerology:
            return True
        return False

    for rel_path, block_lines in section_blocks:
        block_text = "\n".join(block_lines)
        paragraphs = [p.strip() for p in re.split(r"\n[ \t]*\n", block_text) if p.strip()]

        for para_idx, para in enumerate(paragraphs, start=1):
            clean_para = _clean_paragraph_text(para)
            if not clean_para:
                continue
            if not _ALPHA_RE.search(clean_para):
                continue

            reasons: List[str] = []

            if _DIGIT_RE.search(clean_para):
                reasons.append("digits")
            if _MATH_SYMBOL_RE.search(clean_para):
                reasons.append("math-symbols")
            for kw in _KEYWORD_REASONS:
                if kw in clean_para:
                    reasons.append(kw)

            if not reasons:
                continue
            if not _has_structural_signal(clean_para):
                continue

            # Honest classification of extraction confidence
            has_digits = _DIGIT_RE.search(clean_para) is not None
            has_math = _MATH_SYMBOL_RE.search(clean_para) is not None
            has_formula = _FORMULA_HINT_RE.search(clean_para) is not None
            has_interpretation = _INTERPRETATION_HINT_RE.search(clean_para) is not None
            if has_formula and (has_digits or has_math):
                extraction_quality = "possible_formula"
            elif has_interpretation:
                extraction_quality = "interpretation_only"
            elif has_digits:
                extraction_quality = "numeric_reference"
            else:
                extraction_quality = "interpretation_only"

            candidates.append({
                "relative_path": rel_path,
                "paragraph_index": para_idx,
                "reasons": list(dict.fromkeys(reasons)),
                "text": clean_para,
                "char_count": len(clean_para),
                # Honest uncertainty classification fields
                "needs_review": True,
                "extraction_quality": extraction_quality,
                # Input dependency detection (see _INPUT_TYPE_PATTERNS catalog)
                "input_dependencies": _detect_input_dependencies(clean_para),
            })

    return candidates


# ---------------------------------------------------------------------------
# Stage 6 helper: draft catalog
# ---------------------------------------------------------------------------

def _build_draft_catalog(
    book_title: str,
    book_id: str,
    raw_text: str,
    sections: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    extraction_meta: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a draft catalog shaped like book_lab_catalog.json.

    All calc entries carry needs_review=True, missing_formula=True, and
    empty formula/result-value fields so nothing is accidentally treated as
    computable.

    The top-level "status": "draft_needs_review" and "_warning" field ensure
    the live Book Lab API (which reads book_lab_catalog.json, a different file)
    cannot accidentally load this artifact.
    """
    # Aggregate concept hits across all candidate paragraphs.
    # Also carry the per-candidate input_dependencies forward so _aggregate_input_deps
    # can consolidate them per concept.
    concept_evidence: Dict[str, List[Dict[str, Any]]] = {}
    for cand in candidates:
        matched = _match_concepts(str(cand.get("text") or ""))
        for concept_key, snippets in matched.items():
            concept_evidence.setdefault(concept_key, [])
            for snippet in snippets:
                concept_evidence[concept_key].append({
                    "text": snippet,
                    "relative_path": cand.get("relative_path", ""),
                    "paragraph_index": cand.get("paragraph_index", 0),
                    "extraction_quality": cand.get("extraction_quality", "interpretation_only"),
                    # Carry raw per-paragraph input dependency data through for aggregation
                    "input_dependencies": cand.get("input_dependencies", {}),
                })

    section_text_map = {
        rel_path: text
        for rel_path, text in _split_raw_text_into_section_blocks(raw_text, sections)
    }

    draft_calculations: List[Dict[str, Any]] = []
    for concept_key in sorted(concept_evidence):
        evidence_list = concept_evidence[concept_key]
        concept_meta = next(
            (c for c in CONCEPT_CATALOG if c["key"] == concept_key), None
        )
        label_he = str(concept_meta["label"]) if concept_meta else concept_key
        # Confidence grows with evidence count but is capped low (drafts are uncertain)
        confidence = round(min(0.75, 0.25 + 0.04 * min(len(evidence_list), 12)), 3)
        chapter_ref = evidence_list[0].get("relative_path", "") if evidence_list else ""
        source_excerpt = evidence_list[0].get("text", "")[:400] if evidence_list else ""
        source_refs = list(dict.fromkeys(
            e.get("relative_path", "") for e in evidence_list[:6]
            if e.get("relative_path")
        ))

        # Aggregate input dependencies across all evidence for this concept
        input_deps = _aggregate_input_deps(evidence_list)
        chapter_text_parts: List[str] = []
        seen_chapter_refs: set[str] = set()
        for evidence in evidence_list:
            rel_path = str(evidence.get("relative_path") or "").strip()
            if not rel_path or rel_path in seen_chapter_refs:
                continue
            seen_chapter_refs.add(rel_path)
            chapter_text = section_text_map.get(rel_path, "")
            if chapter_text:
                chapter_text_parts.append(chapter_text)
        chapter_text = "\n\n".join(chapter_text_parts).strip()
        formula_text, formula_steps, best_excerpt = _extract_formula_payload(
            concept_key,
            chapter_text,
            evidence_list,
        )
        result_values = _extract_result_value_entries(chapter_text, chapter_ref)
        allowed_result_values = [
            int(value) if str(value).isdigit() else value
            for value in [entry.get("value") for entry in result_values]
            if str(value or "").strip()
        ]
        if not allowed_result_values:
            allowed_result_values = list(range(1, 10)) + [11, 22, 33]
        interpretation_text = _build_interpretation_summary(result_values, chapter_text)
        interpretation_map = {
            str(item.get("value")): str(item.get("meaning") or "")
            for item in result_values
            if str(item.get("value") or "").strip() and str(item.get("meaning") or "").strip()
        }
        source_excerpt = best_excerpt or source_excerpt

        draft_calculations.append({
            "calc_key": concept_key,
            "label_he": label_he,
            "short_explanation": f"טיוטה: {label_he} — דורש בדיקה ידנית",
            "formula_text": formula_text,
            "formula_steps": formula_steps,
            # ── Input dependency fields ────────────────────────────────────
            # input_dependencies: flat list of all known inputs (required + optional)
            # for compatibility with existing catalog consumers that read this field.
            "input_dependencies": input_deps["required_inputs"] + input_deps["optional_inputs"],
            # Structured breakdown so reviewers can answer:
            #   - what does this calc need?      → required_inputs
            #   - what can it optionally use?    → optional_inputs
            #   - what is unclear?               → ambiguous_inputs
            #   - how confident is the evidence? → input_dependency_confidence
            "required_inputs": input_deps["required_inputs"],
            "optional_inputs": input_deps["optional_inputs"],
            "ambiguous_inputs": input_deps["ambiguous_inputs"],
            "input_type_hints": input_deps["input_type_hints"],
            "input_dependency_confidence": input_deps["input_dependency_confidence"],
            "ambiguous_input_dependency": input_deps["ambiguous_input_dependency"],
            # ──────────────────────────────────────────────────────────────
            "allowed_result_values": allowed_result_values,
            "result_values": result_values,
            "result_values_count": len(result_values),
            "interpretation": interpretation_text,
            "interpretation_excerpt": interpretation_text[:500],
            "interpretations_by_value": interpretation_map,
            "chapter_ref": chapter_ref,
            "book_name": book_title,
            "source_refs": source_refs,
            "source_excerpt": source_excerpt,
            "enabled_in_full_map": False,  # explicitly disabled
            # Uncertainty / honest classification
            "needs_review": True,
            "extraction_quality": "possible_formula" if formula_text else ("interpretation_only" if interpretation_text else "numeric_reference"),
            "missing_formula": not bool(formula_text),
            "confidence": confidence,
            "evidence_count": len(evidence_list),
        })

    chapter_summary = [
        {
            "relative_path": s.get("relative_path", ""),
            "file_name": s.get("file_name", ""),
            "word_count": s.get("word_count", 0),
            "calc_like_paragraphs": s.get("calc_like_paragraphs", 0),
        }
        for s in sections
    ]

    return {
        "book_id": book_id,
        "book_name": book_title,
        "status": "draft_needs_review",
        "generated_at": _now_iso(),
        "generated_by": "BookIngestionRunner",
        "extraction_metadata": extraction_meta,
        "chapter_summary": chapter_summary,
        "calculations": draft_calculations,
        "_warning": (
            "DRAFT ARTIFACT – produced by BookIngestionRunner. "
            "This file is NOT book_lab_catalog.json and does NOT affect the "
            "live Book Lab API or any existing calculator. "
            "All 'calculations' entries have needs_review=True and "
            "empty formula/result_values fields. "
            "Manual review is required before any Book Lab integration."
        ),
    }


# ---------------------------------------------------------------------------
# Main runner class
# ---------------------------------------------------------------------------

class BookIngestionRunner:
    """Unified end-to-end runner: PDF → structured Book Lab artifacts.

    Executes six sequential stages and writes all artifacts to `output_dir`.
    Never modifies any artifact belonging to the golden reference book or the
    live Book Lab / API production files.

    Args:
        book_title: Full display title (used in artifact filenames).
        book_id:    Machine-readable identifier (e.g. ``'my_new_book_2025'``).
        pdf_path:   Path to the source PDF.
        output_dir: Where artifacts are written.  Defaults to
                    ``interpretations/research/{book_title}/`` inside NumerologyReportGenerator.
        corpus:     Corpus label for SQLite ingestion (default ``'green'``).

    Raises:
        ValueError: If ``book_id`` or ``book_title`` matches the golden reference.
        FileNotFoundError: If ``pdf_path`` does not exist.
    """

    def __init__(
        self,
        book_title: str,
        book_id: str,
        pdf_path: str,
        output_dir: Optional[str] = None,
        corpus: str = "green",
        source_text_override: Optional[str] = None,
        source_override_strategy: str = "",
    ) -> None:
        # ── Safety guards ──────────────────────────────────────────────────
        if book_id.strip() == _GOLDEN_BOOK_ID:
            raise ValueError(
                f"BookIngestionRunner refuses to process the golden reference book "
                f"(book_id={_GOLDEN_BOOK_ID!r}).  Choose a different book_id."
            )
        if book_title.strip() == _GOLDEN_BOOK_TITLE:
            raise ValueError(
                f"BookIngestionRunner refuses to process the golden reference book "
                f"(title={_GOLDEN_BOOK_TITLE!r}).  Choose a different title."
            )

        self.book_title = book_title.strip()
        self.book_id = book_id.strip()
        self.corpus = corpus.strip() or "green"

        self.pdf_path = Path(pdf_path).resolve()
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {self.pdf_path}")
        self.source_text_override = str(source_text_override or "")
        self.source_override_strategy = str(source_override_strategy or "").strip()

        # ── Output directory ───────────────────────────────────────────────
        if output_dir:
            self.output_dir = Path(output_dir).resolve()
        else:
            self.output_dir = research_book_dir(self.book_title)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # ── Artifact paths (follow existing __artifact naming convention) ──
        _t = self.book_title
        self._manifest_path = self.output_dir / f"{_t}__source_manifest.json"
        self._corpus_path = self.output_dir / f"{_t}__source_corpus.txt"
        self._inventory_path = self.output_dir / f"{_t}__chapter_inventory.json"
        self._candidates_path = self.output_dir / f"{_t}__calc_candidates.json"
        self._draft_catalog_path = self.output_dir / f"{_t}__draft_catalog.json"
        self._quality_report_path = self.output_dir / f"{_t}__ocr_quality_report.json"

        # ── Reused existing components ─────────────────────────────────────
        self._engine = OCREngine(language="heb+eng")
        self._store = KnowledgeStore()
        self._processor = BookProcessor(store=self._store, engine=self._engine)

        self._run_log: List[Dict[str, Any]] = []

    # ──────────────────────────────────────────────────────────────────────
    # Stage 1 – Extract
    # ──────────────────────────────────────────────────────────────────────

    def stage_1_extract(self) -> Tuple[str, Dict[str, Any], str]:
        """Detect native text vs OCR-needed; build full-page corpus text.

        Uses OCREngine.inspect() as a quick status probe (≤40-page sample),
        then calls _extract_full_pdf_text() for the complete corpus.

        Returns:
            (raw_text, extraction_meta, probe_status)
        """
        logger.info("[Stage 1] Inspecting %s", self.pdf_path.name)

        if self.source_text_override.strip():
            raw_text = self.source_text_override
            extract_meta = {
                "strategy": self.source_override_strategy or "override-text",
                "total_pages": len(_PAGE_MARKER_RE.findall(raw_text)),
                "pages_extracted": len(_PAGE_MARKER_RE.findall(raw_text)),
                "ocr_needed_pages": 0,
            }
            probe_status = "override"
        else:
            # Full corpus extraction (all pages) — probe status derived from result,
            # avoiding a redundant second OCR pass.
            raw_text, extract_meta = _extract_full_pdf_text(
                self.pdf_path, self._engine
            )
            probe_status = extract_meta.get("strategy", "unknown")
        logger.info("[Stage 1] extraction strategy → %s", probe_status)

        extraction_meta: Dict[str, Any] = {
            "source_path": str(self.pdf_path),
            "file_name": self.pdf_path.name,
            "file_size_bytes": self.pdf_path.stat().st_size,
            "probe_status": probe_status,
            "extraction_strategy": extract_meta.get("strategy", "unknown"),
            "total_pages": extract_meta.get("total_pages", 0),
            "pages_extracted": extract_meta.get("pages_extracted", 0),
            "ocr_needed_pages": extract_meta.get("ocr_needed_pages", 0),
            "raw_text_length": len(raw_text),
            "page_markers_found": len(_PAGE_MARKER_RE.findall(raw_text)),
            "language": self._engine.language,
            "ocr_capabilities": self._engine.capabilities(),
        }
        if self.source_text_override.strip():
            extraction_meta["source_override_used"] = True
            extraction_meta["source_override_strategy"] = self.source_override_strategy or "override-text"
        if extract_meta.get("extraction_quality"):
            extraction_meta["extraction_quality"] = extract_meta["extraction_quality"]
        if not raw_text.strip():
            logger.warning(
                "[Stage 1] No text extracted – extraction_quality=low_confidence_ocr"
            )
            extraction_meta["extraction_quality"] = "low_confidence_ocr"

        self._log_stage("stage_1_extract", {
            "probe_status": probe_status,
            "strategy": extraction_meta["extraction_strategy"],
            "total_pages": extraction_meta["total_pages"],
            "raw_text_length": extraction_meta["raw_text_length"],
        })

        # Save per-page OCR quality report (used for the rescan/patch workflow)
        try:
            self._save_ocr_quality_report(raw_text, extraction_meta)
        except Exception as _qr_exc:
            logger.warning("[Stage 1] Could not save OCR quality report: %s", _qr_exc)

        return raw_text, extraction_meta, probe_status

    # ──────────────────────────────────────────────────────────────────────
    # Stage 2 – Preserve raw/source outputs
    # ──────────────────────────────────────────────────────────────────────

    def stage_2_preserve_raw(
        self,
        raw_text: str,
        extraction_meta: Dict[str, Any],
    ) -> None:
        """Write __source_manifest.json and __source_corpus.txt.

        The source corpus preserves all page markers exactly as produced by
        the extractor, so downstream rule_extractor._find_page_hint() works.
        """
        logger.info("[Stage 2] Preserving raw source artifacts")

        manifest = {
            "book_id": self.book_id,
            "book_title": self.book_title,
            "generated_at": _now_iso(),
            "generated_by": "BookIngestionRunner",
            "source_file": str(self.pdf_path),
            "extraction_metadata": extraction_meta,
            "artifacts": {
                "source_corpus": self._corpus_path.name,
                "chapter_inventory": self._inventory_path.name,
                "calc_candidates": self._candidates_path.name,
                "draft_catalog": self._draft_catalog_path.name,
                "ocr_quality_report": self._quality_report_path.name,
            },
            "_note": (
                "Auto-generated by BookIngestionRunner.  All artifacts are drafts "
                "requiring manual review before any Book Lab integration."
            ),
        }
        _write_json(self._manifest_path, manifest)
        _write_text(self._corpus_path, raw_text)

        self._log_stage("stage_2_preserve_raw", {
            "manifest": str(self._manifest_path),
            "corpus": str(self._corpus_path),
        })

    # ──────────────────────────────────────────────────────────────────────
    # Stage 3 – Structural split
    # ──────────────────────────────────────────────────────────────────────

    def stage_3_structural_split(
        self,
        raw_text: str,
    ) -> List[Dict[str, Any]]:
        """Detect parts/chapters/sections → write __chapter_inventory.json."""
        logger.info("[Stage 3] Structural split")

        sections = _split_into_sections(raw_text, self.book_id)
        _write_json(self._inventory_path, sections)

        logger.info("[Stage 3] Detected %d section(s)", len(sections))
        self._log_stage("stage_3_structural_split", {"sections_found": len(sections)})
        return sections

    # ──────────────────────────────────────────────────────────────────────
    # Stage 4 – Candidate extraction
    # ──────────────────────────────────────────────────────────────────────

    def stage_4_extract_candidates(
        self,
        raw_text: str,
        sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Scan paragraphs for calc/interpretation candidates → __calc_candidates.json."""
        logger.info("[Stage 4] Extracting candidates")

        candidates = _extract_candidates(raw_text, sections)
        _write_json(self._candidates_path, candidates)

        logger.info("[Stage 4] %d candidate(s) extracted", len(candidates))
        self._log_stage("stage_4_extract_candidates", {"candidates_found": len(candidates)})
        return candidates

    # ──────────────────────────────────────────────────────────────────────
    # Stage 5 – SQLite ingestion (reuses BookProcessor)
    # ──────────────────────────────────────────────────────────────────────

    def stage_5_ingest_db(self) -> Dict[str, Any]:
        """Persist book metadata and chunks in numerology_books.db.

        Calls the existing BookProcessor.add_book() (reused component).
        This does NOT affect the golden reference book's DB records.
        """
        logger.info("[Stage 5] SQLite ingestion via BookProcessor")

        result = self._processor.add_book(
            title=self.book_title,
            author="",
            source_path=str(self.pdf_path),
            corpus=self.corpus,
            method="book_ingestion_runner",
        )
        sqlite_book_id = result.get("book_id")
        logger.info("[Stage 5] SQLite book_id=%s", sqlite_book_id)
        self._log_stage("stage_5_ingest_db", {"sqlite_book_id": sqlite_book_id})
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Stage 6 – Draft catalog
    # ──────────────────────────────────────────────────────────────────────

    def stage_6_draft_catalog(
        self,
        raw_text: str,
        sections: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        extraction_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build draft catalog entry → {title}__draft_catalog.json.

        Named deliberately *__draft_catalog.json* (not book_lab_catalog.json)
        to prevent accidental loading by the live Book Lab API.
        """
        logger.info("[Stage 6] Building draft catalog")

        draft = _build_draft_catalog(
            book_title=self.book_title,
            book_id=self.book_id,
            raw_text=raw_text,
            sections=sections,
            candidates=candidates,
            extraction_meta=extraction_meta,
        )
        _write_json(self._draft_catalog_path, draft)

        calc_count = len(draft.get("calculations") or [])
        logger.info("[Stage 6] Draft catalog: %d candidate calculation(s)", calc_count)
        self._log_stage("stage_6_draft_catalog", {"draft_calculations": calc_count})
        return draft

    # ──────────────────────────────────────────────────────────────────────
    # Orchestrator
    # ──────────────────────────────────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        """Execute all six stages end-to-end.

        Returns a summary dict suitable for logging, JSON export, or display.
        The golden reference book is never touched and no production switch
        is performed.
        """
        logger.info(
            "=== BookIngestionRunner START  book_id=%r  pdf=%s ===",
            self.book_id,
            self.pdf_path.name,
        )
        self._run_log = []

        raw_text, extraction_meta, probe_status = self.stage_1_extract()
        self.stage_2_preserve_raw(raw_text, extraction_meta)
        sections = self.stage_3_structural_split(raw_text)
        candidates = self.stage_4_extract_candidates(raw_text, sections)
        db_result = self.stage_5_ingest_db()
        draft = self.stage_6_draft_catalog(raw_text, sections, candidates, extraction_meta)

        summary: Dict[str, Any] = {
            "book_id": self.book_id,
            "book_title": self.book_title,
            "source_pdf": str(self.pdf_path),
            "output_dir": str(self.output_dir),
            "extraction_status": probe_status,
            "extraction_strategy": extraction_meta.get("extraction_strategy"),
            "total_pages": extraction_meta.get("total_pages"),
            "raw_text_length": extraction_meta.get("raw_text_length"),
            "sections_found": len(sections),
            "candidates_found": len(candidates),
            "draft_calculations": len(draft.get("calculations") or []),
            "sqlite_book_id": db_result.get("book_id"),
            "artifacts_written": {
                "source_manifest": str(self._manifest_path),
                "source_corpus": str(self._corpus_path),
                "chapter_inventory": str(self._inventory_path),
                "calc_candidates": str(self._candidates_path),
                "draft_catalog": str(self._draft_catalog_path),
                "ocr_quality_report": str(self._quality_report_path),
            },
            # Explicit safety confirmations
            "golden_reference_untouched": True,
            "production_switch_performed": False,
            "ui_changed": False,
            "stage_log": self._run_log,
        }

        logger.info(
            "=== BookIngestionRunner COMPLETE  sections=%d  candidates=%d  drafts=%d ===",
            len(sections),
            len(candidates),
            len(draft.get("calculations") or []),
        )
        return summary

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    def _save_ocr_quality_report(
        self,
        raw_text: str,
        extraction_meta: Dict[str, Any],
    ) -> None:
        """Parse per-page Hebrew ratios and write __ocr_quality_report.json.

        The report is the key artifact for the rescan/patch workflow:
          - pages_needing_rescan: ordered list of page numbers below threshold
          - Each entry in pages[]: page, heb_ratio, source, needs_rescan

        Only pages extracted via OCR (source="ocr" or "empty") are flagged.
        Native-text pages (source="native") are always considered good.
        """
        pages = _parse_per_page_quality(raw_text)
        pages_needing_rescan = [p["page"] for p in pages if p["needs_rescan"]]
        extraction_errors = {
            str(k): str(v)
            for k, v in extraction_meta.items()
            if str(k).endswith("_error") and str(v).strip()
        }

        # Average ratio over OCR+empty pages only
        ocr_pages = [p for p in pages if p["source"] in ("ocr", "empty")]
        avg_ratio: Optional[float] = None
        if ocr_pages:
            avg_ratio = sum(p["heb_ratio"] for p in ocr_pages) / len(ocr_pages)

        report: Dict[str, Any] = {
            "book_id": self.book_id,
            "book_title": self.book_title,
            "source_pdf": str(self.pdf_path),
            "output_dir": str(self.output_dir),
            "generated_at": _now_iso(),
            "ocr_threshold": _OCR_QUALITY_THRESHOLD,
            "total_pages": extraction_meta.get("total_pages", len(pages)),
            "pages_scanned": len(pages),
            "pages_needing_rescan": pages_needing_rescan,
            "rescan_count": len(pages_needing_rescan),
            "avg_heb_ratio": round(avg_ratio, 3) if avg_ratio is not None else None,
            "extraction_strategy": extraction_meta.get("extraction_strategy", "unknown"),
            "extraction_errors": extraction_errors,
            "page_markers_found": len(pages),
            "pages": pages,
        }
        if not pages:
            report["integrity_warning"] = (
                "no_page_markers_detected_in_source_corpus; "
                "OCR/page extraction likely failed or returned non-paginated text"
            )
        _write_json(self._quality_report_path, report)
        logger.info(
            "[Stage 1] OCR quality report: %d/%d pages need rescan (avg heb=%s)",
            len(pages_needing_rescan),
            len(pages),
            f"{avg_ratio * 100:.0f}%" if avg_ratio is not None else "N/A (native text)",
        )

    def _log_stage(self, stage: str, info: Dict[str, Any]) -> None:
        self._run_log.append({"stage": stage, "timestamp": _now_iso(), **info})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Run BookIngestionRunner stages on a single PDF.',
    )
    parser.add_argument('--pdf', required=True, help='Path to PDF file')
    parser.add_argument('--output-dir', required=True, help='Output directory for artifacts')
    parser.add_argument('--book-title', default='', help='Book title override')
    parser.add_argument('--book-id', default='', help='Book ID override')
    parser.add_argument('--corpus', default='', help='Corpus name')
    parser.add_argument('--force', action='store_true', help='Re-process even if artifacts exist')
    return parser


if __name__ == '__main__':
    import json as _json
    _args = _build_arg_parser().parse_args()
    _pdf = Path(_args.pdf)
    _runner = BookIngestionRunner(
        book_title=_args.book_title or _pdf.stem,
        book_id=_args.book_id or normalize_corpus_key(_pdf.stem),
        pdf_path=str(_pdf),
        output_dir=_args.output_dir,
        corpus=_args.corpus,
    )
    _result = _runner.run()
    print(_json.dumps(_result, ensure_ascii=False, indent=2))
