from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from interpretation_layout import RESEARCH_ROOT, normalize_corpus_key, source_label_to_corpus_alias

from .final_map_store import FinalMapStore
from .method_registry import INTERNAL_BASELINE_KEY, MethodRegistry


_LEGACY_RUNTIME_ALIASES = {"men", "women"}
_STALE_SOURCE_TOKENS = {
    "interpretations/astrology",
    "interpretations/spirit",
    "interpretations/more_books",
    "interpretations/men",
    "interpretations/women",
    "pythagorean_existing",
}


def _active_research_book_aliases() -> set[str]:
    aliases: set[str] = set()
    if not RESEARCH_ROOT.exists():
        return aliases
    for folder in RESEARCH_ROOT.iterdir():
        if not folder.is_dir() or folder.name == "raw_books":
            continue
        aliases.add(folder.name)
        aliases.add(normalize_corpus_key(folder.name))
    return aliases


def _valid_method_keys() -> set[str]:
    registry = MethodRegistry()
    methods = registry.refresh()
    return {
        str(method.get("key") or "").strip()
        for method in methods
        if str(method.get("key") or "").strip()
    }


def _json_load(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _source_is_valid(source_ref: Any, active_aliases: set[str]) -> bool:
    text = str(source_ref or "").strip().replace("\\", "/")
    if not text:
        return False
    lowered = text.lower()
    if lowered in {"user input", "קלט המשתמש"}:
        return True
    if any(token in lowered for token in _STALE_SOURCE_TOKENS):
        return False
    if lowered.startswith("interpretations/runtime/legacy/"):
        alias = source_label_to_corpus_alias(lowered)
        return alias in _LEGACY_RUNTIME_ALIASES
    if lowered.startswith("interpretations/research/"):
        alias = source_label_to_corpus_alias(lowered)
        return bool(alias) and (
            alias in active_aliases or normalize_corpus_key(alias) in active_aliases
        )
    return False


def _history_row_is_stale(
    row: sqlite3.Row,
    *,
    active_aliases: set[str],
    active_public_methods: set[str],
) -> bool:
    methods_count = int(row["methods_count"] or 0)
    if methods_count > max(1, len(active_public_methods)):
        return True

    sections = _json_load(row["report_sections_json"], [])
    for section in sections:
        if not isinstance(section, dict):
            continue
        source_ref = section.get("source")
        if source_ref and not _source_is_valid(source_ref, active_aliases):
            return True

    summary = _json_load(row["report_summary_json"], {})
    for alias in list(summary.get("book_evidence_corpora") or []):
        normalized = normalize_corpus_key(alias)
        if normalized and normalized not in active_aliases:
            return True

    return False


def cleanup_stale_research_state() -> dict[str, int]:
    registry = MethodRegistry()
    methods = registry.refresh()
    active_aliases = _active_research_book_aliases()
    valid_method_keys = {
        str(method.get("key") or "").strip()
        for method in methods
        if str(method.get("key") or "").strip()
    }
    active_public_methods = {
        key
        for key in valid_method_keys
        if key and key != INTERNAL_BASELINE_KEY
    }

    store = FinalMapStore()
    removed_entries = 0
    removed_history = 0
    removed_notes = 0
    removed_versions = 0

    with store._connect() as conn:  # noqa: SLF001 - targeted maintenance helper
        map_rows = conn.execute(
            """
            SELECT id, row_key, method_key, source_ref
            FROM map_entries
            """
        ).fetchall()
        for row in map_rows:
            row_key = str(row["row_key"] or "").strip()
            method_key = str(row["method_key"] or "").strip()
            source_ref = str(row["source_ref"] or "").strip()
            invalid_row = not row_key or not method_key
            invalid_method = bool(method_key) and method_key not in valid_method_keys
            invalid_source = bool(source_ref) and not _source_is_valid(source_ref, active_aliases)
            if invalid_row or invalid_method or invalid_source:
                conn.execute("DELETE FROM map_entries WHERE id = ?", (row["id"],))
                removed_entries += 1

        note_rows = conn.execute(
            """
            SELECT id, source_ref
            FROM map_notes
            """
        ).fetchall()
        for row in note_rows:
            source_ref = str(row["source_ref"] or "").strip()
            if source_ref and not _source_is_valid(source_ref, active_aliases):
                conn.execute("DELETE FROM map_notes WHERE id = ?", (row["id"],))
                removed_notes += 1

        version_rows = conn.execute(
            """
            SELECT id, snapshot_json
            FROM map_versions
            """
        ).fetchall()
        for row in version_rows:
            snapshot = _json_load(row["snapshot_json"], [])
            invalid_snapshot = False
            if isinstance(snapshot, list):
                for item in snapshot:
                    if not isinstance(item, dict):
                        continue
                    method_key = str(item.get("method_key") or "").strip()
                    source_ref = str(item.get("source_ref") or "").strip()
                    row_key = str(item.get("row_key") or "").strip()
                    if not row_key or (method_key and method_key not in valid_method_keys):
                        invalid_snapshot = True
                        break
                    if source_ref and not _source_is_valid(source_ref, active_aliases):
                        invalid_snapshot = True
                        break
            if invalid_snapshot:
                conn.execute("DELETE FROM map_versions WHERE id = ?", (row["id"],))
                removed_versions += 1

        history_rows = conn.execute(
            """
            SELECT id, methods_count, report_summary_json, report_sections_json
            FROM research_history
            """
        ).fetchall()
        for row in history_rows:
            if _history_row_is_stale(
                row,
                active_aliases=active_aliases,
                active_public_methods=active_public_methods,
            ):
                conn.execute("DELETE FROM research_history WHERE id = ?", (row["id"],))
                removed_history += 1
        conn.commit()

    return {
        "active_research_books": len(active_aliases),
        "removed_map_entries": removed_entries,
        "removed_map_notes": removed_notes,
        "removed_map_versions": removed_versions,
        "removed_history_rows": removed_history,
    }
