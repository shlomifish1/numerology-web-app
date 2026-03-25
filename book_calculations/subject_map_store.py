from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping


class SeferSubjectMapStore:
    _schema_ready = False

    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or Path(__file__).with_name("subject_maps.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not SeferSubjectMapStore._schema_ready:
            self._ensure_schema()
            SeferSubjectMapStore._schema_ready = True

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout = 30000")
            connection.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sefer_subject_map_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT NOT NULL UNIQUE,
                    subject_hash TEXT NOT NULL,
                    subject_identity_json TEXT NOT NULL DEFAULT '{}',
                    subject_payload_json TEXT NOT NULL DEFAULT '{}',
                    subject_full_name TEXT,
                    subject_first_name TEXT,
                    subject_last_name TEXT,
                    subject_birth_date TEXT,
                    book_id TEXT NOT NULL,
                    calculator_id TEXT NOT NULL,
                    definition_version TEXT NOT NULL,
                    calculator_version TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    total_calculations INTEGER NOT NULL DEFAULT 0,
                    computable_count INTEGER NOT NULL DEFAULT 0,
                    computed_full_trace_count INTEGER NOT NULL DEFAULT 0,
                    computed_partial_count INTEGER NOT NULL DEFAULT 0,
                    blocked_total_count INTEGER NOT NULL DEFAULT 0,
                    blocked_counts_json TEXT NOT NULL DEFAULT '{}',
                    with_interpretation_count INTEGER NOT NULL DEFAULT 0,
                    without_interpretation_count INTEGER NOT NULL DEFAULT 0,
                    interpretation_only_count INTEGER NOT NULL DEFAULT 0,
                    report_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sefer_subject_map_calculations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    calc_key TEXT NOT NULL,
                    label_he TEXT,
                    status TEXT NOT NULL,
                    runtime_status TEXT,
                    computed_value_json TEXT,
                    computed_value_text TEXT,
                    interpretation_text TEXT,
                    short_explanation TEXT,
                    formula_text TEXT,
                    formula_steps_json TEXT NOT NULL DEFAULT '[]',
                    input_dependencies_json TEXT NOT NULL DEFAULT '[]',
                    source_refs_json TEXT NOT NULL DEFAULT '[]',
                    execution_trace_json TEXT NOT NULL DEFAULT '{}',
                    reason_bucket TEXT,
                    has_real_runtime_trace INTEGER NOT NULL DEFAULT 0,
                    is_computed INTEGER NOT NULL DEFAULT 0,
                    is_partial INTEGER NOT NULL DEFAULT 0,
                    is_blocked INTEGER NOT NULL DEFAULT 0,
                    is_interpretation_only INTEGER NOT NULL DEFAULT 0,
                    is_research_only INTEGER NOT NULL DEFAULT 0,
                    enabled_in_full_map INTEGER,
                    scope TEXT,
                    result_group TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(run_id) REFERENCES sefer_subject_map_runs(id) ON DELETE CASCADE,
                    UNIQUE(run_id, calc_key)
                );

                CREATE INDEX IF NOT EXISTS idx_sefer_subject_map_lookup
                    ON sefer_subject_map_runs(calculator_id, book_id, definition_version, calculator_version, subject_hash, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_sefer_subject_map_calcs_run
                    ON sefer_subject_map_calculations(run_id, sort_order);
                """
            )
            connection.commit()

    def get_cached_report(self, cache_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, report_json, created_at, updated_at
                FROM sefer_subject_map_runs
                WHERE cache_key = ?
                LIMIT 1
                """,
                (cache_key,),
            ).fetchone()
        if not row:
            return None
        try:
            report = json.loads(str(row["report_json"] or "{}"))
        except Exception:
            return None
        if not isinstance(report, dict):
            return None
        report["_cache_db_meta"] = {
            "run_id": int(row["id"]),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }
        return report

    def save_report(
        self,
        *,
        cache_key: str,
        subject_hash: str,
        subject_identity: Mapping[str, Any],
        subject_payload: Mapping[str, Any],
        book_id: str,
        calculator_id: str,
        definition_version: str,
        calculator_version: str,
        report: Mapping[str, Any],
    ) -> int:
        summary = report.get("summary", {}) if isinstance(report, Mapping) else {}
        blocked_counts = summary.get("blocked_by_reason", {}) if isinstance(summary, Mapping) else {}
        calculations = report.get("calculations", []) if isinstance(report, Mapping) else []

        full_name = str(subject_identity.get("full_name") or "")
        first_name = str(subject_identity.get("first_name") or "")
        last_name = str(subject_identity.get("last_name") or "")
        birth_date = str(subject_identity.get("birth_date") or "")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sefer_subject_map_runs (
                    cache_key,
                    subject_hash,
                    subject_identity_json,
                    subject_payload_json,
                    subject_full_name,
                    subject_first_name,
                    subject_last_name,
                    subject_birth_date,
                    book_id,
                    calculator_id,
                    definition_version,
                    calculator_version,
                    summary_json,
                    total_calculations,
                    computable_count,
                    computed_full_trace_count,
                    computed_partial_count,
                    blocked_total_count,
                    blocked_counts_json,
                    with_interpretation_count,
                    without_interpretation_count,
                    interpretation_only_count,
                    report_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(cache_key) DO UPDATE SET
                    subject_hash = excluded.subject_hash,
                    subject_identity_json = excluded.subject_identity_json,
                    subject_payload_json = excluded.subject_payload_json,
                    subject_full_name = excluded.subject_full_name,
                    subject_first_name = excluded.subject_first_name,
                    subject_last_name = excluded.subject_last_name,
                    subject_birth_date = excluded.subject_birth_date,
                    book_id = excluded.book_id,
                    calculator_id = excluded.calculator_id,
                    definition_version = excluded.definition_version,
                    calculator_version = excluded.calculator_version,
                    summary_json = excluded.summary_json,
                    total_calculations = excluded.total_calculations,
                    computable_count = excluded.computable_count,
                    computed_full_trace_count = excluded.computed_full_trace_count,
                    computed_partial_count = excluded.computed_partial_count,
                    blocked_total_count = excluded.blocked_total_count,
                    blocked_counts_json = excluded.blocked_counts_json,
                    with_interpretation_count = excluded.with_interpretation_count,
                    without_interpretation_count = excluded.without_interpretation_count,
                    interpretation_only_count = excluded.interpretation_only_count,
                    report_json = excluded.report_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    cache_key,
                    subject_hash,
                    json.dumps(dict(subject_identity), ensure_ascii=False, sort_keys=True),
                    json.dumps(dict(subject_payload), ensure_ascii=False, sort_keys=True),
                    full_name,
                    first_name,
                    last_name,
                    birth_date,
                    book_id,
                    calculator_id,
                    definition_version,
                    calculator_version,
                    json.dumps(summary, ensure_ascii=False, sort_keys=True),
                    int(summary.get("total_calculations", 0) or 0),
                    int(summary.get("computable_returned", 0) or 0),
                    int(summary.get("computed_with_full_trace", 0) or 0),
                    int(summary.get("computed_partial", 0) or 0),
                    int(sum(int(v) for v in (blocked_counts.values() if isinstance(blocked_counts, Mapping) else []))),
                    json.dumps(blocked_counts if isinstance(blocked_counts, Mapping) else {}, ensure_ascii=False, sort_keys=True),
                    int(summary.get("with_interpretation", 0) or 0),
                    int(summary.get("without_interpretation", 0) or 0),
                    int(summary.get("interpretation_only", 0) or 0),
                    json.dumps(dict(report), ensure_ascii=False, sort_keys=True),
                ),
            )

            run_row = connection.execute(
                "SELECT id FROM sefer_subject_map_runs WHERE cache_key = ? LIMIT 1",
                (cache_key,),
            ).fetchone()
            if not run_row:
                raise RuntimeError("Failed to persist subject-map run header")
            run_id = int(run_row["id"])

            connection.execute(
                "DELETE FROM sefer_subject_map_calculations WHERE run_id = ?",
                (run_id,),
            )

            for index, item in enumerate(calculations if isinstance(calculations, list) else []):
                calc = item if isinstance(item, Mapping) else {}
                status = str(calc.get("status") or "")
                blocked_reason = status if status not in {"computed", "partially_computed"} else ""
                computed_value = calc.get("computed_value")

                connection.execute(
                    """
                    INSERT INTO sefer_subject_map_calculations (
                        run_id,
                        sort_order,
                        calc_key,
                        label_he,
                        status,
                        runtime_status,
                        computed_value_json,
                        computed_value_text,
                        interpretation_text,
                        short_explanation,
                        formula_text,
                        formula_steps_json,
                        input_dependencies_json,
                        source_refs_json,
                        execution_trace_json,
                        reason_bucket,
                        has_real_runtime_trace,
                        is_computed,
                        is_partial,
                        is_blocked,
                        is_interpretation_only,
                        is_research_only,
                        enabled_in_full_map,
                        scope,
                        result_group
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        index,
                        str(calc.get("calc_key") or ""),
                        str(calc.get("label_he") or ""),
                        status,
                        str(calc.get("runtime_status") or ""),
                        json.dumps(computed_value, ensure_ascii=False, sort_keys=True),
                        "" if computed_value is None else str(computed_value),
                        str(calc.get("interpretation") or ""),
                        str(calc.get("short_explanation") or ""),
                        str(calc.get("formula_text") or ""),
                        json.dumps(calc.get("formula_steps") or [], ensure_ascii=False, sort_keys=True),
                        json.dumps(calc.get("input_dependencies") or [], ensure_ascii=False, sort_keys=True),
                        json.dumps(calc.get("source_refs") or [], ensure_ascii=False, sort_keys=True),
                        json.dumps(calc.get("execution_trace") or {}, ensure_ascii=False, sort_keys=True),
                        blocked_reason or None,
                        1 if bool(calc.get("trace_is_full")) else 0,
                        1 if status == "computed" else 0,
                        1 if status == "partially_computed" else 0,
                        1 if status not in {"computed", "partially_computed"} else 0,
                        1 if status == "interpretation_only" else 0,
                        1 if str(calc.get("scope") or "") == "research_only" else 0,
                        None
                        if calc.get("enabled_in_full_map") is None
                        else (1 if bool(calc.get("enabled_in_full_map")) else 0),
                        str(calc.get("scope") or ""),
                        str(calc.get("result_group") or ""),
                    ),
                )

            connection.commit()
            return run_id
