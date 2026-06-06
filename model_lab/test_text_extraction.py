"""
Minimal self-contained tests for text_extraction.
No external deps beyond the already-present, optional `fitz`. No model/API/
OCR calls. Run with: py -3.12 test_text_extraction.py

All file-writing/reading tests use a temporary directory only — never a
production path. Source "books" are tiny throwaway files created in temp dirs.
"""

import inspect
import os
import shutil
import sys
import tempfile
import zipfile

import text_extraction as te
from text_extraction import (
    VALID_EXTRACTION_METHODS,
    VALID_EXTRACTION_STATUSES,
    build_extraction_report,
    extract_native_text,
    extract_text_from_epub,
    extract_text_from_txt,
    save_text_extraction_outputs,
)
from book_job_record import load_json

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_results: list[bool] = []

HEBREW_TEXT = "שלום עולם זה טקסט בדיקה לחילוץ טקסט"


def check(name: str, condition: bool) -> None:
    _results.append(condition)
    print(f"  {'OK' if condition else 'FAIL'} {name}")
    if not condition:
        print("       ^ unexpected result", file=sys.stderr)


def _write_bytes(dir_path: str, name: str, data: bytes) -> str:
    path = os.path.join(dir_path, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _make_epub(dir_path: str, name: str, sections: list[str]) -> str:
    """Build a minimal .epub-shaped zip with one .xhtml file per section."""
    path = os.path.join(dir_path, name)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        for idx, section_html in enumerate(sections, start=1):
            archive.writestr(f"OEBPS/chapter_{idx:02d}.xhtml", section_html)
    return path


# ── Test 1: TXT extraction reads UTF-8 Hebrew correctly ─────────────────────
print("\n[1] TXT extraction reads UTF-8 Hebrew correctly:")
tmp_dir = tempfile.mkdtemp(prefix="text_extraction_txt_utf8_test_")
try:
    content = f"{HEBREW_TEXT}\nשורה שנייה בעברית\n"
    path = _write_bytes(tmp_dir, "book.txt", content.encode("utf-8"))

    text, meta = extract_text_from_txt(path)
    check("text matches the original Hebrew content", text == content)
    check("encoding_used reported as utf-8 (no BOM)", meta == {"encoding_used": "utf-8", "has_bom": False})

    result = extract_native_text(path)
    check("extraction_method is txt_native", result["extraction_method"] == "txt_native")
    check("format_detected is txt", result["format_detected"] == "txt")
    check("extracted text matches original", result["text"] == content)
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 2: TXT extraction handles utf-8-sig (BOM) ──────────────────────────
print("\n[2] TXT extraction handles utf-8-sig (BOM):")
tmp_dir = tempfile.mkdtemp(prefix="text_extraction_txt_bom_test_")
try:
    content = f"{HEBREW_TEXT}\r\nשורה שנייה\r\n"
    raw = b"\xef\xbb\xbf" + content.encode("utf-8")
    path = _write_bytes(tmp_dir, "book_with_bom.txt", raw)

    text, meta = extract_text_from_txt(path)
    check("BOM stripped from extracted text", not text.startswith("﻿"))
    check("CRLF normalized to LF", "\r" not in text and text == content.replace("\r\n", "\n"))
    check("has_bom reported True", meta["has_bom"] is True)
    check("encoding_used reported as utf-8-sig", meta["encoding_used"] == "utf-8-sig")
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 3: save_text_extraction_outputs writes to explicit temp paths ──────
print("\n[3] save_text_extraction_outputs writes corpus + report to explicit paths:")
tmp_dir = tempfile.mkdtemp(prefix="text_extraction_save_test_")
try:
    content = HEBREW_TEXT * 5
    source_path = _write_bytes(tmp_dir, "book.txt", content.encode("utf-8"))
    corpus_path = os.path.join(tmp_dir, "raw", "source_corpus.txt")
    report_path = os.path.join(tmp_dir, "raw", "extraction_report.json")

    outcome = save_text_extraction_outputs(source_path, corpus_path, report_path, book_id="misparei_bayit", source_id="src-1")
    check("source_corpus.txt written", os.path.isfile(corpus_path))
    check("extraction_report.json written", os.path.isfile(report_path))

    with open(corpus_path, "r", encoding="utf-8") as fh:
        written_corpus = fh.read()
    check("written corpus matches extracted text", written_corpus == outcome["text"] == content)

    loaded_report = load_json(report_path)
    check("loaded report matches returned report", loaded_report == outcome["extraction_report"])
    check("returned dict has documented keys", all(k in outcome for k in ("corpus_path", "report_path", "extraction_report", "text")))

    for bad_path in ("", None):
        try:
            save_text_extraction_outputs(source_path, bad_path, report_path)  # type: ignore[arg-type]
            check(f"rejects empty/None corpus_output_path={bad_path!r}", False)
        except ValueError:
            check(f"rejects empty/None corpus_output_path={bad_path!r}", True)
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 4: extraction_report has expected fields and status ────────────────
print("\n[4] extraction_report has expected fields and a valid status:")
tmp_dir = tempfile.mkdtemp(prefix="text_extraction_report_fields_test_")
try:
    content = HEBREW_TEXT * 5
    source_path = _write_bytes(tmp_dir, "book.txt", content.encode("utf-8"))
    result = extract_native_text(source_path)
    report = build_extraction_report(result, source_path=source_path, book_id="misparei_bayit", source_id="src-2")

    check("report has all documented fields", all(k in report for k in (
        "book_id", "source_id", "source_path", "format_detected", "extraction_method",
        "total_chars", "non_whitespace_chars", "pages_or_sections_count",
        "status", "issues", "warnings", "created_at",
    )))
    check("status is one of the valid statuses", report["status"] in VALID_EXTRACTION_STATUSES)
    check("extraction_method is one of the valid methods", report["extraction_method"] in VALID_EXTRACTION_METHODS)
    check("status is pass for clean Hebrew text", report["status"] == "pass")
    check("total_chars matches extracted text length", report["total_chars"] == len(result["text"]))
    check("non_whitespace_chars <= total_chars", report["non_whitespace_chars"] <= report["total_chars"])
    check("book_id passed through", report["book_id"] == "misparei_bayit")
    check("source_id passed through", report["source_id"] == "src-2")
    check("created_at looks like an ISO8601 UTC timestamp", isinstance(report["created_at"], str) and report["created_at"].endswith("Z"))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 5: missing source file raises FileNotFoundError ────────────────────
print("\n[5] Missing source file raises FileNotFoundError:")
tmp_dir = tempfile.mkdtemp(prefix="text_extraction_missing_source_test_")
try:
    missing_path = os.path.join(tmp_dir, "does_not_exist.txt")
    try:
        extract_native_text(missing_path)
        check("extract_native_text raises FileNotFoundError for missing file", False)
    except FileNotFoundError:
        check("extract_native_text raises FileNotFoundError for missing file", True)

    try:
        save_text_extraction_outputs(missing_path, os.path.join(tmp_dir, "corpus.txt"), os.path.join(tmp_dir, "report.json"))
        check("save_text_extraction_outputs raises FileNotFoundError for missing file", False)
    except FileNotFoundError:
        check("save_text_extraction_outputs raises FileNotFoundError for missing file", True)
    check("no output files left behind for the missing-source case", not os.listdir(tmp_dir))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 6: unsupported extension returns a controlled result, not a crash ──
print("\n[6] Unsupported extension returns a controlled unsupported result:")
tmp_dir = tempfile.mkdtemp(prefix="text_extraction_unsupported_test_")
try:
    docx_path = _write_bytes(tmp_dir, "book.docx", b"not a real docx, just bytes")
    result = extract_native_text(docx_path)
    check("does not crash on an unsupported extension", True)
    check("extraction_method is unsupported", result["extraction_method"] == "unsupported")
    check("format_detected is unknown", result["format_detected"] == "unknown")
    check("issues contains unsupported_format", "unsupported_format" in result["issues"])
    check("text is empty for unsupported format", result["text"] == "")

    report = build_extraction_report(result, source_path=docx_path)
    check("report status is unsupported", report["status"] == "unsupported")
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 7: no production path is required or hardcoded ─────────────────────
print("\n[7] No production path is required or hardcoded:")
_source = inspect.getsource(te)
check("module source has no hardcoded book_jobs path literal", not any(
    token in _source for token in ("\\book_jobs\\", "/book_jobs/", '"book_jobs"', "'book_jobs'")
))
check("module source has no 'web_server' reference", "web_server" not in _source)
check("module source has no drive-letter production path literal", not any(
    token in _source for token in ("C:\\\\", "D:\\\\", "/var/", "/srv/")
))
tmp_dir = tempfile.mkdtemp(prefix="text_extraction_no_prod_path_test_")
try:
    source_path = _write_bytes(tmp_dir, "book.txt", (HEBREW_TEXT * 5).encode("utf-8"))
    corpus_path = os.path.join(tmp_dir, "out", "source_corpus.txt")
    report_path = os.path.join(tmp_dir, "out", "extraction_report.json")
    save_text_extraction_outputs(source_path, corpus_path, report_path)
    check("outputs written only under the explicit temp paths given", os.path.isfile(corpus_path) and os.path.isfile(report_path))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 8: no OCR/model/API functions or imports exist ─────────────────────
print("\n[8] No OCR/model/API functions or imports exist:")
_module_names = " ".join(dir(te)).lower()
_forbidden_name_tokens = ("ocr", "tesseract", "openai", "anthropic", "requests", "model_call", "qwen", "ollama")
check("no OCR/model/API tokens in module's public names", not any(tok in _module_names for tok in _forbidden_name_tokens))

# Code-level patterns only — the module's own safety docstrings legitimately
# say things like "This is NOT OCR", so a bare substring match on "ocr" would
# false-positive on the documentation describing what this module refuses to do.
_forbidden_code_patterns = (
    "import requests", "import openai", "import anthropic", "import pytesseract",
    "tesseract", "pytesseract", "ocr_engine", ".ocr(", "def ocr", "openai.", "anthropic.",
    "requests.post", "requests.get", "qwen", "ollama", "localhost:11434",
)
check("module source has no OCR/model/API call patterns", not any(pat in _source for pat in _forbidden_code_patterns))
_import_lines = [line.strip() for line in _source.splitlines() if line.strip().startswith(("import ", "from "))]
_allowed_import_prefixes = ("import os", "import zipfile", "from html.parser", "from book_job_record", "import fitz", "from __future__")
check("module only imports stdlib + book_job_record + optional fitz", all(
    any(line.startswith(prefix) for prefix in _allowed_import_prefixes) for line in _import_lines
))


# ── Optional: EPUB simple extraction (implemented with stdlib zipfile+HTML) ─
print("\n[9] EPUB extraction — minimal stdlib zipfile + HTML stripping:")
tmp_dir = tempfile.mkdtemp(prefix="text_extraction_epub_test_")
try:
    epub_path = _make_epub(tmp_dir, "book.epub", [
        f"<html><head><style>body {{color:red}}</style></head><body><h1>{HEBREW_TEXT}</h1><p>פרק ראשון</p></body></html>",
        f"<html><body><script>var x = 1;</script><p>פרק שני: {HEBREW_TEXT}</p></body></html>",
    ])
    text, meta = extract_text_from_epub(epub_path)
    check("epub text contains content from both chapters", "פרק ראשון" in text and "פרק שני" in text)
    check("epub text excludes <style> content", "color:red" not in text)
    check("epub text excludes <script> content", "var x = 1" not in text)
    check("sections_count matches number of content files", meta["sections_count"] == 2)

    result = extract_native_text(epub_path)
    check("extraction_method is epub_native", result["extraction_method"] == "epub_native")
    check("pages_or_sections_count reported", result["pages_or_sections_count"] == 2)
    check("no warnings for a normal epub", result["warnings"] == [])

    empty_epub_path = _make_epub(tmp_dir, "empty.epub", [])
    empty_result = extract_native_text(empty_epub_path)
    check("empty epub still reports epub_native (not a crash)", empty_result["extraction_method"] == "epub_native")
    check("empty epub gets a no-content warning", "epub_no_content_sections_found" in empty_result["warnings"])

    not_a_zip_path = _write_bytes(tmp_dir, "broken.epub", b"this is not a zip file")
    broken_result = extract_native_text(not_a_zip_path)
    check("malformed epub returns controlled unsupported result", broken_result["extraction_method"] == "unsupported")
    check("malformed epub reports unsupported_epub issue", "unsupported_epub" in broken_result["issues"])
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Optional: PDF native extraction — only meaningful if `fitz` is present ──
print("\n[10] PDF native extraction:")
if te._FITZ_AVAILABLE:
    tmp_dir = tempfile.mkdtemp(prefix="text_extraction_pdf_test_")
    try:
        pdf_path = os.path.join(tmp_dir, "book.pdf")
        doc = te.fitz.open()
        try:
            page = doc.new_page()
            page.insert_text((72, 72), HEBREW_TEXT, fontname="helv")
            doc.save(pdf_path)
        finally:
            doc.close()

        result = extract_native_text(pdf_path)
        check("extraction_method is pdf_native (fitz available)", result["extraction_method"] == "pdf_native")
        check("format_detected is pdf", result["format_detected"] == "pdf")
        check("pages_or_sections_count is 1", result["pages_or_sections_count"] == 1)
        check("does not OCR (pdf_native only, no ocr token in method)", "ocr" not in result["extraction_method"])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
else:
    print("  SKIPPED — `fitz`/PyMuPDF is not importable in this environment;")
    print("  per the brief, PDFs are reported as 'unsupported_pdf_native_missing_dependency'")
    print("  and no dependency is installed to make this test runnable.")
    tmp_dir = tempfile.mkdtemp(prefix="text_extraction_pdf_missing_dep_test_")
    try:
        pdf_path = _write_bytes(tmp_dir, "book.pdf", b"%PDF-1.4 not a real pdf")
        result = extract_native_text(pdf_path)
        check("pdf reported as unsupported when fitz is missing", result["extraction_method"] == "unsupported")
        check("issue is unsupported_pdf_native_missing_dependency", "unsupported_pdf_native_missing_dependency" in result["issues"])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Summary ──────────────────────────────────────────────────────────────────
total = len(_results)
passed = sum(_results)
failed = total - passed
print(f"\n{'='*50}")
print(f"תוצאות: {passed}/{total} בדיקות עברו" + (f" | {failed} נכשלו" if failed else ""))
sys.exit(0 if failed == 0 else 1)
