"""
Minimal self-contained tests for book_job_record.
No external deps. No model/API/OCR calls. Run with: py -3.12 test_book_job_record.py

All directory-creation tests use a temporary directory only — never a
production path.
"""

import os
import shutil
import sys
import tempfile

from book_job_record import (
    ARTIFACT_FILENAMES,
    ARTIFACT_SECTIONS,
    JOB_STATUSES,
    BookJobRecord,
    all_artifact_relative_paths,
    artifact_relative_path,
    create_artifact_directories,
    load_json,
    save_json,
    validate_record_dict,
)

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_results: list[bool] = []


def check(name: str, condition: bool) -> None:
    _results.append(condition)
    print(f"  {'OK' if condition else 'FAIL'} {name}")
    if not condition:
        print("       ^ unexpected result", file=sys.stderr)


def _base_record(**overrides) -> BookJobRecord:
    kwargs = dict(
        job_id="11111111-1111-1111-1111-111111111111",
        book_id="misparei_bayit",
        status="intake_pending",
        current_stage="intake",
        created_by="dev/manual",
    )
    kwargs.update(overrides)
    return BookJobRecord(**kwargs)


# ── Test 1: valid job record roundtrip (to_dict / from_dict / JSON) ─────────
print("\n[1] Job record roundtrip (to_dict / from_dict / save_json / load_json):")
tmp_dir = tempfile.mkdtemp(prefix="book_job_record_test_")
try:
    record = _base_record()
    as_dict = record.to_dict()
    check("to_dict has all required fields", all(k in as_dict for k in (
        "job_id", "book_id", "status", "current_stage", "created_at", "updated_at",
        "created_by", "artifacts", "approvals_required", "approvals_granted",
        "cost_tracker", "error_log", "retry_count",
    )))

    rebuilt = BookJobRecord.from_dict(as_dict)
    check("from_dict roundtrip preserves job_id", rebuilt.job_id == record.job_id)
    check("from_dict roundtrip preserves book_id", rebuilt.book_id == record.book_id)
    check("from_dict roundtrip preserves status", rebuilt.status == record.status)

    json_path = os.path.join(tmp_dir, "job_record.json")
    record.save_json(json_path)
    check("save_json wrote file", os.path.isfile(json_path))

    loaded = BookJobRecord.load_json(json_path)
    check("load_json roundtrip preserves job_id", loaded.job_id == record.job_id)
    check("load_json roundtrip preserves status", loaded.status == record.status)

    raw = load_json(json_path)
    check("plain load_json returns dict", isinstance(raw, dict))
    validate_record_dict(raw)
    check("validate_record_dict accepts valid record", True)
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 2: invalid status rejected ──────────────────────────────────────────
print("\n[2] Invalid status rejected:")
try:
    _base_record(status="not_a_real_status")
    check("constructor raises ValueError on invalid status", False)
except ValueError:
    check("constructor raises ValueError on invalid status", True)

record = _base_record()
try:
    record.set_status("also_not_real")
    check("set_status raises ValueError on invalid status", False)
except ValueError:
    check("set_status raises ValueError on invalid status", True)
check("set_status validation does not mutate status", record.status == "intake_pending")

try:
    validate_record_dict({**_base_record().to_dict(), "status": "bogus"})
    check("validate_record_dict raises ValueError on invalid status", False)
except ValueError:
    check("validate_record_dict raises ValueError on invalid status", True)

try:
    validate_record_dict({"job_id": "x"})
    check("validate_record_dict raises ValueError on missing fields", False)
except ValueError as exc:
    check("validate_record_dict raises ValueError on missing fields", "missing required fields" in str(exc))

check("all known statuses accepted by constructor", all(
    _base_record(status=s).status == s for s in JOB_STATUSES
))


# ── Test 3: artifact path map contains expected sections/files ──────────────
print("\n[3] Artifact path map — expected sections/files:")
expected_sections = ["raw", "analysis", "audit", "output", "runtime"]
check("ARTIFACT_SECTIONS matches expected list", ARTIFACT_SECTIONS == expected_sections)

expected_paths = {
    "raw/source_manifest.json",
    "raw/source_corpus.txt",
    "raw/extraction_report.json",
    "analysis/corpus_quality_report.json",
    "analysis/book_structure.json",
    "analysis/formula_candidates.json",
    "analysis/interpretation_candidates.json",
    "audit/quality_audit_report.json",
    "audit/human_review_queue.json",
    "audit/approved_extraction.json",
    "output/definition_draft.json",
    "output/definition_diff.json",
    "output/learning_profile_draft.json",
    "output/learning_profile_diff.json",
    "runtime/runtime_manifest.json",
    "runtime/smoke_test_report.json",
    "runtime/preflight_report.json",
}
all_paths = set(all_artifact_relative_paths())
check("all expected artifact paths present", expected_paths == all_paths)
check("artifact_relative_path builds known path", artifact_relative_path("raw", "source_manifest.json") == "raw/source_manifest.json")

try:
    artifact_relative_path("not_a_section", "x.json")
    check("artifact_relative_path rejects unknown section", False)
except ValueError:
    check("artifact_relative_path rejects unknown section", True)

try:
    artifact_relative_path("raw", "not_a_known_file.json")
    check("artifact_relative_path rejects unknown filename", False)
except ValueError:
    check("artifact_relative_path rejects unknown filename", True)

check("every section has a non-empty filename list", all(
    len(ARTIFACT_FILENAMES[s]) > 0 for s in ARTIFACT_SECTIONS
))


# ── Test 4: artifact directories created only in temp dir ───────────────────
print("\n[4] Artifact directories created only in a temp dir:")
tmp_base = tempfile.mkdtemp(prefix="book_job_record_artifacts_")
try:
    job_dir = os.path.join(tmp_base, "book_jobs", "misparei_bayit", "job-0001")
    created = create_artifact_directories(job_dir)
    check("returned one dir per section", len(created) == len(ARTIFACT_SECTIONS))
    check("all created dirs exist on disk", all(os.path.isdir(d) for d in created))
    check("all created dirs are under the temp base_dir", all(
        os.path.commonpath([os.path.abspath(tmp_base), os.path.abspath(d)]) == os.path.abspath(tmp_base)
        for d in created
    ))
    check("section names match canonical list", sorted(os.path.basename(d) for d in created) == sorted(ARTIFACT_SECTIONS))

    # idempotent — calling again must not fail or duplicate
    created_again = create_artifact_directories(job_dir)
    check("re-running create_artifact_directories is idempotent", created_again == created)
finally:
    shutil.rmtree(tmp_base, ignore_errors=True)


# ── Test 5: no production path required ─────────────────────────────────────
print("\n[5] No production path required / base_dir validation:")
try:
    create_artifact_directories("")
    check("create_artifact_directories rejects empty base_dir", False)
except ValueError:
    check("create_artifact_directories rejects empty base_dir", True)

try:
    create_artifact_directories(None)  # type: ignore[arg-type]
    check("create_artifact_directories rejects None base_dir", False)
except ValueError:
    check("create_artifact_directories rejects None base_dir", True)


# ── Test 6: updated_at changes when status changes ──────────────────────────
print("\n[6] updated_at changes when status changes:")
record = _base_record()
original_created_at = record.created_at
# Use a sentinel so the assertion does not depend on wall-clock resolution
# (two calls to utc_now_iso() within the same second would otherwise be equal).
record.updated_at = "SENTINEL_BEFORE_UPDATE"
record.set_status("extracting_text", current_stage="text_extraction")
check("status updated", record.status == "extracting_text")
check("current_stage updated", record.current_stage == "text_extraction")
check("created_at unchanged on status change", record.created_at == original_created_at)
check("updated_at reassigned away from sentinel on status change", record.updated_at != "SENTINEL_BEFORE_UPDATE")
check("updated_at is a non-empty ISO8601-looking string", isinstance(record.updated_at, str) and record.updated_at.endswith("Z"))


# ── Summary ──────────────────────────────────────────────────────────────────
total = len(_results)
passed = sum(_results)
failed = total - passed
print(f"\n{'='*50}")
print(f"תוצאות: {passed}/{total} בדיקות עברו" + (f" | {failed} נכשלו" if failed else ""))
sys.exit(0 if failed == 0 else 1)
