"""
Book Lab — Job Record + Artifact Directory Structure (foundation, v0)

Local-only helper for the future Book Learning Agents pipeline described in
_docs/book_lab/BOOK_LAB_MULTI_AGENT_ARCHITECTURE.md.

This is NOT a queue manager, NOT an agent runner, and performs NO OCR,
model, or API calls. It only defines:
  - stable job statuses / stage constants
  - canonical artifact section + filename conventions
  - a BookJobRecord dataclass with to_dict/from_dict + JSON load/save
  - a safe helper to create the artifact directory tree under an
    explicit base_dir (never touches production paths by default)

stdlib only. No DB. No server. No Flask. No external calls.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

# ── Job statuses (per BOOK_LAB_MULTI_AGENT_ARCHITECTURE.md §7 "Statuses") ───

JOB_STATUSES: list[str] = [
    "intake_pending",
    "extracting_text",
    "corpus_quality_check",
    "analyzing_structure",
    "extracting_formulas",
    "extracting_interpretations",
    "quality_audit",
    "human_review",
    "writing_definition",
    "writing_learning_profile",
    "runtime_promotion",
    "smoke_testing",
    "preflight_check",
    "deploy_ready",
    "completed",
    "failed_recoverable",
    "failed_unrecoverable",
    "cancelled",
]

VALID_JOB_STATUSES = set(JOB_STATUSES)


# ── Canonical artifact sections + expected filenames (per architecture §3) ──

ARTIFACT_SECTIONS: list[str] = ["raw", "analysis", "audit", "output", "runtime"]

ARTIFACT_FILENAMES: dict[str, list[str]] = {
    "raw": [
        "source_manifest.json",
        "source_corpus.txt",
        "extraction_report.json",
    ],
    "analysis": [
        "corpus_quality_report.json",
        "book_structure.json",
        "formula_candidates.json",
        "interpretation_candidates.json",
    ],
    "audit": [
        "quality_audit_report.json",
        "human_review_queue.json",
        "approved_extraction.json",
    ],
    "output": [
        "definition_draft.json",
        "definition_diff.json",
        "learning_profile_draft.json",
        "learning_profile_diff.json",
    ],
    "runtime": [
        "runtime_manifest.json",
        "smoke_test_report.json",
        "preflight_report.json",
    ],
}

REQUIRED_RECORD_FIELDS: list[str] = [
    "job_id",
    "book_id",
    "status",
    "current_stage",
    "created_at",
    "updated_at",
    "created_by",
    "artifacts",
    "approvals_required",
    "approvals_granted",
    "cost_tracker",
    "error_log",
    "retry_count",
]


def utc_now_iso() -> str:
    """ISO8601 UTC timestamp with 'Z' suffix, e.g. 2026-06-06T12:00:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Artifact relative-path helpers ──────────────────────────────────────────

def artifact_relative_path(section: str, filename: str) -> str:
    """Build the canonical relative path 'section/filename', validating both."""
    if section not in ARTIFACT_SECTIONS:
        raise ValueError(f"unknown artifact section: '{section}'")
    if filename not in ARTIFACT_FILENAMES[section]:
        raise ValueError(f"unknown artifact filename '{filename}' for section '{section}'")
    return f"{section}/{filename}"


def all_artifact_relative_paths() -> list[str]:
    """Every canonical artifact path, e.g. ['raw/source_manifest.json', ...]."""
    return [
        f"{section}/{filename}"
        for section in ARTIFACT_SECTIONS
        for filename in ARTIFACT_FILENAMES[section]
    ]


def create_artifact_directories(base_dir: str) -> list[str]:
    """
    Create the canonical artifact section directories under an explicit
    base_dir provided by the caller (e.g. a job's working directory).

    Never writes outside base_dir — does not resolve, default, or fall
    back to any production path. Caller is fully responsible for base_dir.

    Returns the list of created (or already-existing) section directory paths.
    """
    if not base_dir or not isinstance(base_dir, str):
        raise ValueError("base_dir must be a non-empty string provided by the caller")

    created: list[str] = []
    for section in ARTIFACT_SECTIONS:
        section_dir = os.path.join(base_dir, section)
        os.makedirs(section_dir, exist_ok=True)
        created.append(section_dir)
    return created


# ── BookJobRecord ────────────────────────────────────────────────────────────

@dataclass
class BookJobRecord:
    job_id: str
    book_id: str
    status: str = "intake_pending"
    current_stage: str = "intake"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    created_by: str = "unknown"
    artifacts: dict = field(default_factory=dict)
    approvals_required: list = field(default_factory=list)
    approvals_granted: list = field(default_factory=list)
    cost_tracker: dict = field(
        default_factory=lambda: {
            "local_model_calls": 0,
            "low_cost_api_calls": 0,
            "strong_review_calls": 0,
            "estimated_cost": 0.0,
        }
    )
    error_log: list = field(default_factory=list)
    retry_count: int = 0

    def __post_init__(self) -> None:
        if self.status not in VALID_JOB_STATUSES:
            raise ValueError(f"invalid status: '{self.status}'")

    def set_status(self, new_status: str, *, current_stage: str | None = None) -> None:
        """Update status (and optionally stage), bumping updated_at. Validates status."""
        if new_status not in VALID_JOB_STATUSES:
            raise ValueError(f"invalid status: '{new_status}'")
        self.status = new_status
        if current_stage is not None:
            self.current_stage = current_stage
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BookJobRecord":
        validate_record_dict(data)
        kwargs = {key: data[key] for key in REQUIRED_RECORD_FIELDS}
        return cls(**kwargs)

    def save_json(self, path: str) -> None:
        save_json(path, self.to_dict())

    @classmethod
    def load_json(cls, path: str) -> "BookJobRecord":
        return cls.from_dict(load_json(path))


# ── JSON helpers ─────────────────────────────────────────────────────────────

def save_json(path: str, data: dict) -> None:
    """Write data as pretty-printed UTF-8 JSON. Creates parent dirs if needed."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_json(path: str) -> dict:
    """Read and parse a JSON file. Raises ValueError on invalid JSON or non-object root."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"'{path}' must contain a JSON object at the top level")
    return data


def validate_record_dict(data: dict) -> None:
    """Validate that data has all required BookJobRecord fields and a valid status.

    Raises ValueError with a clear, combined message on failure.
    """
    if not isinstance(data, dict):
        raise ValueError("job record data must be a dict")

    missing = [f for f in REQUIRED_RECORD_FIELDS if f not in data]
    if missing:
        raise ValueError(f"job record missing required fields: {missing}")

    status = data.get("status")
    if status not in VALID_JOB_STATUSES:
        raise ValueError(f"job record has invalid status: '{status}'")
