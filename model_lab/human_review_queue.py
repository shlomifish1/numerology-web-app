"""
Book Lab — Human Review Queue (artifact foundation, v0)

Local-only helpers for the human_review_queue.json artifact described in
_docs/book_lab/BOOK_LAB_MULTI_AGENT_ARCHITECTURE.md (Human Review
Coordinator §"מחכה לאחת מ: approve / reject / edit_and_approve / ...",
"שומר audit trail של כל החלטה: who, when, decision, note").

This is NOT a UI, NOT a web server, NOT a DB, NOT an agent runner, NOT a
queue-manager daemon, NOT a model/API call, NOT OCR, NOT a definition
writer, and NOT a runtime_promoter. It only defines:
  - allowed item types / priorities / review statuses
  - a HumanReviewItem dataclass (one candidate awaiting human review)
  - a HumanReviewQueue dataclass (a book job's review queue + audit trail)
  - pure approve/reject/edit_and_approve/on_hold transition helpers that
    mutate an in-memory queue and append an audit_log entry
  - to_dict/from_dict + JSON load/save helpers (explicit path only)

Nothing here ever auto-approves an item, writes to definition.json, or
infers/defaults to a production or runtime path — every transition
requires an explicit reviewer_id, and every save requires an explicit path.

stdlib only. No DB. No server. No Flask. No external calls.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from book_job_record import load_json, save_json, utc_now_iso

ALLOWED_ITEM_TYPES = {"formula", "interpretation", "general_note"}
ALLOWED_PRIORITIES = {"high", "medium", "low"}

# "pending"/"on_hold" are both *not yet final* (on_hold is a temporary
# deferral while the reviewer consults another source); "approved" and
# "approved_with_edit" are both *approval* decisions (the only difference
# is whether the reviewer edited the value before approving). This mapping
# is what the pending/approved/rejected counters below use — see
# HumanReviewQueue's derived properties.
ALLOWED_REVIEW_STATUSES = {"pending", "approved", "rejected", "approved_with_edit", "on_hold"}

_PENDING_LIKE_STATUSES = frozenset({"pending", "on_hold"})
_APPROVED_LIKE_STATUSES = frozenset({"approved", "approved_with_edit"})


# ── HumanReviewItem ──────────────────────────────────────────────────────────

@dataclass
class HumanReviewItem:
    item_id: str
    item_type: str
    priority: str = "medium"
    status: str = "pending"
    data: dict = field(default_factory=dict)
    audit_notes: list = field(default_factory=list)
    reviewer_id: str | None = None
    reviewed_at: str | None = None
    reviewer_note: str | None = None
    edited_value: object | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if self.item_type not in ALLOWED_ITEM_TYPES:
            raise ValueError(f"invalid item_type: '{self.item_type}'")
        if self.priority not in ALLOWED_PRIORITIES:
            raise ValueError(f"invalid priority: '{self.priority}'")
        if self.status not in ALLOWED_REVIEW_STATUSES:
            raise ValueError(f"invalid status: '{self.status}'")

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "priority": self.priority,
            "status": self.status,
            "data": self.data,
            "audit_notes": list(self.audit_notes),
            "reviewer_id": self.reviewer_id,
            "reviewed_at": self.reviewed_at,
            "reviewer_note": self.reviewer_note,
            "edited_value": self.edited_value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HumanReviewItem":
        if not isinstance(data, dict):
            raise ValueError("review item data must be a dict")
        return cls(
            item_id=data["item_id"],
            item_type=data["item_type"],
            priority=data.get("priority", "medium"),
            status=data.get("status", "pending"),
            data=data.get("data", {}),
            audit_notes=list(data.get("audit_notes", [])),
            reviewer_id=data.get("reviewer_id"),
            reviewed_at=data.get("reviewed_at"),
            reviewer_note=data.get("reviewer_note"),
            edited_value=data.get("edited_value"),
            created_at=data.get("created_at", utc_now_iso()),
        )


def create_review_item(
    item_type: str,
    data: dict,
    *,
    priority: str = "medium",
    audit_notes: list | None = None,
    item_id: str | None = None,
) -> HumanReviewItem:
    """
    Build a new HumanReviewItem in 'pending' status from a candidate-like dict.

    Pure constructor — never auto-approves, never reaches into a queue or
    the filesystem. Raises ValueError for an unknown item_type or priority.
    """
    if not isinstance(data, dict):
        raise ValueError("data must be a dict (a candidate-like record)")
    return HumanReviewItem(
        item_id=item_id or str(uuid.uuid4()),
        item_type=item_type,
        priority=priority,
        status="pending",
        data=dict(data),
        audit_notes=list(audit_notes) if audit_notes else [],
    )


# ── HumanReviewQueue ─────────────────────────────────────────────────────────

@dataclass
class HumanReviewQueue:
    book_id: str
    job_id: str
    queue_created: str = field(default_factory=utc_now_iso)
    items: list = field(default_factory=list)
    audit_log: list = field(default_factory=list)

    # total_items / pending / approved / rejected are intentionally *derived*
    # from `items` rather than stored counters — this guarantees they can
    # never drift out of sync with the actual item statuses across
    # transitions (no separate "bump the counter" step to forget).
    @property
    def total_items(self) -> int:
        return len(self.items)

    @property
    def pending(self) -> int:
        return sum(1 for item in self.items if item.status in _PENDING_LIKE_STATUSES)

    @property
    def approved(self) -> int:
        return sum(1 for item in self.items if item.status in _APPROVED_LIKE_STATUSES)

    @property
    def rejected(self) -> int:
        return sum(1 for item in self.items if item.status == "rejected")


def create_human_review_queue(book_id: str, job_id: str, *, items: list | None = None) -> HumanReviewQueue:
    """Build a new, empty-by-default HumanReviewQueue for a book job."""
    if not book_id or not isinstance(book_id, str):
        raise ValueError("book_id must be a non-empty string")
    if not job_id or not isinstance(job_id, str):
        raise ValueError("job_id must be a non-empty string")
    return HumanReviewQueue(book_id=book_id, job_id=job_id, items=list(items) if items else [])


def _get_item(queue: HumanReviewQueue, item_id: str) -> HumanReviewItem:
    for item in queue.items:
        if item.item_id == item_id:
            return item
    raise KeyError(f"no review item with item_id '{item_id}' in this queue")


def _apply_decision(queue: HumanReviewQueue, item: HumanReviewItem, *, decision: str,
                    reviewer_id: str, note: str | None) -> HumanReviewItem:
    """Shared bookkeeping for every transition: stamps the item and appends
    one audit_log entry to the queue (and a copy to the item's own
    audit_notes) recording who decided what, when, and why."""
    if not reviewer_id or not isinstance(reviewer_id, str):
        raise ValueError("reviewer_id must be a non-empty string")

    timestamp = utc_now_iso()
    item.status = decision
    item.reviewer_id = reviewer_id
    item.reviewed_at = timestamp
    item.reviewer_note = note

    audit_entry = {
        "item_id": item.item_id,
        "decision": decision,
        "reviewer_id": reviewer_id,
        "note": note,
        "timestamp": timestamp,
    }
    queue.audit_log.append(audit_entry)
    item.audit_notes.append(audit_entry)
    return item


def approve_item(queue: HumanReviewQueue, item_id: str, reviewer_id: str, note: str | None = None) -> HumanReviewItem:
    """Approve an item as-is (no edits). Raises KeyError if item_id is not in the queue."""
    item = _get_item(queue, item_id)
    return _apply_decision(queue, item, decision="approved", reviewer_id=reviewer_id, note=note)


def reject_item(queue: HumanReviewQueue, item_id: str, reviewer_id: str, note: str) -> HumanReviewItem:
    """
    Reject an item. A non-empty `note` explaining the rejection is required
    (mirrors the architecture's "לדחות ללא הסבר" prohibition — never reject
    without an explanation). Raises KeyError if item_id is not in the queue.
    """
    if not note or not isinstance(note, str):
        raise ValueError("reject_item requires a non-empty note explaining the rejection")
    item = _get_item(queue, item_id)
    return _apply_decision(queue, item, decision="rejected", reviewer_id=reviewer_id, note=note)


def edit_and_approve_item(queue: HumanReviewQueue, item_id: str, reviewer_id: str,
                          edited_value, note: str | None = None) -> HumanReviewItem:
    """
    Approve an item with a human-edited value. The item's original `data`
    is left completely untouched — `edited_value` is stored separately so
    the original candidate and the human correction both remain auditable.
    Raises KeyError if item_id is not in the queue.
    """
    item = _get_item(queue, item_id)
    item = _apply_decision(queue, item, decision="approved_with_edit", reviewer_id=reviewer_id, note=note)
    item.edited_value = edited_value
    return item


def put_item_on_hold(queue: HumanReviewQueue, item_id: str, reviewer_id: str, note: str | None = None) -> HumanReviewItem:
    """Defer a decision on an item (e.g. the reviewer wants to consult another source).
    Raises KeyError if item_id is not in the queue."""
    item = _get_item(queue, item_id)
    return _apply_decision(queue, item, decision="on_hold", reviewer_id=reviewer_id, note=note)


# ── Serialization ────────────────────────────────────────────────────────────

def queue_to_dict(queue: HumanReviewQueue) -> dict:
    """Build the human_review_queue.json dict, including the derived counters."""
    return {
        "book_id": queue.book_id,
        "job_id": queue.job_id,
        "queue_created": queue.queue_created,
        "total_items": queue.total_items,
        "pending": queue.pending,
        "approved": queue.approved,
        "rejected": queue.rejected,
        "items": [item.to_dict() for item in queue.items],
        "audit_log": list(queue.audit_log),
    }


def queue_from_dict(data: dict) -> HumanReviewQueue:
    """Reconstruct a HumanReviewQueue from a human_review_queue.json dict.

    The total_items/pending/approved/rejected counters in `data` (if present)
    are ignored on load — they are always re-derived from the loaded items,
    so a hand-edited or stale count in the JSON can never desynchronize the
    in-memory queue."""
    if not isinstance(data, dict):
        raise ValueError("human review queue data must be a dict")
    missing = [key for key in ("book_id", "job_id", "items") if key not in data]
    if missing:
        raise ValueError(f"human review queue data missing required fields: {missing}")

    items = [HumanReviewItem.from_dict(item_data) for item_data in data["items"]]
    return HumanReviewQueue(
        book_id=data["book_id"],
        job_id=data["job_id"],
        queue_created=data.get("queue_created", utc_now_iso()),
        items=items,
        audit_log=list(data.get("audit_log", [])),
    )


def save_human_review_queue(queue: HumanReviewQueue, path: str) -> None:
    """Write the queue as pretty-printed UTF-8 JSON to an explicit path only —
    never defaults to or infers any production, job-queue, or runtime path."""
    if not path or not isinstance(path, str):
        raise ValueError("path must be a non-empty string provided by the caller")
    save_json(path, queue_to_dict(queue))


def load_human_review_queue(path: str) -> HumanReviewQueue:
    """Read and parse a human_review_queue.json file from an explicit path."""
    return queue_from_dict(load_json(path))
