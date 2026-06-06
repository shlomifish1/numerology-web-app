"""
Minimal self-contained tests for book_intake_pipeline.
No external deps. No model/API/OCR calls. Run with: py -3.12 test_book_intake_pipeline.py

All directory-creation and file-writing tests use a temporary directory
only — never a production path. Source "books" are tiny throwaway text
files created inside the same temp dir.
"""

import os
import shutil
import sys
import tempfile

from book_job_record import VALID_JOB_STATUSES, load_json
from corpus_quality import LOW_QUALITY_CHARS_THRESHOLD, LOW_QUALITY_HEBREW_RATIO
from book_intake_pipeline import run_native_book_intake_pipeline

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_results: list[bool] = []

HEBREW_SENTENCE = "שלום עולם זה טקסט בדיקה תקין בעברית לצורך הרצת צינור הקליטה "


def check(name: str, condition: bool) -> None:
    _results.append(condition)
    print(f"  {'OK' if condition else 'FAIL'} {name}")
    if not condition:
        print("       ^ unexpected result", file=sys.stderr)


def _write_source_file(dir_path: str, name: str, content: bytes) -> str:
    path = os.path.join(dir_path, name)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def _list_all_files(root: str) -> list[str]:
    found = []
    for current_dir, _dirs, files in os.walk(root):
        for name in files:
            found.append(os.path.join(current_dir, name))
    return found


# ── Test 1+9: valid Hebrew TXT — full artifact set + result paths ───────────
print("\n[1+9] Valid UTF-8 Hebrew TXT source — creates the full artifact set:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_happy_test_")
try:
    original_text = HEBREW_SENTENCE * 40
    source_path = _write_source_file(tmp_dir, "book.txt", original_text.encode("utf-8"))
    base_dir = os.path.join(tmp_dir, "jobs")

    result = run_native_book_intake_pipeline(base_dir, source_path, "misparei_bayit", created_by="manual")

    job_dir = result["job_dir"]
    check("job_dir created under base_dir", job_dir.startswith(base_dir))
    check("result has job_id", isinstance(result["job_id"], str) and bool(result["job_id"]))

    check("job_record.json exists", os.path.isfile(result["job_record_path"]))
    check("raw/source_manifest.json exists", os.path.isfile(result["source_manifest_path"]))
    check("raw/source_corpus.txt exists", os.path.isfile(result["source_corpus_path"]))
    check("raw/extraction_report.json exists", os.path.isfile(result["extraction_report_path"]))
    check("analysis/corpus_quality_report.json exists", os.path.isfile(result["corpus_quality_report_path"]))

    check("source_corpus_path matches the canonical raw/ path", result["source_corpus_path"] == os.path.join(job_dir, "raw", "source_corpus.txt"))
    check("extraction_report_path matches the canonical raw/ path", result["extraction_report_path"] == os.path.join(job_dir, "raw", "extraction_report.json"))
    check("corpus_quality_report_path matches the canonical analysis/ path", result["corpus_quality_report_path"] == os.path.join(job_dir, "analysis", "corpus_quality_report.json"))

    check("extraction_report present in result", isinstance(result["extraction_report"], dict))
    check("corpus_quality_report present in result", isinstance(result["corpus_quality_report"], dict))
    check("final_status is a valid job status", result["final_status"] in VALID_JOB_STATUSES)
    check("warnings is a list", isinstance(result["warnings"], list))
    check("issues is a list", isinstance(result["issues"], list))
finally:
    happy_job_dir = result["job_dir"]
    happy_text = original_text
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 2: extracted corpus matches the original text (line-ending safe) ───
print("\n[2] Extracted source_corpus.txt matches the original content:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_corpus_match_test_")
try:
    original_text = f"{HEBREW_SENTENCE}\r\nשורה שנייה\r\n{HEBREW_SENTENCE}" * 10
    source_path = _write_source_file(tmp_dir, "book.txt", original_text.encode("utf-8"))
    base_dir = os.path.join(tmp_dir, "jobs")

    result = run_native_book_intake_pipeline(base_dir, source_path, "misparei_bayit")
    with open(result["source_corpus_path"], "r", encoding="utf-8") as fh:
        written_corpus = fh.read()

    normalized_original = original_text.replace("\r\n", "\n").replace("\r", "\n")
    check("written corpus equals the line-ending-normalized original", written_corpus == normalized_original)
    check("written corpus equals the extraction_report's reported text length", len(written_corpus) == result["extraction_report"]["total_chars"])
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 3: long valid Hebrew corpus -> corpus quality is pass or warn ───────
print("\n[3] Long valid Hebrew corpus -> corpus quality report is pass or warn, job completes:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_quality_pass_test_")
try:
    original_text = HEBREW_SENTENCE * 60
    check("source text is well above the low-quality length threshold", len(original_text) >= LOW_QUALITY_CHARS_THRESHOLD * 2)
    source_path = _write_source_file(tmp_dir, "book.txt", original_text.encode("utf-8"))
    base_dir = os.path.join(tmp_dir, "jobs")

    result = run_native_book_intake_pipeline(base_dir, source_path, "misparei_bayit")
    cqr = result["corpus_quality_report"]
    check("corpus_quality_report status is pass or warn", cqr["status"] in ("pass", "warn"))
    check("estimated_hebrew_ratio is above the low-quality threshold", cqr["estimated_hebrew_ratio"] >= LOW_QUALITY_HEBREW_RATIO)
    check("final_status reflects a non-failed outcome", result["final_status"] in ("completed", "corpus_quality_check"))

    job_record = load_json(result["job_record_path"])
    check("job_record status matches final_status", job_record["status"] == result["final_status"])
    check("job_record current_stage is corpus_quality_check", job_record["current_stage"] == "corpus_quality_check")
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 4: short/low-quality corpus -> controlled failed status, no crash ──
print("\n[4] Short/low-quality corpus -> controlled failed_recoverable status, not a crash:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_quality_fail_test_")
try:
    short_text = "טקסט קצר מדי"
    check("short text really is below the low-quality length threshold", len(short_text) < LOW_QUALITY_CHARS_THRESHOLD)
    source_path = _write_source_file(tmp_dir, "book.txt", short_text.encode("utf-8"))
    base_dir = os.path.join(tmp_dir, "jobs")

    result = run_native_book_intake_pipeline(base_dir, source_path, "misparei_bayit")
    check("does not crash on a short/low-quality corpus", True)
    check("corpus_quality_report status is fail", result["corpus_quality_report"]["status"] == "fail")
    check("final_status is failed_recoverable", result["final_status"] == "failed_recoverable")
    check("issues include the corpus_quality issue", any(issue in result["issues"] for issue in ("corpus_too_short", "corpus_empty", "low_hebrew_ratio")))

    job_record = load_json(result["job_record_path"])
    check("job_record status is failed_recoverable", job_record["status"] == "failed_recoverable")
    check("job_record current_stage is corpus_quality_check", job_record["current_stage"] == "corpus_quality_check")
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 5: unsupported extension -> controlled failure, no crash ───────────
print("\n[5] Unsupported extension -> controlled failed_unrecoverable status, not a crash:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_unsupported_test_")
try:
    source_path = _write_source_file(tmp_dir, "book.docx", b"not a real docx, just bytes")
    base_dir = os.path.join(tmp_dir, "jobs")

    result = run_native_book_intake_pipeline(base_dir, source_path, "misparei_bayit")
    check("does not crash on an unsupported extension", True)
    check("extraction_report extraction_method is unsupported", result["extraction_report"]["extraction_method"] == "unsupported")
    check("corpus_quality_report is None (pipeline stops at extraction)", result["corpus_quality_report"] is None)
    check("corpus_quality_report_path is None", result["corpus_quality_report_path"] is None)
    check("final_status is failed_unrecoverable", result["final_status"] == "failed_unrecoverable")
    check("issues include unsupported_format", "unsupported_format" in result["issues"])

    job_record = load_json(result["job_record_path"])
    check("job_record status is failed_unrecoverable", job_record["status"] == "failed_unrecoverable")
    check("job_record current_stage is extracting_text", job_record["current_stage"] == "extracting_text")
    check("no analysis/corpus_quality_report.json was written", not os.path.isfile(os.path.join(result["job_dir"], "analysis", "corpus_quality_report.json")))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 6: missing source file raises FileNotFoundError ────────────────────
print("\n[6] Missing source file raises FileNotFoundError:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_missing_source_test_")
try:
    missing_path = os.path.join(tmp_dir, "does_not_exist.txt")
    base_dir = os.path.join(tmp_dir, "jobs")
    try:
        run_native_book_intake_pipeline(base_dir, missing_path, "misparei_bayit")
        check("raises FileNotFoundError for a missing source file", False)
    except FileNotFoundError:
        check("raises FileNotFoundError for a missing source file", True)
    check("no job directory was created for the missing-source case", not os.path.isdir(base_dir))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 7: empty/missing base_dir raises ValueError ────────────────────────
print("\n[7] Empty/missing base_dir raises ValueError:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_bad_base_dir_test_")
try:
    source_path = _write_source_file(tmp_dir, "book.txt", (HEBREW_SENTENCE * 5).encode("utf-8"))
    for bad_base_dir in ("", None):
        try:
            run_native_book_intake_pipeline(bad_base_dir, source_path, "misparei_bayit")  # type: ignore[arg-type]
            check(f"rejects empty/None base_dir={bad_base_dir!r}", False)
        except ValueError:
            check(f"rejects empty/None base_dir={bad_base_dir!r}", True)
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 8: no source file copy is created inside the job directory ─────────
print("\n[8] No source file copy exists inside the job directory:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_no_copy_test_")
try:
    original_bytes = (HEBREW_SENTENCE * 30).encode("utf-8")
    source_path = _write_source_file(tmp_dir, "original_book.txt", original_bytes)
    base_dir = os.path.join(tmp_dir, "jobs")

    result = run_native_book_intake_pipeline(base_dir, source_path, "misparei_bayit")
    job_files = _list_all_files(result["job_dir"])

    check("original source filename does not appear anywhere in the job dir", not any(os.path.basename(p) == "original_book.txt" for p in job_files))
    # The canonical raw/source_corpus.txt is *expected* to contain the same
    # text as a clean UTF-8/LF source file — that is native extraction working
    # correctly, not a copy. The anti-bloat guarantee is that no *additional*
    # file (e.g. a binary duplicate of the original source) exists beyond it.
    files_with_original_bytes = [p for p in job_files if open(p, "rb").read() == original_bytes]
    check("original source bytes appear only in the canonical raw/source_corpus.txt (native extraction, not a copy)",
          files_with_original_bytes == [os.path.join(result["job_dir"], "raw", "source_corpus.txt")])

    manifest = load_json(result["source_manifest_path"])
    check("source_manifest references the original source path (metadata only)", manifest["source_path"] == os.path.abspath(source_path))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 9 (artifacts map): job_record artifacts include the expected paths ─
print("\n[9] job_record.json artifacts map includes the expected canonical paths:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_artifacts_map_test_")
try:
    source_path = _write_source_file(tmp_dir, "book.txt", (HEBREW_SENTENCE * 60).encode("utf-8"))
    base_dir = os.path.join(tmp_dir, "jobs")

    result = run_native_book_intake_pipeline(base_dir, source_path, "misparei_bayit")
    job_record = load_json(result["job_record_path"])
    artifact_values = set(job_record["artifacts"].values())

    check("artifacts include raw/source_manifest.json", "raw/source_manifest.json" in artifact_values)
    check("artifacts include raw/source_corpus.txt", "raw/source_corpus.txt" in artifact_values)
    check("artifacts include raw/extraction_report.json", "raw/extraction_report.json" in artifact_values)
    check("artifacts include analysis/corpus_quality_report.json", "analysis/corpus_quality_report.json" in artifact_values)
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 10: all writes are confined to the temp base_dir ───────────────────
print("\n[10] All writes are confined to the temp base_dir:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_pipeline_confinement_test_")
try:
    source_path = _write_source_file(tmp_dir, "book.txt", (HEBREW_SENTENCE * 30).encode("utf-8"))
    base_dir = os.path.join(tmp_dir, "jobs")
    before_siblings = set(os.listdir(tmp_dir))

    result = run_native_book_intake_pipeline(base_dir, source_path, "misparei_bayit")
    after_siblings = set(os.listdir(tmp_dir))

    check("no new entries appeared as siblings of base_dir", after_siblings - before_siblings == {"jobs"} or after_siblings == before_siblings | {"jobs"})
    check("every reported artifact path lives under base_dir", all(
        path is None or os.path.abspath(path).startswith(os.path.abspath(base_dir))
        for path in (
            result["job_record_path"], result["source_manifest_path"], result["source_corpus_path"],
            result["extraction_report_path"], result["corpus_quality_report_path"],
        )
    ))
    check("job_dir itself lives under base_dir", os.path.abspath(result["job_dir"]).startswith(os.path.abspath(base_dir)))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 11: module source has no production path / OCR / model / API code ──
print("\n[11] No production path or OCR/model/API code in the module source:")
import inspect
import book_intake_pipeline as bip
_source = inspect.getsource(bip)
check("module source has no hardcoded book_jobs path literal", not any(
    token in _source for token in ("\\book_jobs\\", "/book_jobs/", '"book_jobs"', "'book_jobs'")
))
check("module source has no 'web_server' reference", "web_server" not in _source)
_forbidden_code_patterns = (
    "import requests", "import openai", "import anthropic", "import pytesseract",
    "tesseract", "pytesseract", "ocr_engine", ".ocr(", "def ocr", "openai.", "anthropic.",
    "requests.post", "requests.get", "qwen", "ollama", "localhost:11434",
)
check("module source has no OCR/model/API call patterns", not any(pat in _source for pat in _forbidden_code_patterns))
# Use the AST (not naive line-prefix scanning) so that prose in the
# docstring — e.g. "...propagated from initialize_book_intake_job)..." —
# can never be mistaken for an import statement.
import ast
_tree = ast.parse(_source)
_imported_modules = []
for node in ast.walk(_tree):
    if isinstance(node, ast.Import):
        _imported_modules.extend(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom):
        _imported_modules.append(node.module)
_allowed_modules = {"__future__", "os", "book_job_record", "book_intake_job", "text_extraction", "corpus_quality"}
check("module only imports stdlib + the existing model_lab foundations",
      bool(_imported_modules) and all(name in _allowed_modules for name in _imported_modules))


# ── Summary ──────────────────────────────────────────────────────────────────
total = len(_results)
passed = sum(_results)
failed = total - passed
print(f"\n{'='*50}")
print(f"תוצאות: {passed}/{total} בדיקות עברו" + (f" | {failed} נכשלו" if failed else ""))
sys.exit(0 if failed == 0 else 1)
