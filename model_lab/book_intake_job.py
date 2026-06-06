"""
Book Lab — Book Intake Job Initializer (foundation, v0)

Local-only manual helper that opens a new book job folder, computes a
source fingerprint, writes a draft source_manifest.json, and creates a
matching job_record.json — using the existing book_job_record helpers.

This is NOT OCR, NOT text extraction, NOT a model/API call, NOT an agent
runner, NOT a queue manager, and does NOT touch runtime/server/production
paths. It only opens the source file to (a) compute its sha256 and
(b) read its size — never to read or print its content.

Source format detection is extension-based only (.pdf/.epub/.txt/unknown);
it does NOT distinguish pdf_text vs. pdf_scanned (that requires actually
parsing the file, which is out of scope for this initializer).

stdlib only. No DB. No server. No Flask. No external calls.
"""

from __future__ import annotations

import hashlib
import os
import uuid

from book_job_record import (
    BookJobRecord,
    artifact_relative_path,
    create_artifact_directories,
    save_json,
    utc_now_iso,
)

JOB_RECORD_FILENAME = "job_record.json"
SOURCE_MANIFEST_RELATIVE_PATH = artifact_relative_path("raw", "source_manifest.json")

_SHA256_CHUNK_SIZE = 1024 * 1024  # 1 MiB

_EXTENSION_FORMAT_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".epub": "epub",
    ".txt": "txt",
}
SOURCE_FORMAT_UNKNOWN = "unknown"


def detect_source_format(path: str) -> str:
    """Detect source format from the file extension only — no parsing, no content read."""
    _, ext = os.path.splitext(path)
    return _EXTENSION_FORMAT_MAP.get(ext.lower(), SOURCE_FORMAT_UNKNOWN)


def compute_sha256(path: str) -> str:
    """Compute the sha256 hex digest of a file, reading it in chunks (stdlib only)."""
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_SHA256_CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_source_manifest(
    *,
    job_id: str,
    book_id: str,
    source_id: str,
    original_filename: str,
    source_path: str,
    file_size_bytes: int,
    format_detected: str,
    language_hint: str | None,
    intake_timestamp: str,
    created_by: str,
    book_title: str | None = None,
) -> dict:
    """Build a draft source_manifest.json dict. Contains metadata only — never file content."""
    manifest = {
        "job_id": job_id,
        "book_id": book_id,
        "source_id": source_id,
        "original_filename": original_filename,
        "source_path": source_path,
        "file_size_bytes": file_size_bytes,
        "format_detected": format_detected,
        "language_hint": language_hint,
        "intake_timestamp": intake_timestamp,
        "created_by": created_by,
        "status": "pending_approval",
    }
    if book_title is not None:
        manifest["book_title"] = book_title
    return manifest


def initialize_book_intake_job(
    base_dir: str,
    source_file_path: str,
    book_id: str,
    *,
    book_title: str | None = None,
    created_by: str = "manual",
    language_hint: str | None = None,
    job_id: str | None = None,
) -> dict:
    """
    Open a new book intake job folder under an explicit base_dir.

    Creates: base_dir/{job_id}/ with the canonical artifact section dirs
    (raw/analysis/audit/output/runtime), a raw/source_manifest.json draft,
    and a job_record.json (status=intake_pending). Does NOT copy the
    source file, does NOT read its content (only hashes + sizes it), and
    never writes outside base_dir.

    Raises ValueError for a missing/invalid base_dir or book_id, and
    FileNotFoundError if source_file_path does not point to an existing file.

    Returns a dict with: job_id, job_dir, source_manifest_path,
    job_record_path, job_record, source_manifest.
    """
    if not base_dir or not isinstance(base_dir, str):
        raise ValueError("base_dir must be a non-empty string provided by the caller")
    if not book_id or not isinstance(book_id, str):
        raise ValueError("book_id must be a non-empty string")
    if not os.path.isfile(source_file_path):
        raise FileNotFoundError(f"source file not found: '{source_file_path}'")

    resolved_job_id = job_id or str(uuid.uuid4())
    job_dir = os.path.join(base_dir, resolved_job_id)
    create_artifact_directories(job_dir)

    original_filename = os.path.basename(source_file_path)
    file_size_bytes = os.path.getsize(source_file_path)
    format_detected = detect_source_format(source_file_path)
    source_id = compute_sha256(source_file_path)
    intake_timestamp = utc_now_iso()

    manifest = build_source_manifest(
        job_id=resolved_job_id,
        book_id=book_id,
        source_id=source_id,
        original_filename=original_filename,
        source_path=os.path.abspath(source_file_path),
        file_size_bytes=file_size_bytes,
        format_detected=format_detected,
        language_hint=language_hint,
        intake_timestamp=intake_timestamp,
        created_by=created_by,
        book_title=book_title,
    )

    source_manifest_path = os.path.join(job_dir, *SOURCE_MANIFEST_RELATIVE_PATH.split("/"))
    save_json(source_manifest_path, manifest)

    job_record_path = os.path.join(job_dir, JOB_RECORD_FILENAME)
    job_record = BookJobRecord(
        job_id=resolved_job_id,
        book_id=book_id,
        status="intake_pending",
        current_stage="intake",
        created_by=created_by,
        artifacts={
            "source_manifest": SOURCE_MANIFEST_RELATIVE_PATH,
            "job_record": JOB_RECORD_FILENAME,
        },
    )
    job_record.save_json(job_record_path)

    return {
        "job_id": resolved_job_id,
        "job_dir": job_dir,
        "source_manifest_path": source_manifest_path,
        "job_record_path": job_record_path,
        "job_record": job_record,
        "source_manifest": manifest,
    }
