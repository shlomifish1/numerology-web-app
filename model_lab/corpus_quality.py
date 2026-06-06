"""
Book Lab — Corpus Quality Analyzer (foundation, v0)

Local-only analyzer that reads an existing source_corpus.txt and produces
a corpus_quality_report dict/json with basic character/line metrics and a
pass / warn / fail verdict.

This is NOT OCR, NOT text extraction, NOT a model/API call, NOT an agent
runner, and does NOT touch runtime/server/production paths. It only reads
an existing text file — it never writes to or modifies the source corpus.

stdlib only. No DB. No server. No Flask. No external calls.
"""

from __future__ import annotations

import json
import os

# ── Thresholds (aligned with intake_validator.py's corpus-quality rules) ────
#
# corpus_empty:        total_chars == 0                         -> fail
# corpus_too_short:    total_chars < LOW_QUALITY_CHARS_THRESHOLD -> fail
#                      (conservative choice: short corpora are treated as a
#                      hard failure here, not a warning, mirroring the
#                      "corpus_low_quality" block-from-model rule in
#                      BOOK_INTAKE_ANALYZER_SPEC.md)
# low_hebrew_ratio:    estimated_hebrew_ratio < LOW_QUALITY_HEBREW_RATIO
#                      (only checked once the corpus is non-empty and long
#                      enough to be meaningfully measured)               -> fail
# high_noise_ratio:    noise_ratio >= NOISE_RATIO_FAIL_THRESHOLD          -> fail
# elevated noise / blank lines / duplicate lines below the fail thresholds
# but at/above their warn thresholds                                     -> warn

LOW_QUALITY_CHARS_THRESHOLD = 500
LOW_QUALITY_HEBREW_RATIO = 0.15

NOISE_RATIO_WARN_THRESHOLD = 0.02
NOISE_RATIO_FAIL_THRESHOLD = 0.10
BLANK_LINE_RATIO_WARN_THRESHOLD = 0.5
DUPLICATE_LINE_RATIO_WARN_THRESHOLD = 0.3

VALID_REPORT_STATUSES = {"pass", "warn", "fail"}

_ALLOWED_CONTROL_CHARS = {"\n", "\r", "\t"}


def _is_hebrew_char(ch: str) -> bool:
    return "֐" <= ch <= "׿"


def _is_latin_char(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z")


def _is_suspicious_char(ch: str) -> bool:
    """Control characters (besides \\n/\\r/\\t) and the Unicode replacement
    character — simple stand-ins for OCR/encoding noise in a text corpus."""
    if ch in _ALLOWED_CONTROL_CHARS:
        return False
    code = ord(ch)
    return code < 0x20 or code == 0x7F or ch == "�"


def analyze_corpus_text(text: str, source_id: str | None = None, book_id: str | None = None) -> dict:
    """
    Compute corpus quality metrics for a text string and decide pass/warn/fail.

    Pure function — does not touch the filesystem. Returns a JSON-serializable
    dict; never mutates or copies the input text.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    total_chars = len(text)

    def _ratio(count: int) -> float:
        return (count / total_chars) if total_chars else 0.0

    whitespace_chars = sum(1 for ch in text if ch.isspace())
    hebrew_chars = sum(1 for ch in text if _is_hebrew_char(ch))
    digit_chars = sum(1 for ch in text if ch.isdigit())
    latin_chars = sum(1 for ch in text if _is_latin_char(ch))
    noise_chars = sum(1 for ch in text if _is_suspicious_char(ch))

    non_whitespace_chars = total_chars - whitespace_chars
    estimated_hebrew_ratio = _ratio(hebrew_chars)
    digit_ratio = _ratio(digit_chars)
    latin_ratio = _ratio(latin_chars)
    whitespace_ratio = _ratio(whitespace_chars)
    noise_ratio = _ratio(noise_chars)

    lines = text.splitlines()
    total_lines = len(lines)
    blank_lines = sum(1 for line in lines if not line.strip())
    blank_line_ratio = (blank_lines / total_lines) if total_lines else 0.0

    non_blank_lines = [line.strip() for line in lines if line.strip()]
    distinct_non_blank = set(non_blank_lines)
    duplicate_line_ratio = (
        (len(non_blank_lines) - len(distinct_non_blank)) / len(non_blank_lines)
        if non_blank_lines else 0.0
    )

    issues: list[str] = []
    warnings: list[str] = []

    if total_chars == 0:
        issues.append("corpus_empty")
    elif total_chars < LOW_QUALITY_CHARS_THRESHOLD:
        issues.append("corpus_too_short")
    elif estimated_hebrew_ratio < LOW_QUALITY_HEBREW_RATIO:
        issues.append("low_hebrew_ratio")
    elif noise_ratio >= NOISE_RATIO_FAIL_THRESHOLD:
        issues.append("high_noise_ratio")

    if not issues:
        if noise_ratio >= NOISE_RATIO_WARN_THRESHOLD:
            warnings.append("elevated_noise_ratio")
        if blank_line_ratio >= BLANK_LINE_RATIO_WARN_THRESHOLD:
            warnings.append("high_blank_line_ratio")
        if duplicate_line_ratio >= DUPLICATE_LINE_RATIO_WARN_THRESHOLD:
            warnings.append("high_duplicate_line_ratio")

    if issues:
        status = "fail"
    elif warnings:
        status = "warn"
    else:
        status = "pass"

    return {
        "book_id": book_id,
        "source_id": source_id,
        "total_chars": total_chars,
        "non_whitespace_chars": non_whitespace_chars,
        "estimated_hebrew_ratio": estimated_hebrew_ratio,
        "digit_ratio": digit_ratio,
        "latin_ratio": latin_ratio,
        "whitespace_ratio": whitespace_ratio,
        "blank_line_ratio": blank_line_ratio,
        "duplicate_line_ratio": duplicate_line_ratio,
        "noise_ratio": noise_ratio,
        "status": status,
        "issues": issues,
        "warnings": warnings,
    }


def analyze_source_corpus_file(path: str, source_id: str | None = None, book_id: str | None = None) -> dict:
    """Read an existing UTF-8 source_corpus.txt and analyze it. Read-only — never modifies the file."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return analyze_corpus_text(text, source_id=source_id, book_id=book_id)


def save_corpus_quality_report(report: dict, path: str) -> None:
    """Write a corpus_quality_report dict as pretty-printed UTF-8 JSON.

    Only writes to the explicit path provided by the caller — never defaults
    to or infers any production, job-queue, or server-side path.
    """
    if not path or not isinstance(path, str):
        raise ValueError("path must be a non-empty string provided by the caller")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_corpus_quality_report(path: str) -> dict:
    """Read and parse a corpus_quality_report JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
