"""
Book Lab — Native Book Intake Pipeline Runner (foundation, v0)

Local-only manual integration runner that chains the existing Phase 1
foundations end to end for a single book source:

  1. initialize_book_intake_job  (book_intake_job.py)
  2. save_text_extraction_outputs (text_extraction.py)  -- native text only
  3. analyze_corpus_text + save_corpus_quality_report (corpus_quality.py)
  4. update job_record.json's artifacts map + status/current_stage

This is NOT OCR, NOT a model/API call, NOT an agent runner, NOT a queue
manager, NOT a UI, NOT a server/runtime integration, and NOT a
runtime_promoter or deploy coordinator. It is a thin orchestration
function: it calls the existing public APIs as-is and does not duplicate
any of their analysis/extraction logic.

stdlib only. No DB. No server. No Flask. No external calls.

── Status / stage decisions made by this runner (documented here because
   the brief asked for "simple clear behavior", not a queue/stage engine) ──

After initialize_book_intake_job() the record starts at
status="intake_pending", current_stage="intake".

Step 1 — extraction:
  * status -> "extracting_text", current_stage -> "extracting_text"
    (recorded together with the extraction artifacts, in a single update)
  * If extraction_report.status is "unsupported" or "fail":
      - issues containing "unsupported_format" or
        "unsupported_pdf_native_missing_dependency" are treated as
        unrecoverable without a code/dependency change
        -> status = "failed_unrecoverable"
      - any other extraction failure (decode/parse errors, empty text,
        malformed archive, ...) is treated as potentially fixable by
        supplying a cleaner source file or retrying
        -> status = "failed_recoverable"
    current_stage stays "extracting_text"; the pipeline stops here —
    corpus quality analysis is skipped (there is no usable corpus yet).

Step 2 — corpus quality (only reached if extraction produced text):
  * current_stage -> "corpus_quality_check"
  * corpus_quality_report.status == "fail" -> status = "failed_recoverable"
  * corpus_quality_report.status == "warn" -> status = "corpus_quality_check"
    (flagged for human review before the pipeline continues further)
  * corpus_quality_report.status == "pass" -> status = "completed"
    ("completed" here means *this v0 pipeline's scope* — intake,
    extraction, and quality check — finished cleanly; later pipeline
    stages such as analyzing_structure are out of scope for this runner)
"""

from __future__ import annotations

import os

from book_job_record import artifact_relative_path, load_json
from book_intake_job import initialize_book_intake_job
from text_extraction import save_text_extraction_outputs
from corpus_quality import analyze_corpus_text, save_corpus_quality_report

_RAW_SOURCE_MANIFEST = artifact_relative_path("raw", "source_manifest.json")
_RAW_SOURCE_CORPUS = artifact_relative_path("raw", "source_corpus.txt")
_RAW_EXTRACTION_REPORT = artifact_relative_path("raw", "extraction_report.json")
_ANALYSIS_CORPUS_QUALITY_REPORT = artifact_relative_path("analysis", "corpus_quality_report.json")

# Extraction issues that cannot be fixed by retrying with the same code path
# (they require either a different source file/format or a dependency that
# this runner is explicitly forbidden from installing).
_UNRECOVERABLE_EXTRACTION_ISSUES = frozenset({
    "unsupported_format",
    "unsupported_pdf_native_missing_dependency",
})


def _job_dir_path(job_dir: str, relative_path: str) -> str:
    return os.path.join(job_dir, *relative_path.split("/"))


def _extraction_failure_status(issues: list[str]) -> str:
    """Classify an extraction failure as recoverable or not (see module docstring)."""
    if any(issue in _UNRECOVERABLE_EXTRACTION_ISSUES for issue in issues):
        return "failed_unrecoverable"
    return "failed_recoverable"


def _corpus_quality_status(report_status: str) -> str:
    """Map a corpus_quality_report status to a job status (see module docstring)."""
    if report_status == "fail":
        return "failed_recoverable"
    if report_status == "warn":
        return "corpus_quality_check"
    return "completed"


def run_native_book_intake_pipeline(
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
    Run the native (non-OCR) book intake pipeline for a single source file.

    Orchestrates the existing foundations end to end under an explicit
    base_dir: opens a job (initialize_book_intake_job), extracts native
    text (save_text_extraction_outputs), analyzes corpus quality
    (analyze_corpus_text / save_corpus_quality_report), and updates
    job_record.json's artifacts map and status/current_stage.

    Does not duplicate any extraction or analysis logic — it only calls
    the existing public APIs and persists their results. Does not copy
    the source file and does not read/print its content beyond what the
    underlying modules already do (hashing, native text extraction).

    Raises ValueError for a missing/invalid base_dir or book_id (propagated
    from initialize_book_intake_job), and FileNotFoundError if
    source_file_path does not point to an existing file.

    Returns a dict with: job_id, job_dir, job_record_path,
    source_manifest_path, source_corpus_path, extraction_report_path,
    corpus_quality_report_path, extraction_report, corpus_quality_report,
    final_status, warnings, issues.

    corpus_quality_report_path / corpus_quality_report are None when the
    pipeline stops at the extraction step (no usable corpus was produced).
    """
    init_result = initialize_book_intake_job(
        base_dir,
        source_file_path,
        book_id,
        book_title=book_title,
        created_by=created_by,
        language_hint=language_hint,
        job_id=job_id,
    )

    job_id = init_result["job_id"]
    job_dir = init_result["job_dir"]
    job_record_path = init_result["job_record_path"]
    job_record = init_result["job_record"]

    source_corpus_path = _job_dir_path(job_dir, _RAW_SOURCE_CORPUS)
    extraction_report_path = _job_dir_path(job_dir, _RAW_EXTRACTION_REPORT)
    corpus_quality_report_path = _job_dir_path(job_dir, _ANALYSIS_CORPUS_QUALITY_REPORT)

    source_manifest = load_json(init_result["source_manifest_path"])
    source_id = source_manifest.get("source_id")

    # ── Step 1: native text extraction ──────────────────────────────────────
    extraction_outcome = save_text_extraction_outputs(
        source_file_path,
        source_corpus_path,
        extraction_report_path,
        book_id=book_id,
        source_id=source_id,
    )
    extraction_report = extraction_outcome["extraction_report"]

    job_record.artifacts[_artifact_key(_RAW_SOURCE_CORPUS)] = _RAW_SOURCE_CORPUS
    job_record.artifacts[_artifact_key(_RAW_EXTRACTION_REPORT)] = _RAW_EXTRACTION_REPORT

    if extraction_report["status"] in ("unsupported", "fail"):
        failure_status = _extraction_failure_status(extraction_report["issues"])
        job_record.set_status(failure_status, current_stage="extracting_text")
        job_record.save_json(job_record_path)

        return {
            "job_id": job_id,
            "job_dir": job_dir,
            "job_record_path": job_record_path,
            "source_manifest_path": init_result["source_manifest_path"],
            "source_corpus_path": source_corpus_path,
            "extraction_report_path": extraction_report_path,
            "corpus_quality_report_path": None,
            "extraction_report": extraction_report,
            "corpus_quality_report": None,
            "final_status": failure_status,
            "warnings": list(extraction_report.get("warnings", [])),
            "issues": list(extraction_report.get("issues", [])),
        }

    job_record.set_status("extracting_text", current_stage="extracting_text")
    job_record.save_json(job_record_path)

    # ── Step 2: corpus quality analysis ─────────────────────────────────────
    corpus_quality_report = analyze_corpus_text(
        extraction_outcome["text"],
        source_id=source_id,
        book_id=book_id,
    )
    save_corpus_quality_report(corpus_quality_report, corpus_quality_report_path)

    job_record.artifacts[_artifact_key(_ANALYSIS_CORPUS_QUALITY_REPORT)] = _ANALYSIS_CORPUS_QUALITY_REPORT

    final_status = _corpus_quality_status(corpus_quality_report["status"])
    job_record.set_status(final_status, current_stage="corpus_quality_check")
    job_record.save_json(job_record_path)

    return {
        "job_id": job_id,
        "job_dir": job_dir,
        "job_record_path": job_record_path,
        "source_manifest_path": init_result["source_manifest_path"],
        "source_corpus_path": source_corpus_path,
        "extraction_report_path": extraction_report_path,
        "corpus_quality_report_path": corpus_quality_report_path,
        "extraction_report": extraction_report,
        "corpus_quality_report": corpus_quality_report,
        "final_status": final_status,
        "warnings": list(extraction_report.get("warnings", [])) + list(corpus_quality_report.get("warnings", [])),
        "issues": list(extraction_report.get("issues", [])) + list(corpus_quality_report.get("issues", [])),
    }


def _artifact_key(relative_path: str) -> str:
    """'raw/source_corpus.txt' -> 'source_corpus' — matches the short keys
    book_intake_job.py already uses in the artifacts map (e.g. 'source_manifest')."""
    filename = relative_path.split("/", 1)[1]
    stem, _ext = os.path.splitext(filename)
    return stem
