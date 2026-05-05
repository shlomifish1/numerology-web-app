"""grouping_detector.py — Source-path grouping logic for scaffold_new_book.

Inspects a file or folder and decides whether it represents:
  SINGLE_FILE    — one PDF file = one book
  ONE_SPLIT_BOOK — multiple PDFs that together form one book (page-range split)
  MULTIPLE_BOOKS — multiple PDFs that are different books
  AMBIGUOUS      — cannot determine; caller must ask the user

No files are written.
No imports from calculators/, rule_extractor, or any project domain module.
Depends only on stdlib + pathlib.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_PDF_SUFFIXES: frozenset[str] = frozenset({".pdf"})

# Patterns that strongly suggest this filename encodes a page range or part marker.
# Each entry: (compiled_regex, human_readable_signal_label)
_PAGE_RANGE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"עד\s*\d+",        re.UNICODE),      "Hebrew 'up to N' (עד N)"),
    (re.compile(r"עד\s*הסוף",       re.UNICODE),      "Hebrew 'to the end' (עד הסוף)"),
    (re.compile(r"\d+\s*[-–]\s*\d+"),                 "Numeric range N-M"),
    (re.compile(r"\d+\s*עד\s*\d+",  re.UNICODE),      "Hebrew 'N to M' (N עד M)"),
    (re.compile(r"פרק.+עד\s*\d+",   re.UNICODE),      "Chapter + page-range (פרק…עד N)"),
    (re.compile(r"חלק\s*[א-ת\d]",   re.UNICODE),      "Hebrew volume/part (חלק א/ב/...)"),
    (re.compile(r"part\s*\d+",       re.IGNORECASE),   "English part indicator (part N)"),
    (re.compile(r"vol\.?\s*\d+",     re.IGNORECASE),   "Volume indicator (vol N)"),
    (re.compile(r"סוף\s*חלק",        re.UNICODE),      "Hebrew 'end of part' (סוף חלק)"),
]

_TERMINAL_PATTERN: re.Pattern = re.compile(r"עד\s*הסוף", re.UNICODE)
_PAGE_END_SENTINEL: int = 10 ** 9   # sort-key for "עד הסוף" files

# Confidence thresholds
_AUTO_SPLIT_THRESHOLD: float  = 0.75  # ≥ this → ONE_SPLIT_BOOK (no question)
_AMBIGUOUS_THRESHOLD:  float  = 0.55  # ≥ this → AMBIGUOUS (ask user)
# < _AMBIGUOUS_THRESHOLD → MULTIPLE_BOOKS (or ask, depending on anti-signals)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BookCandidate:
    """One logical book with an ordered list of source files."""
    files:                List[Path]
    suggested_name:       str  = ""
    ordering_confirmed:   bool = False   # set to True after user confirms order
    ordering_note:        str  = ""      # human-readable per-file order description
    has_unknown_order:    bool = False   # True if any file had no extractable page number


@dataclass
class GroupingResult:
    """Output of detect_grouping()."""
    case:             str          # SINGLE_FILE | ONE_SPLIT_BOOK | MULTIPLE_BOOKS | AMBIGUOUS
    confidence:       float        # 0.0 – 1.0
    books:            List[BookCandidate]
    signals:          List[str]    # positive signals (why this grouping was chosen)
    anti_signals:     List[str]    # negative signals (evidence against this grouping)
    pdf_count:        int
    needs_user_input: bool         # True → caller must ask a question before proceeding
    question:         str          # the question to ask (empty when needs_user_input=False)
    source_path:      Path = field(default_factory=Path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_grouping(source: Path) -> GroupingResult:
    """Inspect *source* and return a GroupingResult.

    Args:
        source: A file path (PDF) or a folder path.

    Raises:
        FileNotFoundError: If *source* does not exist.
        ValueError:        If *source* is a folder with no PDF files.
    """
    source = Path(source).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source path does not exist: {source}")

    # ── Single file ───────────────────────────────────────────────────────
    if source.is_file():
        return GroupingResult(
            case             = "SINGLE_FILE",
            confidence       = 1.0,
            books            = [BookCandidate(
                files          = [source],
                suggested_name = source.stem,
                ordering_note  = f"1. {source.name}  [only file]",
            )],
            signals          = ["Input is a single file"],
            anti_signals     = [],
            pdf_count        = 1,
            needs_user_input = False,
            question         = "",
            source_path      = source,
        )

    # ── Folder ────────────────────────────────────────────────────────────
    pdf_files = _collect_pdfs(source)
    if not pdf_files:
        raise ValueError(f"No PDF files found in: {source}")

    if len(pdf_files) == 1:
        return GroupingResult(
            case             = "SINGLE_FILE",
            confidence       = 1.0,
            books            = [BookCandidate(
                files          = [pdf_files[0]],
                suggested_name = source.name,
                ordering_note  = f"1. {pdf_files[0].name}  [only PDF in folder]",
            )],
            signals          = ["Only one PDF found in folder"],
            anti_signals     = [],
            pdf_count        = 1,
            needs_user_input = False,
            question         = "",
            source_path      = source,
        )

    # Multiple files: score and decide
    score, signals, anti_signals = _score_files(pdf_files)

    if score >= _AUTO_SPLIT_THRESHOLD:
        ordered, has_unknown = _order_files_by_page(pdf_files)
        candidate = BookCandidate(
            files          = ordered,
            suggested_name = source.name,
            ordering_note  = _build_order_note(ordered),
            has_unknown_order = has_unknown,
        )
        return GroupingResult(
            case             = "ONE_SPLIT_BOOK",
            confidence       = score,
            books            = [candidate],
            signals          = signals,
            anti_signals     = anti_signals,
            pdf_count        = len(pdf_files),
            needs_user_input = False,
            question         = "",
            source_path      = source,
        )

    if score >= _AMBIGUOUS_THRESHOLD:
        return GroupingResult(
            case             = "AMBIGUOUS",
            confidence       = score,
            books            = [],   # filled after user answers
            signals          = signals,
            anti_signals     = anti_signals,
            pdf_count        = len(pdf_files),
            needs_user_input = True,
            question         = (
                "Is this folder one book split into multiple files, "
                "or multiple separate books?"
            ),
            source_path      = source,
        )

    # Low score → treat as multiple books
    groups  = _group_by_prefix(pdf_files)
    books   = [
        BookCandidate(
            files          = g,
            suggested_name = _suggest_name_from_files(g),
            ordering_note  = _build_order_note(g),
        )
        for g in groups
    ]
    return GroupingResult(
        case             = "MULTIPLE_BOOKS",
        confidence       = score,
        books            = books,
        signals          = signals,
        anti_signals     = anti_signals,
        pdf_count        = len(pdf_files),
        needs_user_input = False,
        question         = "",
        source_path      = source,
    )


def force_one_split_book(source: Path, pdf_files: Optional[List[Path]] = None) -> GroupingResult:
    """Build a ONE_SPLIT_BOOK result from *source* without re-scoring.

    Used when the user explicitly answered 'one split book' to the ambiguity question.
    """
    source = Path(source).resolve()
    if pdf_files is None:
        pdf_files = _collect_pdfs(source)
    ordered, has_unknown = _order_files_by_page(pdf_files)
    candidate = BookCandidate(
        files             = ordered,
        suggested_name    = source.name,
        ordering_note     = _build_order_note(ordered),
        has_unknown_order = has_unknown,
    )
    return GroupingResult(
        case             = "ONE_SPLIT_BOOK",
        confidence       = 1.0,
        books            = [candidate],
        signals          = ["User confirmed: one split book"],
        anti_signals     = [],
        pdf_count        = len(pdf_files),
        needs_user_input = False,
        question         = "",
        source_path      = source,
    )


def force_multiple_books(source: Path, pdf_files: Optional[List[Path]] = None) -> GroupingResult:
    """Build a MULTIPLE_BOOKS result from *source* without re-scoring.

    Used when the user explicitly answered 'multiple books' to the ambiguity question.
    """
    source = Path(source).resolve()
    if pdf_files is None:
        pdf_files = _collect_pdfs(source)
    groups = _group_by_prefix(pdf_files)
    books  = [
        BookCandidate(
            files          = g,
            suggested_name = _suggest_name_from_files(g),
            ordering_note  = _build_order_note(g),
        )
        for g in groups
    ]
    return GroupingResult(
        case             = "MULTIPLE_BOOKS",
        confidence       = 1.0,
        books            = books,
        signals          = ["User confirmed: multiple separate books"],
        anti_signals     = [],
        pdf_count        = len(pdf_files),
        needs_user_input = False,
        question         = "",
        source_path      = source,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_pdfs(folder: Path) -> List[Path]:
    """Return sorted list of PDF files directly inside *folder* (not recursive).

    Excludes scaffold-generated artifact files (``__merged_source.pdf``,
    ``__source_manifest``, etc.) so that a second run on a folder that already
    contains a merged PDF from a previous Phase B run is not confused.
    """
    return sorted(
        f for f in folder.iterdir()
        if (
            f.is_file()
            and f.suffix.lower() in _VALID_PDF_SUFFIXES
            # Ignore scaffold artifacts — double-underscore prefix marks them
            and "__" not in f.stem
        )
    )


def _is_page_range_filename(name: str) -> bool:
    """Return True if *name* contains any page-range or part-indicator pattern."""
    return any(pat.search(name) for pat, _ in _PAGE_RANGE_PATTERNS)


def _matched_signals(name: str) -> List[str]:
    """Return list of signal labels matched in *name*."""
    return [label for pat, label in _PAGE_RANGE_PATTERNS if pat.search(name)]


def _extract_page_start(name: str) -> int:
    """Return sort-key page number extracted from *name*.

    Returns _PAGE_END_SENTINEL for 'עד הסוף' (terminal chunk).
    Returns -1 if no page number found (unknown order).
    """
    # Terminal: "עד הסוף" → goes last
    if _TERMINAL_PATTERN.search(name):
        return _PAGE_END_SENTINEL

    # "N עד M" or "N-M" or "N–M" → start page = N
    m = re.search(r"(\d+)\s*(?:עד|[-–])\s*\d+", name, re.UNICODE)
    if m:
        return int(m.group(1))

    # "עד N" → end page N; use it as sort-key
    m = re.search(r"עד\s*(\d+)", name, re.UNICODE)
    if m:
        return int(m.group(1))

    return -1


def _order_files_by_page(files: List[Path]) -> Tuple[List[Path], bool]:
    """Return (ordered_files, has_unknown_order).

    Files with extractable page numbers sort by ascending number.
    Files with no number sort last.
    has_unknown_order is True when any file had page number = -1.
    """
    def sort_key(f: Path) -> Tuple[int, int]:
        n = _extract_page_start(f.name)
        return (0 if n >= 0 else 1, n if n >= 0 else 0)

    ordered = sorted(files, key=sort_key)
    has_unknown = any(_extract_page_start(f.name) == -1 for f in files)
    return ordered, has_unknown


def _build_order_note(files: List[Path]) -> str:
    """Build a human-readable numbered list of files with their detected page ranges."""
    lines = []
    for i, f in enumerate(files, 1):
        n = _extract_page_start(f.name)
        if n == _PAGE_END_SENTINEL:
            tag = "[final chunk — עד הסוף]"
        elif n >= 0:
            tag = f"[starts near page {n}]"
        else:
            tag = "[page order unknown — verify manually]"
        lines.append(f"  {i}. {f.name}  {tag}")
    return "\n".join(lines)


def _score_files(files: List[Path]) -> Tuple[float, List[str], List[str]]:
    """Compute confidence score + signal lists for a list of PDFs.

    Returns (score, positive_signals, anti_signals).
    score is clamped to [0.0, 1.0].
    """
    names    = [f.name for f in files]
    score    = 0.50
    signals:     List[str] = []
    anti_signals: List[str] = []

    # ── Positive signals ──────────────────────────────────────────────────
    page_range_count = sum(1 for n in names if _is_page_range_filename(n))
    has_terminal     = any(_TERMINAL_PATTERN.search(n) for n in names)

    if page_range_count == len(names):
        score += 0.20
        signals.append(f"All {len(names)} files match page-range patterns")
    elif page_range_count >= max(1, len(names) * 0.60):
        score += 0.10
        signals.append(f"{page_range_count}/{len(names)} files match page-range patterns")

    if has_terminal:
        score += 0.20
        signals.append("Terminal chunk found (עד הסוף) — confirms ordered split")

    # Numeric ordering: extract page starts, check at least 2 are known and ascending
    page_starts = [_extract_page_start(n) for n in names]
    known = [(i, p) for i, p in enumerate(page_starts) if 0 <= p < _PAGE_END_SENTINEL]
    if len(known) >= 2:
        sorted_pages = sorted(p for _, p in known)
        original_pages = [p for _, p in known]
        if sorted_pages == original_pages:
            score += 0.10
            signals.append("Files are already in ascending page-number order")
        else:
            # They can still be re-ordered; note this is a mild positive
            score += 0.05
            signals.append("Files have extractable page numbers (will be reordered)")

    if _any_shared_prefix(names):
        score += 0.05
        signals.append("Files share a common filename prefix")

    # ── Negative signals ──────────────────────────────────────────────────
    distinct_tokens = _count_distinct_non_numeric_tokens(names)
    if distinct_tokens >= 4:
        score -= 0.20
        anti_signals.append(
            f"Multiple distinct non-numeric tokens detected ({distinct_tokens}) — "
            "suggests different titles"
        )
    elif distinct_tokens >= 2 and page_range_count == 0:
        score -= 0.10
        anti_signals.append(
            "No page-range patterns AND multiple distinct title tokens — "
            "possible multi-book folder"
        )

    if not _any_shared_prefix(names) and page_range_count == 0:
        score -= 0.10
        anti_signals.append("No shared filename prefix and no page-range indicators")

    return max(0.0, min(1.0, score)), signals, anti_signals


def _any_shared_prefix(names: List[str]) -> bool:
    """Return True if all names share at least one non-trivial token."""
    if len(names) < 2:
        return True
    sets = [_significant_tokens(n) for n in names]
    common = sets[0].copy()
    for s in sets[1:]:
        common &= s
    return bool(common)


def _significant_tokens(name: str) -> set[str]:
    """Extract non-numeric, non-trivial tokens from a filename stem."""
    stem = Path(name).stem
    # Remove page-range patterns first so digits don't count as title tokens
    cleaned = re.sub(r"\d+", " ", stem)
    cleaned = re.sub(
        r"\b(?:עד|הסוף|חלק|פרק|part|vol|section|סוף)\b", " ", cleaned,
        flags=re.IGNORECASE | re.UNICODE,
    )
    tokens = re.split(r"[\s_\-–.]+", cleaned.strip())
    return {t.strip() for t in tokens if len(t.strip()) >= 2}


def _count_distinct_non_numeric_tokens(names: List[str]) -> int:
    """Count how many distinct significant tokens appear across all names."""
    all_tokens: set[str] = set()
    for n in names:
        all_tokens |= _significant_tokens(n)
    return len(all_tokens)


def _group_by_prefix(files: List[Path]) -> List[List[Path]]:
    """Group files by their 2-token shared prefix. Each group = one book candidate."""
    groups: dict[str, List[Path]] = {}
    for f in files:
        key = _prefix_key(f.name)
        groups.setdefault(key, []).append(f)
    return list(groups.values())


def _prefix_key(name: str) -> str:
    """Return a stable 2-token grouping key for *name*."""
    stem = Path(name).stem
    tokens = re.split(r"[\s_\-–.]+", stem.strip())
    non_numeric = [t for t in tokens if t and not t.isdigit() and len(t) >= 2]
    if non_numeric:
        return "_".join(non_numeric[:2]).lower()
    return (stem[:8] or "unknown").lower()


def _suggest_name_from_files(files: List[Path]) -> str:
    """Suggest a book name from a group of files."""
    if not files:
        return "unknown"
    return _prefix_key(files[0].name)
