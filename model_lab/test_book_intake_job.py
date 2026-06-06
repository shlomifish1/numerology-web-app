"""
Minimal self-contained tests for book_intake_job.
No external deps. No model/API/OCR calls. Run with: py -3.12 test_book_intake_job.py

All directory-creation and file-writing tests use a temporary directory
only — never a production path. Source "books" are tiny throwaway text
files created inside the same temp dir.
"""

import hashlib
import os
import shutil
import sys
import tempfile

from book_job_record import ARTIFACT_SECTIONS, BookJobRecord, load_json, validate_record_dict
from book_intake_job import (
    JOB_RECORD_FILENAME,
    SOURCE_MANIFEST_RELATIVE_PATH,
    build_source_manifest,
    compute_sha256,
    detect_source_format,
    initialize_book_intake_job,
)

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_results: list[bool] = []


def check(name: str, condition: bool) -> None:
    _results.append(condition)
    print(f"  {'OK' if condition else 'FAIL'} {name}")
    if not condition:
        print("       ^ unexpected result", file=sys.stderr)


def _write_source_file(dir_path: str, name: str = "demo_book.txt", content: bytes = b"hello book lab\n") -> str:
    path = os.path.join(dir_path, name)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


# ── Test 1: detect_source_format — extension-based only ─────────────────────
print("\n[1] detect_source_format — extension-based detection:")
check("detects .pdf", detect_source_format("book.pdf") == "pdf")
check("detects .epub", detect_source_format("book.epub") == "epub")
check("detects .txt", detect_source_format("book.txt") == "txt")
check("case-insensitive extension", detect_source_format("BOOK.PDF") == "pdf")
check("unknown extension maps to 'unknown'", detect_source_format("book.docx") == "unknown")
check("missing extension maps to 'unknown'", detect_source_format("book") == "unknown")


# ── Test 2: compute_sha256 — correct, stable file hash ───────────────────────
print("\n[2] compute_sha256 — matches hashlib reference and is stable:")
tmp_dir = tempfile.mkdtemp(prefix="book_intake_job_hash_test_")
try:
    content = b"the quick brown fox jumps over the lazy dog\n" * 100
    path = _write_source_file(tmp_dir, "sample.txt", content)
    expected = hashlib.sha256(content).hexdigest()
    check("hash matches hashlib reference", compute_sha256(path) == expected)
    check("hash is stable across repeated calls", compute_sha256(path) == compute_sha256(path))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 3: build_source_manifest — shape and fixed status ──────────────────
print("\n[3] build_source_manifest — required fields and fixed status:")
manifest = build_source_manifest(
    job_id="job-1", book_id="misparei_bayit", source_id="deadbeef",
    original_filename="book.pdf", source_path="C:/tmp/book.pdf",
    file_size_bytes=123, format_detected="pdf", language_hint="he",
    intake_timestamp="2026-06-06T12:00:00Z", created_by="dev/manual",
)
check("manifest has all expected fields", all(k in manifest for k in (
    "job_id", "book_id", "source_id", "original_filename", "source_path",
    "file_size_bytes", "format_detected", "language_hint",
    "intake_timestamp", "created_by", "status",
)))
check("manifest status is fixed to pending_approval", manifest["status"] == "pending_approval")
check("book_title omitted when not provided", "book_title" not in manifest)

manifest_with_title = build_source_manifest(
    job_id="job-1", book_id="misparei_bayit", source_id="deadbeef",
    original_filename="book.pdf", source_path="C:/tmp/book.pdf",
    file_size_bytes=123, format_detected="pdf", language_hint="he",
    intake_timestamp="2026-06-06T12:00:00Z", created_by="dev/manual",
    book_title="Misparei HaBayit",
)
check("book_title included when provided", manifest_with_title.get("book_title") == "Misparei HaBayit")


# ── Test 4: initialize_book_intake_job — creates expected directory tree ────
print("\n[4] initialize_book_intake_job — creates job_dir with artifact sections:")
tmp_base = tempfile.mkdtemp(prefix="book_intake_job_init_test_")
try:
    source_dir = tempfile.mkdtemp(prefix="book_intake_job_source_", dir=tmp_base)
    source_path = _write_source_file(source_dir, "demo_book.txt")

    result = initialize_book_intake_job(tmp_base, source_path, "misparei_bayit", language_hint="he")
    job_dir = result["job_dir"]

    check("job_dir created under base_dir", os.path.isdir(job_dir))
    check("job_dir is inside the temp base_dir", os.path.commonpath(
        [os.path.abspath(tmp_base), os.path.abspath(job_dir)]
    ) == os.path.abspath(tmp_base))
    check("all canonical artifact section dirs exist", all(
        os.path.isdir(os.path.join(job_dir, section)) for section in ARTIFACT_SECTIONS
    ))
    check("job_record.json written to job_dir root", os.path.isfile(os.path.join(job_dir, JOB_RECORD_FILENAME)))
    check("source_manifest.json written under raw/", os.path.isfile(
        os.path.join(job_dir, *SOURCE_MANIFEST_RELATIVE_PATH.split("/"))
    ))
finally:
    shutil.rmtree(tmp_base, ignore_errors=True)


# ── Test 5: source_manifest.json — written values match the source file ─────
print("\n[5] source_manifest.json — values match the actual source file:")
tmp_base = tempfile.mkdtemp(prefix="book_intake_job_manifest_test_")
try:
    source_dir = tempfile.mkdtemp(prefix="book_intake_job_source_", dir=tmp_base)
    content = b"draft chapter content for the manifest test\n"
    source_path = _write_source_file(source_dir, "draft_book.PDF", content)

    result = initialize_book_intake_job(
        tmp_base, source_path, "misparei_bayit",
        book_title="Misparei HaBayit", created_by="dev/manual", language_hint="he",
    )
    on_disk = load_json(result["source_manifest_path"])

    check("source_id equals sha256 of the source file", on_disk["source_id"] == hashlib.sha256(content).hexdigest())
    check("original_filename matches basename", on_disk["original_filename"] == "draft_book.PDF")
    check("source_path is an absolute path to the source file", os.path.isabs(on_disk["source_path"])
          and os.path.abspath(on_disk["source_path"]) == os.path.abspath(source_path))
    check("file_size_bytes matches actual size", on_disk["file_size_bytes"] == os.path.getsize(source_path))
    check("format_detected derived from extension (case-insensitive)", on_disk["format_detected"] == "pdf")
    check("language_hint passed through", on_disk["language_hint"] == "he")
    check("book_title passed through when provided", on_disk.get("book_title") == "Misparei HaBayit")
    check("status is pending_approval", on_disk["status"] == "pending_approval")
    check("job_id matches the returned job_id", on_disk["job_id"] == result["job_id"])
    check("book_id matches the requested book_id", on_disk["book_id"] == "misparei_bayit")
finally:
    shutil.rmtree(tmp_base, ignore_errors=True)


# ── Test 6: job_record.json — valid BookJobRecord in intake_pending ─────────
print("\n[6] job_record.json — valid BookJobRecord, status=intake_pending:")
tmp_base = tempfile.mkdtemp(prefix="book_intake_job_record_test_")
try:
    source_dir = tempfile.mkdtemp(prefix="book_intake_job_source_", dir=tmp_base)
    source_path = _write_source_file(source_dir)

    result = initialize_book_intake_job(tmp_base, source_path, "misparei_bayit", created_by="dev/manual")
    raw = load_json(result["job_record_path"])
    validate_record_dict(raw)
    check("job_record.json passes validate_record_dict", True)

    loaded = BookJobRecord.load_json(result["job_record_path"])
    check("status is intake_pending", loaded.status == "intake_pending")
    check("current_stage is intake", loaded.current_stage == "intake")
    check("job_id matches the returned job_id", loaded.job_id == result["job_id"])
    check("book_id matches the requested book_id", loaded.book_id == "misparei_bayit")
    check("created_by passed through", loaded.created_by == "dev/manual")
    check("artifacts references the source manifest path", loaded.artifacts.get("source_manifest") == SOURCE_MANIFEST_RELATIVE_PATH)
finally:
    shutil.rmtree(tmp_base, ignore_errors=True)


# ── Test 7: returned result dict — documented keys match the files on disk ──
print("\n[7] returned result — documented keys present and consistent with disk:")
tmp_base = tempfile.mkdtemp(prefix="book_intake_job_result_test_")
try:
    source_dir = tempfile.mkdtemp(prefix="book_intake_job_source_", dir=tmp_base)
    source_path = _write_source_file(source_dir)

    result = initialize_book_intake_job(tmp_base, source_path, "misparei_bayit")
    check("result has all documented keys", all(k in result for k in (
        "job_id", "job_dir", "source_manifest_path", "job_record_path", "job_record", "source_manifest",
    )))
    check("job_record is a BookJobRecord instance", isinstance(result["job_record"], BookJobRecord))
    check("source_manifest_path points at an existing file", os.path.isfile(result["source_manifest_path"]))
    check("job_record_path points at an existing file", os.path.isfile(result["job_record_path"]))
    check("source_manifest dict matches the file on disk", result["source_manifest"] == load_json(result["source_manifest_path"]))
    check("job_record matches the file on disk", result["job_record"].to_dict() == load_json(result["job_record_path"]))
finally:
    shutil.rmtree(tmp_base, ignore_errors=True)


# ── Test 8: explicit job_id is honored consistently ─────────────────────────
print("\n[8] explicit job_id — honored consistently across dir/manifest/record:")
tmp_base = tempfile.mkdtemp(prefix="book_intake_job_explicit_id_test_")
try:
    source_dir = tempfile.mkdtemp(prefix="book_intake_job_source_", dir=tmp_base)
    source_path = _write_source_file(source_dir)
    explicit_id = "11111111-2222-3333-4444-555555555555"

    result = initialize_book_intake_job(tmp_base, source_path, "misparei_bayit", job_id=explicit_id)
    check("returned job_id equals the explicit job_id", result["job_id"] == explicit_id)
    check("job_dir is named after the explicit job_id", os.path.basename(result["job_dir"]) == explicit_id)
    check("source_manifest job_id matches explicit job_id", result["source_manifest"]["job_id"] == explicit_id)
    check("job_record job_id matches explicit job_id", result["job_record"].job_id == explicit_id)
finally:
    shutil.rmtree(tmp_base, ignore_errors=True)


# ── Test 9: validation errors — base_dir / book_id ──────────────────────────
print("\n[9] validation errors — base_dir and book_id must be non-empty strings:")
tmp_base = tempfile.mkdtemp(prefix="book_intake_job_validation_test_")
try:
    source_dir = tempfile.mkdtemp(prefix="book_intake_job_source_", dir=tmp_base)
    source_path = _write_source_file(source_dir)

    for bad_base_dir in ("", None):
        try:
            initialize_book_intake_job(bad_base_dir, source_path, "misparei_bayit")  # type: ignore[arg-type]
            check(f"rejects base_dir={bad_base_dir!r}", False)
        except ValueError:
            check(f"rejects base_dir={bad_base_dir!r}", True)

    for bad_book_id in ("", None):
        try:
            initialize_book_intake_job(tmp_base, source_path, bad_book_id)  # type: ignore[arg-type]
            check(f"rejects book_id={bad_book_id!r}", False)
        except ValueError:
            check(f"rejects book_id={bad_book_id!r}", True)
finally:
    shutil.rmtree(tmp_base, ignore_errors=True)


# ── Test 10: missing source file — FileNotFoundError, nothing left behind ───
print("\n[10] missing source file — FileNotFoundError and no job_dir created:")
tmp_base = tempfile.mkdtemp(prefix="book_intake_job_missing_source_test_")
try:
    missing_path = os.path.join(tmp_base, "does_not_exist.pdf")
    entries_before = set(os.listdir(tmp_base))
    try:
        initialize_book_intake_job(tmp_base, missing_path, "misparei_bayit")
        check("raises FileNotFoundError for a missing source file", False)
    except FileNotFoundError:
        check("raises FileNotFoundError for a missing source file", True)
    check("no job directory left behind under base_dir", set(os.listdir(tmp_base)) == entries_before)
finally:
    shutil.rmtree(tmp_base, ignore_errors=True)


# ── Summary ──────────────────────────────────────────────────────────────────
total = len(_results)
passed = sum(_results)
failed = total - passed
print(f"\n{'='*50}")
print(f"תוצאות: {passed}/{total} בדיקות עברו" + (f" | {failed} נכשלו" if failed else ""))
sys.exit(0 if failed == 0 else 1)
