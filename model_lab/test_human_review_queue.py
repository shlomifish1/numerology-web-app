"""
Minimal self-contained tests for human_review_queue.
No external deps. No model/API/OCR calls. Run with: py -3.12 test_human_review_queue.py

All file-writing tests use a temporary directory only — never a production
path. Queues/items are tiny throwaway in-memory structures.
"""

import os
import shutil
import sys
import tempfile

from human_review_queue import (
    ALLOWED_ITEM_TYPES,
    ALLOWED_PRIORITIES,
    ALLOWED_REVIEW_STATUSES,
    HumanReviewItem,
    HumanReviewQueue,
    approve_item,
    create_human_review_queue,
    create_review_item,
    edit_and_approve_item,
    load_human_review_queue,
    put_item_on_hold,
    queue_from_dict,
    queue_to_dict,
    reject_item,
    save_human_review_queue,
)

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_results: list[bool] = []


def check(name: str, condition: bool) -> None:
    _results.append(bool(condition))
    print(f"  {'OK' if condition else 'FAIL'} {name}")
    if not condition:
        print("       ^ unexpected result", file=sys.stderr)


def _formula_candidate(value: str = "חוכמה = 8") -> dict:
    return {"calc_key": "wisdom_number", "formula": value, "source_quote": "עמוד 42, פרק ג'"}


# ── Test 1: create_review_item creates a pending item with valid fields ─────
print("\n[1] create_review_item creates a pending item with valid fields:")
item = create_review_item("formula", _formula_candidate(), priority="high", audit_notes=None)
check("item is a HumanReviewItem", isinstance(item, HumanReviewItem))
check("item_id is a non-empty string", isinstance(item.item_id, str) and bool(item.item_id))
check("item_type is 'formula'", item.item_type == "formula")
check("priority is 'high'", item.priority == "high")
check("status starts as 'pending'", item.status == "pending")
check("data matches the candidate dict", item.data == _formula_candidate())
check("audit_notes starts empty", item.audit_notes == [])
check("reviewer fields start unset", item.reviewer_id is None and item.reviewed_at is None and item.reviewer_note is None)
check("edited_value starts unset", item.edited_value is None)
check("created_at looks like an ISO8601 UTC timestamp", isinstance(item.created_at, str) and item.created_at.endswith("Z"))
check("default priority is 'medium'", create_review_item("general_note", {"text": "הערה"}).priority == "medium")
check("explicit item_id is honored", create_review_item("formula", _formula_candidate(), item_id="fixed-id-1").item_id == "fixed-id-1")


# ── Test 2: invalid item_type is rejected ───────────────────────────────────
print("\n[2] Invalid item_type is rejected:")
check("'formula'/'interpretation'/'general_note' are the only allowed item types", ALLOWED_ITEM_TYPES == {"formula", "interpretation", "general_note"})
try:
    create_review_item("not_a_real_type", {"x": 1})
    check("create_review_item rejects an invalid item_type", False)
except ValueError:
    check("create_review_item rejects an invalid item_type", True)
try:
    HumanReviewItem(item_id="x", item_type="bogus")
    check("HumanReviewItem itself rejects an invalid item_type", False)
except ValueError:
    check("HumanReviewItem itself rejects an invalid item_type", True)


# ── Test 3: invalid priority is rejected ────────────────────────────────────
print("\n[3] Invalid priority is rejected:")
check("'high'/'medium'/'low' are the only allowed priorities", ALLOWED_PRIORITIES == {"high", "medium", "low"})
try:
    create_review_item("formula", _formula_candidate(), priority="urgent")
    check("create_review_item rejects an invalid priority", False)
except ValueError:
    check("create_review_item rejects an invalid priority", True)
try:
    HumanReviewItem(item_id="x", item_type="formula", priority="urgent")
    check("HumanReviewItem itself rejects an invalid priority", False)
except ValueError:
    check("HumanReviewItem itself rejects an invalid priority", True)


# ── Test 4: create_human_review_queue counts pending items correctly ────────
print("\n[4] create_human_review_queue counts pending items correctly:")
items = [
    create_review_item("formula", _formula_candidate("נוסחה א'")),
    create_review_item("formula", _formula_candidate("נוסחה ב'")),
    create_review_item("interpretation", {"text": "פירוש לדוגמה"}, priority="low"),
]
queue = create_human_review_queue("misparei_bayit", "job-123", items=items)
check("queue is a HumanReviewQueue", isinstance(queue, HumanReviewQueue))
check("book_id/job_id stored", queue.book_id == "misparei_bayit" and queue.job_id == "job-123")
check("total_items counts all items", queue.total_items == 3)
check("pending counts all freshly-created items", queue.pending == 3)
check("approved/rejected start at zero", queue.approved == 0 and queue.rejected == 0)
check("queue_created looks like an ISO8601 UTC timestamp", queue.queue_created.endswith("Z"))
check("audit_log starts empty", queue.audit_log == [])

empty_queue = create_human_review_queue("misparei_bayit", "job-456")
check("queue with no items starts completely empty", empty_queue.total_items == 0 and empty_queue.pending == 0)
for bad_book_id, bad_job_id in (("", "job-1"), ("book-1", ""), (None, "job-1")):
    try:
        create_human_review_queue(bad_book_id, bad_job_id)  # type: ignore[arg-type]
        check(f"rejects empty/None book_id/job_id ({bad_book_id!r}, {bad_job_id!r})", False)
    except ValueError:
        check(f"rejects empty/None book_id/job_id ({bad_book_id!r}, {bad_job_id!r})", True)


# ── Test 5: approve_item updates status, reviewer, reviewed_at, audit_log ───
print("\n[5] approve_item updates status/reviewer/reviewed_at and appends an audit_log entry:")
queue = create_human_review_queue("misparei_bayit", "job-1", items=[create_review_item("formula", _formula_candidate(), item_id="item-1")])
before_log_len = len(queue.audit_log)
approved = approve_item(queue, "item-1", reviewer_id="shlomi", note="נראה תקין, מאושר")
check("returns the updated item", approved is queue.items[0])
check("status becomes 'approved'", approved.status == "approved")
check("reviewer_id recorded", approved.reviewer_id == "shlomi")
check("reviewed_at recorded as a timestamp", isinstance(approved.reviewed_at, str) and approved.reviewed_at.endswith("Z"))
check("reviewer_note recorded", approved.reviewer_note == "נראה תקין, מאושר")
check("queue.approved counter updated", queue.approved == 1 and queue.pending == 0)
check("exactly one audit_log entry was appended", len(queue.audit_log) == before_log_len + 1)
last_entry = queue.audit_log[-1]
check("audit_log entry has who/when/decision/note", all(k in last_entry for k in ("reviewer_id", "timestamp", "decision", "note")))
check("audit_log entry decision is 'approved'", last_entry["decision"] == "approved")
check("audit_log entry was copied into the item's own audit_notes", last_entry in approved.audit_notes)
check("approve_item without a note leaves reviewer_note as None", approve_item(
    create_human_review_queue("b", "j", items=[create_review_item("formula", _formula_candidate(), item_id="x")]),
    "x", reviewer_id="shlomi",
).reviewer_note is None)


# ── Test 6: reject_item requires a note and updates counts ──────────────────
print("\n[6] reject_item requires a note and updates counts:")
queue = create_human_review_queue("misparei_bayit", "job-1", items=[create_review_item("formula", _formula_candidate(), item_id="item-1")])
for bad_note in ("", None):
    try:
        reject_item(queue, "item-1", reviewer_id="shlomi", note=bad_note)  # type: ignore[arg-type]
        check(f"rejects an empty/None note ({bad_note!r})", False)
    except ValueError:
        check(f"rejects an empty/None note ({bad_note!r})", True)
check("item is still pending after the rejected attempts", queue.items[0].status == "pending")

rejected = reject_item(queue, "item-1", reviewer_id="shlomi", note="אין מקור/ציטוט תומך")
check("status becomes 'rejected'", rejected.status == "rejected")
check("reviewer_note stores the rejection reason", rejected.reviewer_note == "אין מקור/ציטוט תומך")
check("queue.rejected counter updated", queue.rejected == 1 and queue.pending == 0)
check("audit_log records the rejection with its note", queue.audit_log[-1]["decision"] == "rejected" and queue.audit_log[-1]["note"] == "אין מקור/ציטוט תומך")


# ── Test 7: edit_and_approve preserves edited_value and logs the audit entry ─
print("\n[7] edit_and_approve_item preserves original data and stores edited_value separately:")
original_data = _formula_candidate("נוסחה מקורית")
queue = create_human_review_queue("misparei_bayit", "job-1", items=[create_review_item("formula", original_data, item_id="item-1")])
edited = edit_and_approve_item(queue, "item-1", reviewer_id="shlomi", edited_value={"formula": "נוסחה מתוקנת"}, note="תוקן ניסוח")
check("status becomes 'approved_with_edit'", edited.status == "approved_with_edit")
check("original data is left completely untouched", edited.data == original_data)
check("edited_value is stored separately from data", edited.edited_value == {"formula": "נוסחה מתוקנת"})
check("data and edited_value remain distinct objects", edited.data is not edited.edited_value)
check("queue.approved counts approved_with_edit items too", queue.approved == 1 and queue.pending == 0)
check("audit_log records the edit-and-approve decision", queue.audit_log[-1]["decision"] == "approved_with_edit")
check("audit entry was copied into the item's audit_notes", queue.audit_log[-1] in edited.audit_notes)


# ── Test 8: on_hold works and logs the decision ─────────────────────────────
print("\n[8] put_item_on_hold updates status and logs the decision:")
queue = create_human_review_queue("misparei_bayit", "job-1", items=[create_review_item("interpretation", {"text": "פירוש"}, item_id="item-1")])
held = put_item_on_hold(queue, "item-1", reviewer_id="shlomi", note="צריך להתייעץ עם מקור נוסף")
check("status becomes 'on_hold'", held.status == "on_hold")
check("reviewer_note stores the reason", held.reviewer_note == "צריך להתייעץ עם מקור נוסף")
check("on_hold items still count as pending (decision not yet final)", queue.pending == 1 and queue.approved == 0 and queue.rejected == 0)
check("audit_log records the on_hold decision", queue.audit_log[-1]["decision"] == "on_hold")


# ── Test 9: save/load queue roundtrip ───────────────────────────────────────
print("\n[9] save_human_review_queue / load_human_review_queue roundtrip:")
tmp_dir = tempfile.mkdtemp(prefix="human_review_queue_roundtrip_test_")
try:
    queue = create_human_review_queue("misparei_bayit", "job-1", items=[
        create_review_item("formula", _formula_candidate(), item_id="item-1"),
        create_review_item("interpretation", {"text": "פירוש"}, item_id="item-2", priority="low"),
    ])
    approve_item(queue, "item-1", reviewer_id="shlomi", note="מאושר")
    reject_item(queue, "item-2", reviewer_id="shlomi", note="לא רלוונטי")

    queue_path = os.path.join(tmp_dir, "audit", "human_review_queue.json")
    save_human_review_queue(queue, queue_path)
    check("save_human_review_queue wrote the file", os.path.isfile(queue_path))
    check("save_human_review_queue created the parent dir", os.path.isdir(os.path.dirname(queue_path)))

    loaded = load_human_review_queue(queue_path)
    check("loaded queue is a HumanReviewQueue", isinstance(loaded, HumanReviewQueue))
    check("loaded queue_to_dict equals the original queue_to_dict", queue_to_dict(loaded) == queue_to_dict(queue))
    check("loaded items reconstruct as HumanReviewItem instances", all(isinstance(i, HumanReviewItem) for i in loaded.items))
    check("loaded counters match (re-derived, not just copied)", loaded.approved == 1 and loaded.rejected == 1 and loaded.pending == 0)
    check("loaded audit_log matches the original", loaded.audit_log == queue.audit_log)

    roundtrip_dict = queue_to_dict(queue)
    rebuilt = queue_from_dict(roundtrip_dict)
    check("queue_from_dict(queue_to_dict(queue)) round-trips cleanly", queue_to_dict(rebuilt) == roundtrip_dict)

    try:
        save_human_review_queue(queue, "")
        check("save_human_review_queue rejects an empty path", False)
    except ValueError:
        check("save_human_review_queue rejects an empty path", True)
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 10: cannot transition a missing item_id ────────────────────────────
print("\n[10] Cannot transition a missing item_id:")
queue = create_human_review_queue("misparei_bayit", "job-1", items=[create_review_item("formula", _formula_candidate(), item_id="real-item")])
for fn, args in (
    (approve_item, ("ghost-item", "shlomi")),
    (reject_item, ("ghost-item", "shlomi", "סיבה")),
    (edit_and_approve_item, ("ghost-item", "shlomi", {"x": 1})),
    (put_item_on_hold, ("ghost-item", "shlomi")),
):
    try:
        fn(queue, *args)
        check(f"{fn.__name__} raises KeyError for a missing item_id", False)
    except KeyError:
        check(f"{fn.__name__} raises KeyError for a missing item_id", True)
check("the real item is untouched by the failed lookups", queue.items[0].status == "pending")
check("no spurious audit_log entries were appended", queue.audit_log == [])


# ── Test 11: no production path is required or hardcoded ────────────────────
print("\n[11] No production path is required or hardcoded:")
import ast
import inspect

import human_review_queue as hrq
_source = inspect.getsource(hrq)
_tree = ast.parse(_source)

# The module's own safety-statement docstring deliberately *names* the things
# it is NOT (OCR, runtime_promoter, definition.json, ...) — scanning raw
# source text for those words would false-positive on its own disclaimer
# (the same false-positive class hit in test_book_intake_pipeline.py).
# So: drop the module docstring's lines (located via the AST node's own line
# span, not naive string matching) and scan only the remaining code.
_source_lines = _source.splitlines()
_first_stmt = _tree.body[0] if _tree.body else None
_is_docstring = (
    isinstance(_first_stmt, ast.Expr)
    and isinstance(_first_stmt.value, ast.Constant)
    and isinstance(_first_stmt.value.value, str)
)
if _is_docstring:
    _doc_start, _doc_end = _first_stmt.lineno, _first_stmt.end_lineno
    _code_lines = _source_lines[:_doc_start - 1] + _source_lines[_doc_end:]
else:
    _code_lines = _source_lines
_code = "\n".join(_code_lines)
check("module docstring was actually found and excluded from the scan", _is_docstring and "NOT OCR" in _source and "NOT OCR" not in _code)

check("module code (excl. its own docstring) has no hardcoded book_jobs path literal", not any(
    token in _code for token in ("\\book_jobs\\", "/book_jobs/", '"book_jobs"', "'book_jobs'")
))
check("module code has no 'web_server' reference", "web_server" not in _code)
check("module code has no drive-letter production path literal", not any(
    token in _code for token in ("C:\\\\", "D:\\\\", "/var/", "/srv/")
))
check("module code has no definition.json writer reference", "definition.json" not in _code)

_imported_modules = []
for node in ast.walk(_tree):
    if isinstance(node, ast.Import):
        _imported_modules.extend(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom):
        _imported_modules.append(node.module)
_allowed_modules = {"__future__", "uuid", "dataclasses", "book_job_record"}
check("module only imports stdlib + book_job_record", bool(_imported_modules) and all(name in _allowed_modules for name in _imported_modules))

_forbidden_code_patterns = (
    "import requests", "import openai", "import anthropic", "import flask", "import sqlite3",
    "tesseract", "pytesseract", "ocr_engine", ".ocr(", "openai.", "anthropic.",
    "requests.post", "requests.get", "qwen", "ollama", "localhost:11434", "runtime_promoter",
)
check("module code has no OCR/model/API/server/runtime_promoter patterns", not any(pat in _code for pat in _forbidden_code_patterns))

tmp_dir = tempfile.mkdtemp(prefix="human_review_queue_no_prod_path_test_")
try:
    queue = create_human_review_queue("misparei_bayit", "job-1", items=[create_review_item("formula", _formula_candidate())])
    queue_path = os.path.join(tmp_dir, "human_review_queue.json")
    save_human_review_queue(queue, queue_path)
    check("queue written only under the explicit temp path given", os.path.isfile(queue_path))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Summary ──────────────────────────────────────────────────────────────────
total = len(_results)
passed = sum(_results)
failed = total - passed
print(f"\n{'='*50}")
print(f"תוצאות: {passed}/{total} בדיקות עברו" + (f" | {failed} נכשלו" if failed else ""))
sys.exit(0 if failed == 0 else 1)
