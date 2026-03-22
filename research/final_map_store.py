"""SQLite-backed persistence for research and automatic numerology maps."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class FinalMapStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or Path(__file__).with_name("final_map_store.sqlite"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS map_entries (
                    id              TEXT PRIMARY KEY,
                    map_scope       TEXT NOT NULL DEFAULT 'auto',
                    profile_key     TEXT NOT NULL DEFAULT '',
                    profile_label   TEXT NOT NULL DEFAULT '',
                    row_key         TEXT NOT NULL DEFAULT '',
                    row_label       TEXT NOT NULL DEFAULT '',
                    method_key      TEXT NOT NULL DEFAULT '',
                    method_label    TEXT NOT NULL DEFAULT '',
                    value           TEXT NOT NULL DEFAULT '',
                    summary         TEXT NOT NULL DEFAULT '',
                    preview         TEXT NOT NULL DEFAULT '',
                    sections_json   TEXT NOT NULL DEFAULT '[]',
                    snapshot_json   TEXT NOT NULL DEFAULT '{}',
                    version_key     TEXT NOT NULL DEFAULT 'live',
                    layer_key       TEXT NOT NULL DEFAULT 'live',
                    decision_state  TEXT NOT NULL DEFAULT 'approved',
                    confidence      REAL NOT NULL DEFAULT 0.0,
                    source_ref      TEXT NOT NULL DEFAULT '',
                    source_kind     TEXT NOT NULL DEFAULT 'cell',
                    cabinet_used    INTEGER NOT NULL DEFAULT 0,
                    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(map_scope, profile_key, row_key, method_key, value)
                );

                CREATE TABLE IF NOT EXISTS map_notes (
                    id            TEXT PRIMARY KEY,
                    map_scope     TEXT NOT NULL DEFAULT 'auto',
                    profile_key   TEXT NOT NULL DEFAULT '',
                    note_kind     TEXT NOT NULL DEFAULT 'note',
                    confidence    REAL NOT NULL DEFAULT 0.0,
                    source_kind   TEXT NOT NULL DEFAULT '',
                    source_ref    TEXT NOT NULL DEFAULT '',
                    note_text     TEXT NOT NULL DEFAULT '',
                    source_entry  TEXT NOT NULL DEFAULT '',
                    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS map_versions (
                    id            TEXT PRIMARY KEY,
                    map_scope     TEXT NOT NULL DEFAULT 'auto',
                    profile_key   TEXT NOT NULL DEFAULT '',
                    version_label TEXT NOT NULL DEFAULT '',
                    version_index  INTEGER NOT NULL DEFAULT 0,
                    entry_count    INTEGER NOT NULL DEFAULT 0,
                    snapshot_json  TEXT NOT NULL DEFAULT '[]',
                    source_kind   TEXT NOT NULL DEFAULT 'manual',
                    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._ensure_columns(
                conn,
                "map_entries",
                {
                    "version_key": "TEXT NOT NULL DEFAULT 'live'",
                    "layer_key": "TEXT NOT NULL DEFAULT 'live'",
                    "decision_state": "TEXT NOT NULL DEFAULT 'approved'",
                    "confidence": "REAL NOT NULL DEFAULT 0.0",
                    "source_ref": "TEXT NOT NULL DEFAULT ''",
                },
            )
            self._ensure_columns(
                conn,
                "map_notes",
                {
                    "note_kind": "TEXT NOT NULL DEFAULT 'note'",
                    "confidence": "REAL NOT NULL DEFAULT 0.0",
                    "source_kind": "TEXT NOT NULL DEFAULT ''",
                    "source_ref": "TEXT NOT NULL DEFAULT ''",
                },
            )
            conn.commit()

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _json_load(value: Any, fallback: Any) -> Any:
        if value in (None, ""):
            return fallback
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except Exception:
            return fallback

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _scope(value: Any) -> str:
        return "research" if str(value).strip().lower() == "research" else "auto"

    @staticmethod
    def _entry_key(entry: dict[str, Any], scope: str) -> tuple[str, str, str, str, str]:
        return (
            scope,
            str(entry.get("profile_key") or ""),
            str(entry.get("row_key") or ""),
            str(entry.get("method_key") or ""),
            str(entry.get("value") or ""),
        )

    def upsert_entry(self, entry: dict[str, Any], scope: str = "auto", source_kind: str = "cell") -> dict[str, Any]:
        scope = self._scope(scope)
        entry_id = self._clean_text(entry.get("id")) or str(uuid.uuid4())
        version_key = self._clean_text(entry.get("version_key")) or "live"
        layer_key = self._clean_text(entry.get("layer_key")) or scope
        payload = {
            "id": entry_id,
            "map_scope": scope,
            "profile_key": self._clean_text(entry.get("profile_key")),
            "profile_label": self._clean_text(entry.get("profile_label")),
            "row_key": self._clean_text(entry.get("row_key")),
            "row_label": self._clean_text(entry.get("row_label")),
            "method_key": self._clean_text(entry.get("method_key")),
            "method_label": self._clean_text(entry.get("method_label")),
            "value": self._clean_text(entry.get("value")),
            "summary": self._clean_text(entry.get("summary")),
            "preview": self._clean_text(entry.get("preview")),
            "sections_json": json.dumps(entry.get("sections") or [], ensure_ascii=False),
            "snapshot_json": json.dumps(entry.get("snapshot") or {}, ensure_ascii=False),
            "version_key": version_key,
            "layer_key": layer_key,
            "decision_state": self._clean_text(entry.get("decision_state")) or "approved",
            "confidence": float(entry.get("confidence") or 0.0),
            "source_ref": self._clean_text(entry.get("source_ref")),
            "source_kind": self._clean_text(source_kind or entry.get("source_kind") or "cell") or "cell",
            "cabinet_used": 1 if entry.get("cabinet_used") else 0,
            "updated_at": self._utc_now(),
        }
        key = self._entry_key(payload, scope)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO map_entries (
                    id, map_scope, profile_key, profile_label, row_key, row_label,
                    method_key, method_label, value, summary, preview, sections_json,
                    snapshot_json, version_key, layer_key, decision_state, confidence,
                    source_ref, source_kind, cabinet_used, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(map_scope, profile_key, row_key, method_key, value) DO UPDATE SET
                    profile_label = excluded.profile_label,
                    row_label = excluded.row_label,
                    method_label = excluded.method_label,
                    summary = excluded.summary,
                    preview = excluded.preview,
                    sections_json = excluded.sections_json,
                    snapshot_json = excluded.snapshot_json,
                    version_key = excluded.version_key,
                    layer_key = excluded.layer_key,
                    decision_state = excluded.decision_state,
                    confidence = excluded.confidence,
                    source_ref = excluded.source_ref,
                    source_kind = excluded.source_kind,
                    cabinet_used = excluded.cabinet_used,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["id"],
                    payload["map_scope"],
                    payload["profile_key"],
                    payload["profile_label"],
                    payload["row_key"],
                    payload["row_label"],
                    payload["method_key"],
                    payload["method_label"],
                    payload["value"],
                    payload["summary"],
                    payload["preview"],
                    payload["sections_json"],
                    payload["snapshot_json"],
                    payload["version_key"],
                    payload["layer_key"],
                    payload["decision_state"],
                    payload["confidence"],
                    payload["source_ref"],
                    payload["source_kind"],
                    payload["cabinet_used"],
                    payload["updated_at"],
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM map_entries
                WHERE map_scope = ? AND profile_key = ? AND row_key = ? AND method_key = ? AND value = ?
                """,
                key,
            ).fetchone()
        return self._row_to_entry(row) or {}

    def delete_entry(self, entry_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM map_entries WHERE id = ?", (entry_id,))
            conn.commit()
            return cur.rowcount > 0

    def set_entry_decision(self, entry_id: str, decision_state: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE map_entries SET decision_state = ?, updated_at = ? WHERE id = ?",
                (self._clean_text(decision_state) or "approved", self._utc_now(), entry_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def promote_entry(self, entry_id: str, target_scope: str = "auto") -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM map_entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        item = self._row_to_entry(row)
        if not item:
            return None
        item["map_scope"] = self._scope(target_scope)
        item["layer_key"] = "final"
        item["decision_state"] = "approved"
        item["source_kind"] = "final_promotion"
        item["source_ref"] = item.get("source_ref") or entry_id
        item["version_key"] = item.get("version_key") or "live"
        return self.upsert_entry(item, scope=item["map_scope"], source_kind=str(item.get("source_kind") or "promoted"))

    def clear_entries(self, scope: str | None = None, profile_key: str | None = None) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if scope:
            clauses.append("map_scope = ?")
            params.append(self._scope(scope))
        if profile_key:
            clauses.append("profile_key = ?")
            params.append(profile_key)
        query = "DELETE FROM map_entries"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            cur = conn.execute(query, params)
            conn.commit()
            return int(cur.rowcount or 0)

    def list_entries(
        self,
        scope: str | None = None,
        profile_key: str | None = None,
        version_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if version_id:
            version = self.get_version(version_id)
            if not version:
                return []
            snapshot = self._json_load(version.get("snapshot_json"), [])
            entries = [self._normalize_snapshot_entry(item) for item in snapshot if isinstance(item, dict)]
            return entries[:limit] if limit else entries
        clauses: list[str] = []
        params: list[Any] = []
        if scope:
            clauses.append("map_scope = ?")
            params.append(self._scope(scope))
        if profile_key:
            clauses.append("profile_key = ?")
            params.append(profile_key)
        query = "SELECT * FROM map_entries"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY CASE map_scope WHEN 'auto' THEN 0 ELSE 1 END, updated_at DESC, created_at DESC"
        if limit:
            query += " LIMIT ?"
            params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_entry(row) for row in rows if row is not None]

    def counts(self, profile_key: str | None = None) -> dict[str, int]:
        clauses: list[str] = []
        params: list[Any] = []
        if profile_key:
            clauses.append("profile_key = ?")
            params.append(profile_key)
        query = "SELECT map_scope, COUNT(*) AS count FROM map_entries"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " GROUP BY map_scope"
        result = {"auto": 0, "research": 0, "final": 0, "total": 0}
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            final_query = "SELECT COUNT(*) AS count FROM map_entries WHERE layer_key = 'final'"
            final_params: list[Any] = []
            if profile_key:
                final_query += " AND profile_key = ?"
                final_params.append(profile_key)
            final_row = conn.execute(final_query, final_params).fetchone()
        for row in rows:
            scope = self._scope(row["map_scope"])
            count = int(row["count"] or 0)
            result[scope] = count
            result["total"] += count
        result["final"] = int(final_row["count"] or 0) if final_row else 0
        return result

    def add_note(
        self,
        note_text: str,
        profile_key: str = "",
        scope: str = "auto",
        source_entry: str = "",
        note_kind: str = "note",
        confidence: float = 0.0,
        source_kind: str = "",
        source_ref: str = "",
    ) -> dict[str, Any]:
        note_id = str(uuid.uuid4())
        scope = self._scope(scope)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO map_notes (
                    id, map_scope, profile_key, note_kind, confidence, source_kind,
                    source_ref, note_text, source_entry, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (note_id, scope, profile_key, self._clean_text(note_kind) or "note", float(confidence or 0.0), self._clean_text(source_kind), self._clean_text(source_ref), note_text, source_entry, self._utc_now()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM map_notes WHERE id = ?", (note_id,)).fetchone()
        return dict(row) if row is not None else {}

    def list_notes(self, scope: str | None = None, profile_key: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope:
            clauses.append("map_scope = ?")
            params.append(self._scope(scope))
        if profile_key:
            clauses.append("profile_key = ?")
            params.append(profile_key)
        query = "SELECT * FROM map_notes"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def search(
        self,
        query_text: str,
        scope: str | None = None,
        profile_key: str | None = None,
        limit: int = 50,
    ) -> dict[str, list[dict[str, Any]]]:
        terms = [part.strip() for part in str(query_text or "").split() if part.strip()]
        if not terms:
            return {"entries": [], "notes": []}

        entry_clauses = []
        note_clauses = []
        entry_params: list[Any] = []
        note_params: list[Any] = []
        for term in terms:
            pattern = f"%{term}%"
            entry_clauses.append(
                "(profile_key LIKE ? OR profile_label LIKE ? OR row_key LIKE ? OR row_label LIKE ? OR method_key LIKE ? OR method_label LIKE ? OR value LIKE ? OR summary LIKE ? OR preview LIKE ? OR source_ref LIKE ? OR source_kind LIKE ? OR map_scope LIKE ? OR layer_key LIKE ?)"
            )
            entry_params.extend([pattern] * 13)
            note_clauses.append("(profile_key LIKE ? OR note_text LIKE ? OR note_kind LIKE ? OR source_ref LIKE ? OR source_kind LIKE ?)")
            note_params.extend([pattern] * 5)

        entry_query = "SELECT * FROM map_entries WHERE " + " AND ".join(entry_clauses)
        note_query = "SELECT * FROM map_notes WHERE " + " AND ".join(note_clauses)
        if scope:
            entry_query += " AND map_scope = ?"
            note_query += " AND map_scope = ?"
            entry_params.append(self._scope(scope))
            note_params.append(self._scope(scope))
        if profile_key:
            entry_query += " AND profile_key = ?"
            note_query += " AND profile_key = ?"
            entry_params.append(profile_key)
            note_params.append(profile_key)
        entry_query += " ORDER BY updated_at DESC LIMIT ?"
        note_query += " ORDER BY created_at DESC LIMIT ?"
        entry_params.append(limit)
        note_params.append(limit)
        with self._connect() as conn:
            entry_rows = conn.execute(entry_query, entry_params).fetchall()
            note_rows = conn.execute(note_query, note_params).fetchall()
        return {
            "entries": [self._row_to_entry(row) for row in entry_rows if row is not None],
            "notes": [dict(row) for row in note_rows if row is not None],
        }

    def create_version(
        self,
        scope: str = "auto",
        profile_key: str = "",
        version_label: str = "",
        source_kind: str = "manual",
    ) -> dict[str, Any]:
        scope = self._scope(scope)
        entries = self.list_entries(scope=scope, profile_key=profile_key or None, limit=500)
        version_id = str(uuid.uuid4())
        version_label = self._clean_text(version_label) or f"{scope}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        snapshot = json.dumps(entries, ensure_ascii=False)
        with self._connect() as conn:
            version_index = int(
                conn.execute(
                    "SELECT COALESCE(MAX(version_index), 0) + 1 AS next_index FROM map_versions WHERE map_scope = ? AND profile_key = ?",
                    (scope, profile_key),
                ).fetchone()["next_index"]
            )
            conn.execute(
                """
                INSERT INTO map_versions (
                    id, map_scope, profile_key, version_label, version_index,
                    entry_count, snapshot_json, source_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    scope,
                    profile_key,
                    version_label,
                    version_index,
                    len(entries),
                    snapshot,
                    self._clean_text(source_kind) or "manual",
                    self._utc_now(),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM map_versions WHERE id = ?", (version_id,)).fetchone()
        return dict(row) if row is not None else {}

    def list_versions(self, scope: str | None = None, profile_key: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope:
            clauses.append("map_scope = ?")
            params.append(self._scope(scope))
        if profile_key:
            clauses.append("profile_key = ?")
            params.append(profile_key)
        query = "SELECT * FROM map_versions"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM map_versions WHERE id = ?", (version_id,)).fetchone()
        return dict(row) if row is not None else None

    def restore_version(self, version_id: str) -> dict[str, Any] | None:
        version = self.get_version(version_id)
        if not version:
            return None
        scope = self._scope(version.get("map_scope"))
        profile_key = str(version.get("profile_key") or "")
        snapshot = self._json_load(version.get("snapshot_json"), [])
        removed = self.clear_entries(scope=scope, profile_key=profile_key or None)
        restored = 0
        for item in snapshot:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_snapshot_entry(item)
            normalized["map_scope"] = scope
            normalized["profile_key"] = profile_key
            normalized["layer_key"] = normalized.get("layer_key") or scope
            normalized["version_key"] = version.get("id") or normalized.get("version_key") or "live"
            normalized["decision_state"] = normalized.get("decision_state") or "approved"
            normalized["source_kind"] = normalized.get("source_kind") or "snapshot"
            normalized["source_ref"] = normalized.get("source_ref") or version_id
            self.upsert_entry(normalized, scope=scope, source_kind=str(normalized.get("source_kind") or "snapshot"))
            restored += 1
        return {
            "version": version,
            "removed": removed,
            "restored": restored,
            "counts": self.counts(profile_key or None),
        }

    def _normalize_snapshot_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        item = dict(entry)
        item["sections"] = self._json_load(item.get("sections_json"), item.get("sections", []))
        item["snapshot"] = self._json_load(item.get("snapshot_json"), item.get("snapshot", {}))
        item["cabinet_used"] = bool(item.get("cabinet_used"))
        item["version_key"] = item.get("version_key") or "snapshot"
        item["layer_key"] = item.get("layer_key") or item.get("map_scope") or "live"
        item["decision_state"] = item.get("decision_state") or "approved"
        item["confidence"] = float(item.get("confidence") or 0.0)
        item["source_ref"] = item.get("source_ref") or ""
        item["source_kind"] = item.get("source_kind") or ""
        return item

    def _row_to_entry(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["sections"] = self._json_load(item.get("sections_json"), [])
        item["snapshot"] = self._json_load(item.get("snapshot_json"), {})
        item["cabinet_used"] = bool(item.get("cabinet_used"))
        item["confidence"] = float(item.get("confidence") or 0.0)
        item["source_ref"] = item.get("source_ref") or ""
        item["source_kind"] = item.get("source_kind") or ""
        return item
