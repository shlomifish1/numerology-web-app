"""
Book Lab — Native Text Extraction (foundation, v0)

Local-only extractor that reads an existing source file that already
contains accessible text and produces a plain-text corpus plus an
extraction_report dict/json.

This is NOT OCR, NOT scanned-PDF support, NOT a model/API call, NOT an
agent runner, and does NOT touch runtime/server/production paths. It only
reads an existing source file — it never modifies it, and it never writes
anywhere except the explicit output paths the caller provides.

Supported (native text only):
  - .txt   — UTF-8 / UTF-8-with-BOM text files
  - .epub  — minimal stdlib zipfile + HTML-stripping (no full EPUB engine)
  - .pdf   — native text layer only, via the same `fitz` (PyMuPDF) dependency
             already used by book_ingestion/book_ingestion_runner.py for its
             "fitz-native-full" strategy. If `fitz` is not importable, PDFs
             are reported as unsupported — no dependency is installed.

Anything else (scanned PDFs, images, unknown extensions, decode failures,
corrupted archives) is reported back as a controlled "unsupported"/"fail"
result — never a crash and never a silent OCR fallback.

stdlib only (plus the already-present, optional `fitz`). No DB. No server.
No Flask. No external services. No pip install.
"""

from __future__ import annotations

import os
import zipfile
from html.parser import HTMLParser

from book_job_record import artifact_relative_path, save_json, utc_now_iso

# `fitz` (PyMuPDF) is an existing, already-imported dependency of
# book_ingestion_runner.py's native-PDF strategy — guarded the same way here.
# We do NOT install it; if it is unavailable, PDFs are simply unsupported.
try:
    import fitz  # type: ignore  (PyMuPDF)
    _FITZ_AVAILABLE = True
except ImportError:
    fitz = None
    _FITZ_AVAILABLE = False


_FORMAT_EXTENSION_MAP: dict[str, str] = {
    ".txt": "txt",
    ".epub": "epub",
    ".pdf": "pdf",
}

_EPUB_CONTENT_EXTENSIONS = (".xhtml", ".html", ".htm")
_HTML_SKIP_TAGS = {"script", "style"}

VALID_EXTRACTION_METHODS = {"txt_native", "epub_native", "pdf_native", "unsupported"}
VALID_EXTRACTION_STATUSES = {"pass", "warn", "fail", "unsupported"}


def _detect_format(path: str) -> str:
    _, ext = os.path.splitext(path)
    return _FORMAT_EXTENSION_MAP.get(ext.lower(), "unknown")


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _write_text_file(path: str, text: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# ── TXT extraction ───────────────────────────────────────────────────────────

def extract_text_from_txt(path: str) -> tuple[str, dict]:
    """
    Read a .txt file as UTF-8, falling back to utf-8-sig (BOM-aware) decoding.
    Normalizes line endings to '\\n' only — does not otherwise alter content.

    Returns (text, metadata) where metadata has 'encoding_used' and 'has_bom'.
    Raises ValueError if the file cannot be decoded as UTF-8 at all.
    """
    with open(path, "rb") as fh:
        raw = fh.read()

    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"unable to decode '{path}' as UTF-8 (or UTF-8 with BOM): {exc}") from exc

    return _normalize_line_endings(text), {
        "encoding_used": "utf-8-sig" if has_bom else "utf-8",
        "has_bom": has_bom,
    }


# ── EPUB extraction (minimal: zipfile + stdlib HTML stripping) ──────────────

class _HTMLTextExtractor(HTMLParser):
    """Collects visible text from HTML/XHTML, skipping <script>/<style> bodies."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in _HTML_SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _HTML_SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def _strip_html(html_text: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html_text)
    parser.close()
    return parser.get_text()


def extract_text_from_epub(path: str) -> tuple[str, dict]:
    """
    Minimal EPUB text extraction: open the .epub as a zip archive, read every
    .xhtml/.html/.htm entry in name-sorted order, and strip HTML tags with the
    stdlib html.parser. This is intentionally NOT a full EPUB engine — no
    spine/manifest/TOC parsing, no CSS, no images.

    Returns (text, metadata) where metadata has 'sections_count'.
    Raises (zipfile.BadZipFile, KeyError, ...) on a malformed archive — the
    caller (extract_native_text) turns that into a controlled unsupported result.
    """
    sections: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name for name in archive.namelist()
            if name.lower().endswith(_EPUB_CONTENT_EXTENSIONS)
        )
        for name in names:
            raw = archive.read(name)
            html_text = raw.decode("utf-8", errors="replace")
            section_text = _strip_html(html_text).strip()
            if section_text:
                sections.append(section_text)

    text = _normalize_line_endings("\n\n".join(sections))
    return text, {"sections_count": len(sections)}


# ── PDF native-text extraction (only if `fitz`/PyMuPDF is already present) ──

def _extract_pdf_native_text(path: str) -> tuple[str, int]:
    """Native text layer only (page.get_text('text')) — never rasterizes or OCRs."""
    doc = fitz.open(path)
    try:
        page_texts = [(page.get_text("text") or "") for page in doc]
        return _normalize_line_endings("\n".join(page_texts)), len(doc)
    finally:
        doc.close()


# ── Dispatcher ───────────────────────────────────────────────────────────────

def extract_native_text(path: str) -> dict:
    """
    Detect the source format from its extension and extract native text only.

    Returns a dict with: text, extraction_method, format_detected,
    pages_or_sections_count, issues, warnings. Never raises for an
    unsupported format or a decode/parse failure — those become a
    controlled 'unsupported' result instead. Raises FileNotFoundError
    if `path` does not point to an existing file.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"source file not found: '{path}'")

    format_detected = _detect_format(path)

    if format_detected == "txt":
        try:
            text, _meta = extract_text_from_txt(path)
        except ValueError as exc:
            return {
                "text": "", "extraction_method": "unsupported", "format_detected": "txt",
                "pages_or_sections_count": None,
                "issues": ["txt_decode_error"], "warnings": [str(exc)],
            }
        return {
            "text": text, "extraction_method": "txt_native", "format_detected": "txt",
            "pages_or_sections_count": None, "issues": [], "warnings": [],
        }

    if format_detected == "epub":
        try:
            text, meta = extract_text_from_epub(path)
        except Exception as exc:
            return {
                "text": "", "extraction_method": "unsupported", "format_detected": "epub",
                "pages_or_sections_count": None,
                "issues": ["unsupported_epub"], "warnings": [f"epub_extraction_failed: {exc}"],
            }
        warnings = [] if meta["sections_count"] > 0 else ["epub_no_content_sections_found"]
        return {
            "text": text, "extraction_method": "epub_native", "format_detected": "epub",
            "pages_or_sections_count": meta["sections_count"], "issues": [], "warnings": warnings,
        }

    if format_detected == "pdf":
        if not _FITZ_AVAILABLE:
            return {
                "text": "", "extraction_method": "unsupported", "format_detected": "pdf",
                "pages_or_sections_count": None,
                "issues": ["unsupported_pdf_native_missing_dependency"], "warnings": [],
            }
        try:
            text, page_count = _extract_pdf_native_text(path)
        except Exception as exc:
            return {
                "text": "", "extraction_method": "unsupported", "format_detected": "pdf",
                "pages_or_sections_count": None,
                "issues": ["pdf_native_extraction_failed"], "warnings": [str(exc)],
            }
        return {
            "text": text, "extraction_method": "pdf_native", "format_detected": "pdf",
            "pages_or_sections_count": page_count, "issues": [], "warnings": [],
        }

    return {
        "text": "", "extraction_method": "unsupported", "format_detected": format_detected,
        "pages_or_sections_count": None,
        "issues": ["unsupported_format"], "warnings": [],
    }


# ── Report building + saving ─────────────────────────────────────────────────

def build_extraction_report(extraction_result: dict, source_path: str,
                            book_id: str | None = None, source_id: str | None = None) -> dict:
    """Build the extraction_report.json dict from an extract_native_text() result."""
    text = extraction_result["text"]
    total_chars = len(text)
    non_whitespace_chars = sum(1 for ch in text if not ch.isspace())

    method = extraction_result["extraction_method"]
    issues = list(extraction_result.get("issues", []))
    warnings = list(extraction_result.get("warnings", []))

    if method == "unsupported":
        status = "unsupported"
    elif total_chars == 0:
        status = "fail"
        if "no_text_extracted" not in issues:
            issues.append("no_text_extracted")
    elif warnings:
        status = "warn"
    else:
        status = "pass"

    return {
        "book_id": book_id,
        "source_id": source_id,
        "source_path": source_path,
        "format_detected": extraction_result["format_detected"],
        "extraction_method": method,
        "total_chars": total_chars,
        "non_whitespace_chars": non_whitespace_chars,
        "pages_or_sections_count": extraction_result.get("pages_or_sections_count"),
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "created_at": utc_now_iso(),
    }


def save_text_extraction_outputs(source_file_path: str, corpus_output_path: str, report_output_path: str,
                                 book_id: str | None = None, source_id: str | None = None) -> dict:
    """
    Extract native text from source_file_path and write exactly two files:
    the plain-text corpus to corpus_output_path and the JSON report to
    report_output_path — both explicit paths supplied by the caller. Never
    defaults to or infers a production/job-queue/server-side path.

    Returns a dict with: corpus_path, report_path, extraction_report, text.
    """
    if not corpus_output_path or not isinstance(corpus_output_path, str):
        raise ValueError("corpus_output_path must be a non-empty string provided by the caller")
    if not report_output_path or not isinstance(report_output_path, str):
        raise ValueError("report_output_path must be a non-empty string provided by the caller")

    extraction_result = extract_native_text(source_file_path)
    report = build_extraction_report(
        extraction_result,
        source_path=os.path.abspath(source_file_path),
        book_id=book_id,
        source_id=source_id,
    )

    _write_text_file(corpus_output_path, extraction_result["text"])
    save_json(report_output_path, report)

    return {
        "corpus_path": corpus_output_path,
        "report_path": report_output_path,
        "extraction_report": report,
        "text": extraction_result["text"],
    }


# ── Optional integration helper (explicit job_dir, canonical raw/ paths) ────

def write_extraction_outputs_for_job(job_dir: str, source_file_path: str,
                                     book_id: str | None = None, source_id: str | None = None) -> dict:
    """
    Tiny convenience wrapper around save_text_extraction_outputs(): writes to
    the canonical raw/source_corpus.txt and raw/extraction_report.json paths
    (per book_job_record.py's artifact conventions) under an explicit job_dir.
    """
    corpus_path = os.path.join(job_dir, *artifact_relative_path("raw", "source_corpus.txt").split("/"))
    report_path = os.path.join(job_dir, *artifact_relative_path("raw", "extraction_report.json").split("/"))
    return save_text_extraction_outputs(source_file_path, corpus_path, report_path,
                                        book_id=book_id, source_id=source_id)
