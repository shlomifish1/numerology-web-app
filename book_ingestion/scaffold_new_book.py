"""scaffold_new_book.py — MVP book onboarding scaffold.

Phase A  (--phase A):
    Inspect source path, detect file grouping, print a preview.
    Writes NOTHING.  Asks the user if grouping is ambiguous.

Phase B  (--phase B):
    Detect grouping (same logic as Phase A), show the full write preview,
    ask for confirmation, then:
      1. Merge split-book PDFs into one combined source (if fitz is available).
      2. Run BookIngestionRunner → 5 ingestion artifacts.
      3. Read the produced __draft_catalog.json.
      4. Write 3 review-artifact stubs (reviewed_catalog, definition_candidate,
         review_report) whose entry count matches the draft, NOT a fixed number.

Phases C/D/E/F are NOT implemented in this MVP.

Safety guarantees:
  - golden reference book IDs and title are hard-blocked
  - green_legacy ID is hard-blocked
  - registry.py is NEVER written
  - book_lab_catalog.json is NEVER written
  - no calculator .py is created
  - no book_calculations/*.definition.json is created
  - DEFAULT_CALCULATOR_ID remains "green_legacy"

CLI:
    python scaffold_new_book.py \\
        --source     <file_or_folder> \\
        --book-name-he  <Hebrew title> \\
        --calculator-id <snake_case_id> \\
        [--phase A|B]           (default: A)
        [--outdir  <path>]
        [--skip-db]
        [--dry-run]
        [--yes]
        [--verbose]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path bootstrap — mirrors the same pattern used in book_ingestion_runner.py
# ---------------------------------------------------------------------------

_SCAFFOLD_FILE  = Path(__file__).resolve()
_INGESTION_DIR  = _SCAFFOLD_FILE.parent           # .../book_ingestion/
_NRG_DIR        = _INGESTION_DIR.parent           # .../NumerologyReportGenerator/
_PROJECT_ROOT   = _NRG_DIR.parent                 # .../ai_agents/
_OCR_DIR        = _PROJECT_ROOT / "ocr"

for _p in (_PROJECT_ROOT, _NRG_DIR, _OCR_DIR, str(_INGESTION_DIR)):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------

from book_ingestion.grouping_detector import (  # noqa: E402
    GroupingResult,
    BookCandidate,
    detect_grouping,
    force_one_split_book,
    force_multiple_books,
    _collect_pdfs,
)
from interpretation_layout import research_book_dir  # noqa: E402

# BookIngestionRunner is imported lazily in phase_b() so that Phase A works
# even if some optional dependency (fitz, etc.) is missing.

# ---------------------------------------------------------------------------
# Safety constants
# ---------------------------------------------------------------------------

_GOLDEN_IDS: frozenset[str] = frozenset({
    "green_legacy",
    "sefer_hanumerologia_hashalem",
    "sifur_hanumerology_hashalem",
})
_GOLDEN_TITLES: frozenset[str] = frozenset({"ספר הנומרולוגיה השלם"})
_VALID_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _write_json(path: Path, data: Any, *, dry_run: bool, verbose: bool) -> None:
    if dry_run:
        print(f"  [DRY-RUN] WOULD WRITE: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    if verbose:
        print(f"  WROTE: {path}")


def _confirm(prompt: str, default_yes: bool = False, auto_yes: bool = False) -> bool:
    """Ask Y/n.  Returns True if user confirms."""
    if auto_yes:
        print(f"{prompt} [auto-yes]")
        return True
    suffix = " [Y/n]: " if default_yes else " [y/N]: "
    try:
        answer = input(prompt + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)
    if default_yes:
        return answer not in {"n", "no"}
    return answer in {"y", "yes"}


def _ask_grouping_choice(result: GroupingResult) -> str:
    """Ask the user to resolve an AMBIGUOUS grouping.  Returns '1' or '2'."""
    print()
    print("┌" + "─" * 64 + "┐")
    print("│  GROUPING AMBIGUOUS — clarification required               │")
    print("├" + "─" * 64 + "┤")
    print(f"│  Folder: {str(result.source_path):<54} │")
    print(f"│  PDFs found: {result.pdf_count:<50} │")
    print("│  Files:                                                    │")
    for f in _collect_pdfs(result.source_path):
        truncated = f.name[:54]
        print(f"│    - {truncated:<58} │")
    print("│                                                            │")
    print("│  Is this folder:                                           │")
    print("│    [1] One book split into multiple files                  │")
    print("│    [2] Multiple separate books                             │")
    print("└" + "─" * 64 + "┘")
    while True:
        try:
            answer = input("  Enter 1 or 2 (or Ctrl+C to abort): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)
        if answer in {"1", "2"}:
            return answer
        print("  Please enter 1 or 2.")


def _safety_check(calculator_id: str, book_name_he: str) -> None:
    """Abort with a clear error if any safety guard fires."""
    if not calculator_id:
        _die("--calculator-id is required.")
    if not book_name_he:
        _die("--book-name-he is required.")
    if not _VALID_ID_RE.match(calculator_id):
        _die(
            f"calculator_id {calculator_id!r} is invalid. "
            "Use lowercase letters, digits, and underscores only. "
            "Must start with a letter."
        )
    if calculator_id in _GOLDEN_IDS:
        _die(
            f"calculator_id {calculator_id!r} is protected "
            "(golden reference or production default). Choose a different ID."
        )
    if book_name_he in _GOLDEN_TITLES:
        _die(
            f"book_name_he {book_name_he!r} is the golden reference title. "
            "Choose a different title."
        )


def _die(message: str) -> None:
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Preview printer
# ---------------------------------------------------------------------------

def _print_grouping_preview(
    result:         GroupingResult,
    book_name_he:   str,
    calculator_id:  str,
    outdir:         Optional[Path],
) -> None:
    """Print a human-readable preview of the detected grouping and planned output."""
    print()
    print("=" * 68)
    print("  GROUPING RESULT")
    print("=" * 68)
    print(f"  Source path  : {result.source_path}")
    print(f"  PDFs found   : {result.pdf_count}")
    print(f"  Decision     : {result.case}")
    print(f"  Confidence   : {result.confidence:.2f}")
    print()

    if result.signals:
        print("  Positive signals detected:")
        for s in result.signals:
            print(f"    ✓ {s}")
    if result.anti_signals:
        print("  Anti-signals detected:")
        for s in result.anti_signals:
            print(f"    ✗ {s}")
    print()

    if result.case in {"SINGLE_FILE", "ONE_SPLIT_BOOK"} and result.books:
        book = result.books[0]
        print(f"  Book         : {book_name_he}")
        print(f"  Calculator ID: {calculator_id}")
        resolved_outdir = outdir or research_book_dir(book_name_he)
        print(f"  Output dir   : {resolved_outdir}")
        print()
        print("  File order:")
        print(book.ordering_note)
        if book.has_unknown_order:
            print()
            print("  ⚠  WARNING: one or more files have no extractable page number.")
            print("     Verify the order above before proceeding.")

    elif result.case == "MULTIPLE_BOOKS":
        print(f"  {len(result.books)} book candidate(s) detected:")
        for i, book in enumerate(result.books, 1):
            print(f"    Book {i}: {book.suggested_name}")
            for f in book.files:
                print(f"      - {f.name}")

    print()


def _print_phase_b_write_preview(
    book_name_he:  str,
    calculator_id: str,
    outdir:        Path,
    source_files:  List[Path],
    will_merge:    bool,
) -> None:
    """Print exact list of files that Phase B will write before asking for confirmation."""
    t = book_name_he
    print()
    print("=" * 68)
    print("  PHASE B — FILES THAT WILL BE WRITTEN")
    print("=" * 68)
    print(f"  Book         : {book_name_he}")
    print(f"  Calculator ID: {calculator_id}")
    print(f"  Output dir   : {outdir}")
    print()

    if will_merge and len(source_files) > 1:
        print("  Source files (will be merged in this order):")
        for i, f in enumerate(source_files, 1):
            print(f"    {i}. {f.name}")
        merged_name = f"{t}__merged_source.pdf"
        print(f"  → Merged PDF (temporary): {outdir / merged_name}")
    else:
        print(f"  Source file: {source_files[0].name}")
    print()

    print("  Ingestion artifacts (written by BookIngestionRunner):")
    for suffix in [
        "__source_manifest.json",
        "__source_corpus.txt",
        "__chapter_inventory.json",
        "__calc_candidates.json",
        "__draft_catalog.json",
    ]:
        print(f"    {outdir / (t + suffix)}")
    print()

    print("  Review artifact stubs (written by scaffold — awaiting human review):")
    for suffix in [
        "__reviewed_catalog.json",
        "__definition_candidate.json",
        "__review_report.json",
    ]:
        print(f"    {outdir / (t + suffix)}")
    print()

    print("  NOT written:")
    print("    ✗ registry.py")
    print("    ✗ book_lab_catalog.json")
    print("    ✗ calculators/<id>.py")
    print("    ✗ book_calculations/<id>.definition.json")
    print()


# ---------------------------------------------------------------------------
# PDF merger (fitz-based, optional)
# ---------------------------------------------------------------------------

def _try_merge_pdfs(files: List[Path], dest: Path, verbose: bool) -> bool:
    """Merge *files* into *dest* using PyMuPDF.  Returns True on success."""
    try:
        import fitz  # type: ignore
    except ImportError:
        return False
    try:
        merged = fitz.open()
        for f in files:
            doc = fitz.open(str(f))
            merged.insert_pdf(doc)
            doc.close()
        merged.save(str(dest))
        merged.close()
        if verbose:
            print(f"  Merged {len(files)} PDFs → {dest.name}")
        return True
    except Exception as exc:
        if verbose:
            print(f"  WARNING: PDF merge failed ({exc}). Will use first file only.")
        return False


# ---------------------------------------------------------------------------
# Stub artifact writers
# ---------------------------------------------------------------------------

def _build_reviewed_catalog_stub(
    book_name_he:   str,
    calculator_id:  str,
    draft_catalog:  Dict[str, Any],
) -> Dict[str, Any]:
    """Build the reviewed_catalog stub from draft_catalog.

    Entry count = len(draft_catalog["calculations"]) — NOT hardcoded.
    """
    draft_calcs: List[Dict[str, Any]] = list(draft_catalog.get("calculations") or [])

    stub_calculations = []
    for entry in draft_calcs:
        stub_entry: Dict[str, Any] = {
            "calc_key":          entry.get("calc_key", ""),
            "label_he":          entry.get("label_he", ""),
            # ── fields the human reviewer must fill ──────────────────────
            "review_bucket":     "PENDING_HUMAN_REVIEW",
            "review_confidence": "PENDING_HUMAN_REVIEW",
            "review_notes":      "PENDING_HUMAN_REVIEW",
            # ── invariants ───────────────────────────────────────────────
            "enabled_in_full_map": False,
            "needs_review":        True,
            "formula_text":        entry.get("formula_text", ""),
            "formula_steps":       entry.get("formula_steps", []),
            "interpretation":      entry.get("interpretation", ""),
            "interpretation_excerpt": entry.get("interpretation_excerpt", ""),
            "interpretations_by_value": entry.get("interpretations_by_value", {}),
            "result_values":       entry.get("result_values", []),
            "allowed_result_values": entry.get("allowed_result_values", []),
            "input_dependencies":  entry.get("input_dependencies", []),
            "required_inputs":     entry.get("required_inputs", []),
            "optional_inputs":     entry.get("optional_inputs", []),
            "ambiguous_inputs":    entry.get("ambiguous_inputs", []),
            "chapter_ref":         entry.get("chapter_ref", ""),
            "source_refs":         entry.get("source_refs", []),
            "source_excerpt":      entry.get("source_excerpt", ""),
            "short_explanation":   entry.get("short_explanation", ""),
            # ── draft reference data (read-only for reviewer) ────────────
            "_draft_ref": {
                "evidence_count":               entry.get("evidence_count", 0),
                "input_dependency_confidence":  entry.get("input_dependency_confidence", ""),
                "required_inputs":              entry.get("required_inputs", []),
                "optional_inputs":              entry.get("optional_inputs", []),
                "ambiguous_inputs":             entry.get("ambiguous_inputs", []),
                "source_excerpt":               entry.get("source_excerpt", ""),
                "formula_text":                 entry.get("formula_text", ""),
                "formula_steps":                entry.get("formula_steps", []),
                "interpretation":               entry.get("interpretation", ""),
                "interpretations_by_value":     entry.get("interpretations_by_value", {}),
                "result_values":                entry.get("result_values", []),
                "allowed_result_values":        entry.get("allowed_result_values", []),
                "chapter_ref":                  entry.get("chapter_ref", ""),
                "source_refs":                  entry.get("source_refs", []),
                "confidence":                   entry.get("confidence", 0.0),
                "extraction_quality":           entry.get("extraction_quality", ""),
                "missing_formula":              entry.get("missing_formula", True),
                "input_type_hints":             entry.get("input_type_hints", {}),
            },
        }
        stub_calculations.append(stub_entry)

    total = len(stub_calculations)
    return {
        "_warning": (
            "REVIEWED DRAFT ARTIFACT – produced by scaffold_new_book.py (Phase B stub). "
            "All entries are PENDING_HUMAN_REVIEW. "
            "This file is NOT book_lab_catalog.json and does NOT affect the live "
            "Book Lab API or any existing calculator. "
            "Production switch NOT performed."
        ),
        "book_id":    calculator_id,
        "book_title": book_name_he,
        "review_pass": {
            "performed_at":               _now_iso(),
            "source_draft":               f"{book_name_he}__draft_catalog.json",
            "method":                     "stub_awaiting_human_review",
            "golden_reference_untouched": True,
            "production_switch_performed": False,
        },
        "book_level": {
            "primary_subject":        "PENDING_HUMAN_REVIEW",
            "subject_note":           "PENDING_HUMAN_REVIEW",
            "inherited_context_inputs": [],
            "secondary_context_inputs": [],
            "inherited_context_note": "PENDING_HUMAN_REVIEW",
            "calculation_methods":    {},
        },
        "false_positive_inputs_detected": None,
        "review_summary": {
            "total_draft_entries":                 total,
            "calculation_candidate":               0,
            "mixed_calculation_and_interpretation": 0,
            "interpretation_only":                 0,
            "ambiguous_needs_review":              0,
            "false_positive":                      0,
            "_note": (
                "Counts reflect PENDING_HUMAN_REVIEW state. "
                "Update each review_bucket, then recount."
            ),
        },
        "calculations": stub_calculations,
        "_review_instructions": [
            "1. Read __source_corpus.txt in full before classifying any entry.",
            "2. For each entry in 'calculations': set review_bucket to one of: "
               "calculation_candidate | mixed_calculation_and_interpretation | "
               "interpretation_only | ambiguous_needs_review | false_positive",
            "3. Set review_confidence to: high | medium | low",
            "4. Fill review_notes with a specific reason.",
            "5. For calculation_candidate and mixed entries: add formula_sketch, "
               "required_inputs, optional_inputs, result_values, source_excerpt.",
            "6. Set book_level.inherited_context_inputs once for the whole book.",
            "7. Update review_summary counts when review is complete.",
        ],
    }


def _build_definition_candidate_stub(
    book_name_he:  str,
    calculator_id: str,
    draft_catalog: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the definition_candidate stub.

    definition_entries is intentionally empty — filled by human after
    reviewing __reviewed_catalog.json.
    """
    draft_calcs = list(draft_catalog.get("calculations") or [])
    return {
        "_warning": (
            "DEFINITION CANDIDATE ARTIFACT – produced by scaffold_new_book.py (Phase B stub). "
            "definition_entries is empty. "
            "Fill it after completing __reviewed_catalog.json review. "
            "formula_text and formula_steps must remain empty here — "
            "they are defined in book_calculations/<id>.definition.json. "
            "Production switch NOT performed."
        ),
        "_status":    "stub_awaiting_human_review",
        "book_id":    calculator_id,
        "book_title": book_name_he,
        "review_pass": {
            "performed_at":               _now_iso(),
            "source_draft":               f"{book_name_he}__draft_catalog.json",
            "source_reviewed":            "PENDING_HUMAN_REVIEW",
            "golden_reference_untouched": True,
            "production_switch_performed": False,
        },
        "book_level_context": {
            "inherited_context_inputs": [],
            "note":                     "PENDING_HUMAN_REVIEW",
            "distinct_formulas_count":  0,
            "distinct_formulas":        [],
        },
        "definition_entries": [],
        "discovered_concepts_not_in_catalog": [],
        "_draft_entry_count": len(draft_calcs),
        "_review_todo": [
            "1. Open __reviewed_catalog.json and classify every entry.",
            "2. For each 'calculation_candidate' or 'mixed_calculation_and_interpretation' "
               "entry: create one item in definition_entries with:",
            "     definition_key, label_he, description_he,",
            "     source_methods_unified_from, formula_text_note, formula_steps_note,",
            "     open_questions, required_inputs, optional_inputs,",
            "     result_values, interpretation_table, source_excerpt.",
            "   formula_text and formula_steps MUST remain empty here.",
            "3. If the book contains formulas not in CONCEPT_CATALOG,",
            "   document them in discovered_concepts_not_in_catalog.",
            "4. Set book_level_context.inherited_context_inputs.",
            "5. Set book_level_context.distinct_formulas_count and distinct_formulas.",
        ],
    }


def _build_review_report_stub(
    book_name_he:   str,
    calculator_id:  str,
    draft_catalog:  Dict[str, Any],
    manifest:       Dict[str, Any],
) -> Dict[str, Any]:
    """Build the review_report stub.

    Populates extraction metadata from the manifest.
    All human-authored sections are PENDING_HUMAN_REVIEW.
    total_entries reflects actual draft count, NOT a fixed number.
    """
    extraction_meta = manifest.get("extraction_metadata") or {}
    draft_calcs = list(draft_catalog.get("calculations") or [])
    total = len(draft_calcs)

    return {
        "_type":    "review_report",
        "_warning": (
            "REVIEW REPORT ARTIFACT – produced by scaffold_new_book.py (Phase B stub). "
            "Informational only. Does not affect the live Book Lab API, "
            "any existing calculator, or the golden reference book."
        ),
        "_status":    "stub_awaiting_human_review",
        "book_id":    calculator_id,
        "book_title": book_name_he,
        "review_pass": {
            "performed_at":               _now_iso(),
            "source_draft":               f"{book_name_he}__draft_catalog.json",
            "ingestion_runner_version":    "BookIngestionRunner v1",
            "extraction_strategy_used":   extraction_meta.get("extraction_strategy", "unknown"),
            "pages_extracted":            extraction_meta.get("pages_extracted", 0),
            "raw_text_length":            extraction_meta.get("raw_text_length", 0),
            "golden_reference_untouched": True,
            "production_switch_performed": False,
            "artifacts_produced": [
                f"{book_name_he}__reviewed_catalog.json",
                f"{book_name_he}__definition_candidate.json",
                f"{book_name_he}__review_report.json",
            ],
        },
        "book_content_summary": {
            "subject":   "PENDING_HUMAN_REVIEW",
            "author":    "PENDING_HUMAN_REVIEW",
            "pages":     extraction_meta.get("total_pages", 0),
            "structure": "PENDING_HUMAN_REVIEW",
            "key_formulas": [],
            "interpretation_content": {
                "covers_values":    [],
                "per_value_sections": [],
                "coverage":         "PENDING_HUMAN_REVIEW",
            },
        },
        "draft_catalog_classification": {
            "total_entries": total,
            "_note":         "PENDING_HUMAN_REVIEW — fill after completing reviewed_catalog.json",
            "by_bucket": {
                "calculation_candidate":               {"count": 0, "keys": []},
                "mixed_calculation_and_interpretation": {"count": 0, "keys": []},
                "interpretation_only":                  {"count": 0, "keys": []},
                "ambiguous_needs_review":               {"count": 0, "keys": []},
                "false_positive": {
                    "count": 0,
                    "keys":  [],
                    "breakdown": {
                        "zero_evidence_entries":      0,
                        "zero_evidence_keys":         [],
                        "low_evidence_false_concepts": 0,
                        "low_evidence_breakdown":     {},
                    },
                },
            },
        },
        "false_positive_inputs_report": {
            "total_false_positive_inputs_detected": 0,
            "details": [],
        },
        "input_dependency_normalization": {
            "book_level_inputs":   {},
            "normalized_decision": "PENDING_HUMAN_REVIEW",
        },
        "discovery_notes":        [],
        "recommended_next_steps": [
            {
                "step":        1,
                "priority":    "high",
                "action":      "Review __reviewed_catalog.json — classify every entry",
                "responsible": "human reviewer",
            },
            {
                "step":        2,
                "priority":    "high",
                "action":      "Fill __definition_candidate.json with calculation_candidate entries",
                "responsible": "human reviewer",
            },
            {
                "step":        3,
                "priority":    "high",
                "action":      "Complete review_report.json — book_content_summary and "
                               "draft_catalog_classification",
                "responsible": "human reviewer",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Phase A
# ---------------------------------------------------------------------------

def phase_a(
    source:         Path,
    book_name_he:   str,
    calculator_id:  str,
    outdir:         Optional[Path],
) -> None:
    """Phase A: inspect source, detect grouping, print preview.  Writes nothing."""
    print()
    print("=" * 68)
    print("  scaffold_new_book.py  —  Phase A: Inspect")
    print("=" * 68)

    result = detect_grouping(source)

    # Resolve ambiguity interactively if needed
    if result.needs_user_input:
        answer = _ask_grouping_choice(result)
        if answer == "1":
            result = force_one_split_book(source)
        else:
            result = force_multiple_books(source)

    _print_grouping_preview(result, book_name_he, calculator_id, outdir)

    # Print next-step hint
    if result.case in {"SINGLE_FILE", "ONE_SPLIT_BOOK"}:
        print("  Next step → run Phase B:")
        id_safe   = calculator_id or "<calculator_id>"
        name_safe = book_name_he  or "<book_name_he>"
        source_q  = f'"{source}"'
        print(f"    python scaffold_new_book.py \\")
        print(f"        --source {source_q} \\")
        print(f'        --book-name-he "{name_safe}" \\')
        print(f'        --calculator-id "{id_safe}" \\')
        print(f"        --phase B")
        print()
    elif result.case == "MULTIPLE_BOOKS":
        print(f"  Detected {len(result.books)} separate books.")
        print("  Run Phase B separately for each book, using a distinct --calculator-id.")
        print()


# ---------------------------------------------------------------------------
# Phase B
# ---------------------------------------------------------------------------

def phase_b(
    source:         Path,
    book_name_he:   str,
    calculator_id:  str,
    outdir:         Optional[Path],
    skip_db:        bool,
    dry_run:        bool,
    auto_yes:       bool,
    verbose:        bool,
) -> None:
    """Phase B: detect grouping → preview → confirm → run ingestion → write stubs."""

    # ── Detect grouping ───────────────────────────────────────────────────
    result = detect_grouping(source)

    if result.needs_user_input:
        answer = _ask_grouping_choice(result)
        if answer == "1":
            result = force_one_split_book(source)
        else:
            result = force_multiple_books(source)

    # Phase B only processes ONE book at a time
    if result.case == "MULTIPLE_BOOKS":
        _die(
            "Phase B detected multiple books in this folder. "
            "Run Phase B separately for each book. "
            "Use Phase A first to identify the grouping."
        )

    book_candidate: BookCandidate = result.books[0]
    source_files: List[Path] = book_candidate.files

    # ── Resolve output directory ──────────────────────────────────────────
    resolved_outdir: Path = (
        outdir if outdir else research_book_dir(book_name_he)
    )

    # ── Check for PDF merge capability ───────────────────────────────────
    needs_merge = len(source_files) > 1
    can_fitz    = False
    if needs_merge:
        try:
            import fitz  # type: ignore  # noqa: F401
            can_fitz = True
        except ImportError:
            pass

    # ── Print full write preview ──────────────────────────────────────────
    _print_grouping_preview(result, book_name_he, calculator_id, resolved_outdir)
    _print_phase_b_write_preview(
        book_name_he, calculator_id, resolved_outdir,
        source_files, will_merge=(needs_merge and can_fitz)
    )

    if needs_merge and not can_fitz:
        print(
            "  ⚠  WARNING: PyMuPDF (fitz) not available — cannot merge split PDFs.\n"
            "     Will process the first file only.\n"
            f"     First file: {source_files[0].name}"
        )
        print()

    # ── Dry-run: list what would be written and exit ──────────────────────
    if dry_run:
        print("  [DRY-RUN] No files will be written.  Exiting.")
        print()
        return

    # ── Confirmation prompt ───────────────────────────────────────────────
    if not _confirm("  Proceed with Phase B?", default_yes=False, auto_yes=auto_yes):
        print("  Aborted.")
        sys.exit(0)
    print()

    # ── Idempotency check ─────────────────────────────────────────────────
    reviewed_catalog_path = resolved_outdir / f"{book_name_he}__reviewed_catalog.json"
    if reviewed_catalog_path.exists() and not auto_yes:
        print(f"  Review artifacts already exist in: {resolved_outdir}")
        if not _confirm(
            "  Re-generate and overwrite existing review artifacts?",
            default_yes=False, auto_yes=auto_yes
        ):
            print("  Aborted.")
            sys.exit(0)
        print()

    # ── Determine single PDF path for BookIngestionRunner ─────────────────
    merged_pdf_path: Optional[Path] = None
    if needs_merge and can_fitz:
        resolved_outdir.mkdir(parents=True, exist_ok=True)
        merged_name = f"{book_name_he}__merged_source.pdf"
        merged_pdf_path = resolved_outdir / merged_name
        success = _try_merge_pdfs(source_files, merged_pdf_path, verbose)
        if not success:
            print(
                f"  WARNING: PDF merge failed. Falling back to first file: "
                f"{source_files[0].name}"
            )
            merged_pdf_path = None
    pdf_to_use: Path = (
        merged_pdf_path if merged_pdf_path is not None else source_files[0]
    )

    # ── Run BookIngestionRunner ───────────────────────────────────────────
    print("  Running BookIngestionRunner...")
    try:
        from book_ingestion.book_ingestion_runner import BookIngestionRunner  # noqa: E402
    except ImportError as exc:
        _die(f"Cannot import BookIngestionRunner: {exc}")

    runner = BookIngestionRunner(
        book_title = book_name_he,
        book_id    = calculator_id,
        pdf_path   = str(pdf_to_use),
        output_dir = str(resolved_outdir),
    )

    # Patch skip_db: if skip_db, monkey-patch stage_5 to a no-op for this run
    if skip_db:
        runner.stage_5_ingest_db = lambda: {"skipped": True}  # type: ignore
        if verbose:
            print("  DB ingestion skipped (--skip-db).")

    try:
        run_summary = runner.run()
    except Exception as exc:
        _die(f"BookIngestionRunner failed: {exc}")

    if verbose:
        print(f"  Ingestion complete. Summary: {json.dumps(run_summary, ensure_ascii=False)}")

    # ── Quality gates (warn, do not abort) ────────────────────────────────
    corpus_path = resolved_outdir / f"{book_name_he}__source_corpus.txt"
    if corpus_path.exists():
        corpus_len = len(corpus_path.read_text(encoding="utf-8", errors="replace"))
        if corpus_len < 3000:
            print(
                f"  ⚠  WARNING: Source corpus is very short ({corpus_len} chars). "
                "Extraction may be incomplete."
            )
    else:
        print("  ⚠  WARNING: __source_corpus.txt was not produced.")

    draft_path = resolved_outdir / f"{book_name_he}__draft_catalog.json"
    if not draft_path.exists():
        _die(f"__draft_catalog.json was not produced at {draft_path}")

    draft_catalog = json.loads(draft_path.read_text(encoding="utf-8"))
    draft_calcs   = list(draft_catalog.get("calculations") or [])
    total_draft   = len(draft_calcs)

    if total_draft == 0:
        print(
            "  ⚠  WARNING: draft_catalog has 0 calculation entries. "
            "Review the corpus — the book may not have matched any concept patterns."
        )
    else:
        meaningful = sum(1 for c in draft_calcs if int(c.get("evidence_count", 0)) > 0)
        print(
            f"  Draft catalog: {total_draft} entries "
            f"({meaningful} with evidence > 0)"
        )

    # ── Read manifest for review_report stub ─────────────────────────────
    manifest_path = resolved_outdir / f"{book_name_he}__source_manifest.json"
    manifest: Dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # ── Write 3 review-artifact stubs ────────────────────────────────────
    print("  Writing review artifact stubs...")

    reviewed_stub = _build_reviewed_catalog_stub(book_name_he, calculator_id, draft_catalog)
    _write_json(
        resolved_outdir / f"{book_name_he}__reviewed_catalog.json",
        reviewed_stub, dry_run=False, verbose=verbose,
    )

    def_candidate_stub = _build_definition_candidate_stub(book_name_he, calculator_id, draft_catalog)
    _write_json(
        resolved_outdir / f"{book_name_he}__definition_candidate.json",
        def_candidate_stub, dry_run=False, verbose=verbose,
    )

    report_stub = _build_review_report_stub(book_name_he, calculator_id, draft_catalog, manifest)
    _write_json(
        resolved_outdir / f"{book_name_he}__review_report.json",
        report_stub, dry_run=False, verbose=verbose,
    )

    # ── Final summary ─────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("  Phase B complete.")
    print("=" * 68)
    print(f"  Book           : {book_name_he}")
    print(f"  Calculator ID  : {calculator_id}")
    print(f"  Output dir     : {resolved_outdir}")
    print(f"  Draft entries  : {total_draft}  (NOT hardcoded — reflects actual draft)")
    print()
    print("  Artifacts written:")
    for suffix in [
        "__source_manifest.json",
        "__source_corpus.txt",
        "__chapter_inventory.json",
        "__calc_candidates.json",
        "__draft_catalog.json",
        "__reviewed_catalog.json",
        "__definition_candidate.json",
        "__review_report.json",
    ]:
        p = resolved_outdir / (book_name_he + suffix)
        status = "✓" if p.exists() else "✗ MISSING"
        print(f"    {status}  {p.name}")
    print()
    print("  NOT written:")
    print("    ✗ registry.py")
    print("    ✗ book_lab_catalog.json")
    print("    ✗ calculators/<id>.py")
    print("    ✗ book_calculations/<id>.definition.json")
    print()
    print("  Next step: open __reviewed_catalog.json and classify each entry.")
    print("  Search for 'PENDING_HUMAN_REVIEW' to find all unfilled fields.")
    print()
    print("  Confirmations:")
    print("    golden_reference_untouched  = True")
    print("    production_switch_performed = False")
    print("    DEFAULT_CALCULATOR_ID       = green_legacy  (unchanged)")
    print()


# ---------------------------------------------------------------------------
# Programmatic API (for web GUI — no interactive prompts, no sys.exit)
# ---------------------------------------------------------------------------

def _grouping_to_dict(result: GroupingResult) -> Dict[str, Any]:
    """Serialize a GroupingResult to a plain dict for JSON responses."""
    return {
        "case": result.case,
        "confidence": result.confidence,
        "pdf_count": result.pdf_count,
        "needs_user_input": result.needs_user_input,
        "question": result.question,
        "signals": list(result.signals),
        "anti_signals": list(result.anti_signals),
        "source_path": str(result.source_path),
        "books": [
            {
                "suggested_name": b.suggested_name,
                "ordering_confirmed": b.ordering_confirmed,
                "ordering_note": b.ordering_note,
                "has_unknown_order": b.has_unknown_order,
                "files": [str(f) for f in b.files],
                "file_names": [f.name for f in b.files],
            }
            for b in result.books
        ],
    }


def run_phase_b_api(
    source: Path,
    book_name_he: str,
    calculator_id: str,
    outdir: Optional[Path] = None,
    skip_db: bool = True,
    dry_run: bool = False,
    grouping_mode: str = "auto",
) -> Dict[str, Any]:
    """Programmatic Phase B — no interactive prompts, raises instead of sys.exit.

    Returns a result dict suitable for JSON serialization.
    ``grouping_mode``: "auto" | "single" | "multi"
      - "auto"   : use detect_grouping(); raises ValueError if ambiguous
      - "single" : force ONE_SPLIT_BOOK
      - "multi"  : force MULTIPLE_BOOKS (Phase B will raise — run per book)
    """
    warnings_list: List[str] = []

    # ── Validation ──────────────────────────────────────────────────────────
    if not calculator_id:
        raise ValueError("calculator_id is required.")
    if not book_name_he:
        raise ValueError("book_name_he is required.")
    if not _VALID_ID_RE.match(calculator_id):
        raise ValueError(
            f"calculator_id {calculator_id!r} is invalid. "
            "Use only lowercase letters, digits, and underscores. Must start with a letter."
        )
    if calculator_id in _GOLDEN_IDS:
        raise ValueError(
            f"calculator_id {calculator_id!r} is protected "
            "(golden reference or production default). Choose a different ID."
        )
    if book_name_he in _GOLDEN_TITLES:
        raise ValueError(
            f"book_name_he {book_name_he!r} is the golden reference title. "
            "Choose a different title."
        )

    # ── Grouping ─────────────────────────────────────────────────────────────
    if grouping_mode == "single":
        result = force_one_split_book(source)
    elif grouping_mode == "multi":
        result = force_multiple_books(source)
    else:
        result = detect_grouping(source)
        if result.needs_user_input:
            raise ValueError(
                "Grouping is ambiguous — cannot proceed automatically. "
                "Set grouping_mode to 'single' or 'multi' to resolve."
            )

    if result.case == "MULTIPLE_BOOKS":
        raise ValueError(
            "Multiple books detected. Phase B processes one book at a time. "
            "Run separately for each book with grouping_mode='single'."
        )

    if not result.books:
        raise ValueError("No book candidates found in source path.")

    book_candidate: BookCandidate = result.books[0]
    source_files: List[Path] = book_candidate.files
    resolved_outdir: Path = outdir if outdir else research_book_dir(book_name_he)

    # ── PDF merge availability ────────────────────────────────────────────────
    needs_merge = len(source_files) > 1
    can_fitz = False
    if needs_merge:
        try:
            import fitz  # type: ignore  # noqa: F401
            can_fitz = True
        except ImportError:
            pass

    # ── Dry-run: return plan without executing ────────────────────────────────
    if dry_run:
        _ARTIFACT_SUFFIXES = [
            "__source_manifest.json",
            "__source_corpus.txt",
            "__chapter_inventory.json",
            "__calc_candidates.json",
            "__draft_catalog.json",
            "__reviewed_catalog.json",
            "__definition_candidate.json",
            "__review_report.json",
        ]
        planned = {
            book_name_he + s: str(resolved_outdir / (book_name_he + s))
            for s in _ARTIFACT_SUFFIXES
        }
        return {
            "ok": True,
            "dry_run": True,
            "book_name_he": book_name_he,
            "calculator_id": calculator_id,
            "output_dir": str(resolved_outdir),
            "grouping": _grouping_to_dict(result),
            "will_merge": needs_merge and can_fitz,
            "merge_warning": (
                "PyMuPDF (fitz) not available — first file will be used only."
                if needs_merge and not can_fitz else ""
            ),
            "planned_artifacts": planned,
            "warnings": [],
            "confirmed": {
                "golden_reference_untouched": True,
                "production_switch_performed": False,
                "default_calculator_id": "green_legacy",
            },
        }

    # ── PDF merge ─────────────────────────────────────────────────────────────
    merged_pdf_path: Optional[Path] = None
    if needs_merge and can_fitz:
        resolved_outdir.mkdir(parents=True, exist_ok=True)
        merged_name = f"{book_name_he}__merged_source.pdf"
        merged_pdf_path = resolved_outdir / merged_name
        success = _try_merge_pdfs(source_files, merged_pdf_path, verbose=False)
        if not success:
            warnings_list.append(
                f"PDF merge failed. Falling back to first file: {source_files[0].name}"
            )
            merged_pdf_path = None
    elif needs_merge:
        warnings_list.append(
            f"PyMuPDF (fitz) not available. Processing first file only: {source_files[0].name}"
        )

    pdf_to_use: Path = merged_pdf_path if merged_pdf_path is not None else source_files[0]

    # ── BookIngestionRunner ───────────────────────────────────────────────────
    try:
        from book_ingestion.book_ingestion_runner import BookIngestionRunner  # noqa: E402
    except ImportError as exc:
        raise RuntimeError(f"Cannot import BookIngestionRunner: {exc}") from exc

    runner = BookIngestionRunner(
        book_title=book_name_he,
        book_id=calculator_id,
        pdf_path=str(pdf_to_use),
        output_dir=str(resolved_outdir),
    )
    if skip_db:
        runner.stage_5_ingest_db = lambda: {"skipped": True}  # type: ignore

    try:
        run_summary = runner.run()
    except Exception as exc:
        raise RuntimeError(f"BookIngestionRunner failed: {exc}") from exc

    # ── Quality gates (warn, continue) ───────────────────────────────────────
    corpus_path = resolved_outdir / f"{book_name_he}__source_corpus.txt"
    if corpus_path.exists():
        corpus_len = len(corpus_path.read_text(encoding="utf-8", errors="replace"))
        if corpus_len < 3000:
            warnings_list.append(
                f"Source corpus is very short ({corpus_len} chars). "
                "Extraction may be incomplete."
            )
    else:
        warnings_list.append("__source_corpus.txt was not produced.")

    draft_path = resolved_outdir / f"{book_name_he}__draft_catalog.json"
    if not draft_path.exists():
        raise RuntimeError(
            f"__draft_catalog.json was not produced at: {draft_path}"
        )

    draft_catalog = json.loads(draft_path.read_text(encoding="utf-8"))
    draft_calcs: List[Dict[str, Any]] = list(draft_catalog.get("calculations") or [])
    total_draft = len(draft_calcs)

    if total_draft == 0:
        warnings_list.append(
            "draft_catalog has 0 calculation entries. "
            "Review the corpus — the book may not match any concept patterns."
        )

    # ── Manifest ─────────────────────────────────────────────────────────────
    manifest_path = resolved_outdir / f"{book_name_he}__source_manifest.json"
    manifest: Dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Write 3 review-artifact stubs ────────────────────────────────────────
    reviewed_stub = _build_reviewed_catalog_stub(book_name_he, calculator_id, draft_catalog)
    _write_json(
        resolved_outdir / f"{book_name_he}__reviewed_catalog.json",
        reviewed_stub, dry_run=False, verbose=False,
    )

    def_stub = _build_definition_candidate_stub(book_name_he, calculator_id, draft_catalog)
    _write_json(
        resolved_outdir / f"{book_name_he}__definition_candidate.json",
        def_stub, dry_run=False, verbose=False,
    )

    report_stub = _build_review_report_stub(
        book_name_he, calculator_id, draft_catalog, manifest
    )
    _write_json(
        resolved_outdir / f"{book_name_he}__review_report.json",
        report_stub, dry_run=False, verbose=False,
    )

    # ── Artifact status dict ──────────────────────────────────────────────────
    _ARTIFACT_SUFFIXES_FULL = [
        "__source_manifest.json",
        "__source_corpus.txt",
        "__chapter_inventory.json",
        "__calc_candidates.json",
        "__draft_catalog.json",
        "__reviewed_catalog.json",
        "__definition_candidate.json",
        "__review_report.json",
    ]
    artifacts: Dict[str, Any] = {}
    for s in _ARTIFACT_SUFFIXES_FULL:
        p = resolved_outdir / (book_name_he + s)
        artifacts[book_name_he + s] = {"exists": p.exists(), "path": str(p)}

    return {
        "ok": True,
        "dry_run": False,
        "book_name_he": book_name_he,
        "calculator_id": calculator_id,
        "output_dir": str(resolved_outdir),
        "grouping": _grouping_to_dict(result),
        "draft_entries": total_draft,
        "run_summary": run_summary if isinstance(run_summary, dict) else {},
        "artifacts": artifacts,
        "warnings": warnings_list,
        "confirmed": {
            "golden_reference_untouched": True,
            "production_switch_performed": False,
            "default_calculator_id": "green_legacy",
        },
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Ensure Hebrew text prints correctly on Windows consoles
    import io as _io
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    else:
        sys.stdout = _io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    parser = argparse.ArgumentParser(
        prog="scaffold_new_book.py",
        description=(
            "MVP book onboarding scaffold — Phase A (inspect) and Phase B "
            "(generate review artifact stubs)."
        ),
    )
    parser.add_argument(
        "--source", "-s",
        required=False,
        help="Source file (PDF) or folder path.",
    )
    parser.add_argument(
        "--book-name-he", "-n",
        default="",
        help="Hebrew book title (used in artifact filenames).",
    )
    parser.add_argument(
        "--calculator-id", "-i",
        default="",
        help="Unique calculator ID: lowercase letters, digits, underscores.",
    )
    parser.add_argument(
        "--phase", "-p",
        choices=["A", "B"],
        default="A",
        help="Phase to run. A=inspect only, B=generate review artifacts. Default: A.",
    )
    parser.add_argument(
        "--outdir", "-o",
        default=None,
        help=(
            "Output directory for artifacts. "
            "Default: interpretations/research/<book_name_he>/ inside NumerologyReportGenerator."
        ),
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        default=False,
        help="Skip BookIngestionRunner Stage 5 (SQLite ingestion). Useful for offline review.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be written without writing anything.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="Auto-confirm all prompts.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Print detailed progress.",
    )

    args = parser.parse_args()

    # Phase A requires: source (optionally book-name-he / calculator-id for preview)
    # Phase B requires: source + book-name-he + calculator-id
    if args.phase == "B":
        if not args.source:
            parser.error("--source is required for Phase B")
        if not args.book_name_he:
            parser.error("--book-name-he is required for Phase B")
        if not args.calculator_id:
            parser.error("--calculator-id is required for Phase B")
    else:  # Phase A
        if not args.source:
            parser.error("--source is required for Phase A")

    # Safety checks (only if we have both id and title)
    if args.calculator_id or args.book_name_he:
        _safety_check(
            args.calculator_id or "placeholder_id_check",
            args.book_name_he  or "placeholder_title_check",
        )

    source  = Path(args.source).resolve()
    outdir  = Path(args.outdir).resolve() if args.outdir else None

    if args.phase == "A":
        phase_a(
            source        = source,
            book_name_he  = args.book_name_he,
            calculator_id = args.calculator_id,
            outdir        = outdir,
        )
    elif args.phase == "B":
        _safety_check(args.calculator_id, args.book_name_he)
        phase_b(
            source        = source,
            book_name_he  = args.book_name_he,
            calculator_id = args.calculator_id,
            outdir        = outdir,
            skip_db       = args.skip_db,
            dry_run       = args.dry_run,
            auto_yes      = args.yes,
            verbose       = args.verbose,
        )


if __name__ == "__main__":
    main()
