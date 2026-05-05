"""SQLite-backed approvals for research methods."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional


class ApprovalStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or Path(__file__).with_name("approval_store.sqlite"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS method_approvals (
                    method_key TEXT PRIMARY KEY,
                    enabled_for_customers INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def list_statuses(self) -> Dict[str, bool]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT method_key, enabled_for_customers FROM method_approvals"
            ).fetchall()
        return {row["method_key"]: bool(row["enabled_for_customers"]) for row in rows}

    def get_status(self, method_key: str, default: bool = False) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT enabled_for_customers
                FROM method_approvals
                WHERE method_key = ?
                """,
                (method_key,),
            ).fetchone()
        if row is None:
            return default
        return bool(row["enabled_for_customers"])

    def set_customer_enabled(self, method_key: str, enabled: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO method_approvals (method_key, enabled_for_customers, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(method_key) DO UPDATE SET
                    enabled_for_customers = excluded.enabled_for_customers,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (method_key, int(enabled)),
            )
            connection.commit()

    def merge_methods(self, methods: Iterable[Dict[str, object]]) -> None:
        for method in methods:
            method_key = str(method["key"])
            enabled = bool(method.get("enabled_for_customers", False))
            if self.get_status(method_key, default=enabled) != enabled:
                self.set_customer_enabled(method_key, enabled)
