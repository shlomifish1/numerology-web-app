"""SQLite persistence for ingested book metadata, chunks, and chapter categories."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


GENERATED_PATTERNS = ('%_books.md', '%_category_map.md', '%_ocr_queue.md', '%_runtime.md', '%_seed_plan.md', '%_taxonomy.md', '%_intake.md')


class KnowledgeStore:
    _schema_ready = False

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or Path(__file__).with_name('numerology_books.db'))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not KnowledgeStore._schema_ready:
            self._ensure_schema()
            KnowledgeStore._schema_ready = True

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout = 30000")
        except Exception:
            pass
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            existing_tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required_tables = {
                "books",
                "book_chunks",
                "book_categories",
                "book_rules",
                "book_artifacts",
                "book_learning_log",
            }
            if required_tables.issubset(existing_tables):
                return

            ddl = """
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    corpus TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    source_path TEXT NOT NULL UNIQUE,
                    extension TEXT,
                    language_hint TEXT,
                    status TEXT NOT NULL,
                    text_length INTEGER NOT NULL DEFAULT 0,
                    excerpt TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS book_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE,
                    UNIQUE(book_id, chunk_index)
                );

                CREATE TABLE IF NOT EXISTS book_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    source TEXT NOT NULL DEFAULT 'rule',
                    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE,
                    UNIQUE(book_id, category)
                );

                CREATE TABLE IF NOT EXISTS book_rules (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    corpus        TEXT    NOT NULL,
                    concept_key   TEXT    NOT NULL,
                    concept_label TEXT    NOT NULL,
                    calc_method   TEXT,
                    interpretation_rules TEXT,
                    source_chunks TEXT,
                    confidence    REAL    NOT NULL DEFAULT 0.0,
                    cabinet_used  INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(corpus, concept_key)
                );

                CREATE TABLE IF NOT EXISTS book_artifacts (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id       INTEGER NOT NULL,
                    artifact_type TEXT NOT NULL DEFAULT 'raw',
                    content_text  TEXT NOT NULL DEFAULT '',
                    content_json  TEXT NOT NULL DEFAULT '{}',
                    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS book_learning_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    corpus      TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    progress    TEXT,
                    error       TEXT,
                    started_at  TEXT,
                    finished_at TEXT,
                    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_books_corpus_updated ON books(corpus, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_books_source_path ON books(source_path);
                CREATE INDEX IF NOT EXISTS idx_book_chunks_book_id ON book_chunks(book_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_book_artifacts_book_id ON book_artifacts(book_id, artifact_type);
                CREATE INDEX IF NOT EXISTS idx_book_rules_corpus ON book_rules(corpus, concept_key);
                CREATE INDEX IF NOT EXISTS idx_learning_log_corpus_created ON book_learning_log(corpus, created_at DESC);
            """
            connection.executescript(ddl)
            connection.commit()

    def upsert_book(self, record: Dict[str, object]) -> int:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO books (
                    corpus, title, author, source_path, extension, language_hint,
                    status, text_length, excerpt, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_path) DO UPDATE SET
                    corpus = excluded.corpus,
                    title = excluded.title,
                    author = excluded.author,
                    extension = excluded.extension,
                    language_hint = excluded.language_hint,
                    status = excluded.status,
                    text_length = excluded.text_length,
                    excerpt = excluded.excerpt,
                    metadata_json = excluded.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    record.get('corpus'),
                    record.get('title'),
                    record.get('author'),
                    record.get('source_path'),
                    record.get('extension'),
                    record.get('language_hint'),
                    record.get('status'),
                    int(record.get('text_length') or 0),
                    record.get('excerpt'),
                    record.get('metadata_json'),
                ),
            )
            book_id = connection.execute(
                'SELECT id FROM books WHERE source_path = ?',
                (record.get('source_path'),),
            ).fetchone()['id']
            connection.commit()
            return int(book_id)

    def replace_chunks(self, book_id: int, chunks: Iterable[str]) -> None:
        with self._connect() as connection:
            connection.execute('DELETE FROM book_chunks WHERE book_id = ?', (book_id,))
            for index, chunk in enumerate(chunks):
                connection.execute(
                    'INSERT INTO book_chunks (book_id, chunk_index, content) VALUES (?, ?, ?)',
                    (book_id, index, chunk),
                )
            connection.commit()

    def replace_categories(self, book_id: int, categories: Iterable[Dict[str, object]]) -> None:
        with self._connect() as connection:
            connection.execute('DELETE FROM book_categories WHERE book_id = ?', (book_id,))
            for item in categories:
                connection.execute(
                    'INSERT INTO book_categories (book_id, category, confidence, source) VALUES (?, ?, ?, ?)',
                    (book_id, item['category'], float(item.get('confidence', 0.0)), item.get('source', 'rule')),
                )
            connection.commit()

    def save_book_artifact(self, book_id: int, artifact_type: str, content_text: str = '', content_json: Dict[str, object] | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                'INSERT INTO book_artifacts (book_id, artifact_type, content_text, content_json) VALUES (?, ?, ?, ?)',
                (book_id, artifact_type, content_text, json.dumps(content_json or {}, ensure_ascii=False)),
            )
            connection.commit()

    def sync_corpus_sources(self, corpus: str, valid_sources: Sequence[str]) -> None:
        with self._connect() as connection:
            existing = connection.execute(
                'SELECT id, source_path FROM books WHERE corpus = ?',
                (corpus,),
            ).fetchall()
            valid = set(valid_sources)
            stale_ids = [row['id'] for row in existing if row['source_path'] not in valid]
            if stale_ids:
                placeholders = ','.join('?' for _ in stale_ids)
                connection.execute(f'DELETE FROM book_categories WHERE book_id IN ({placeholders})', stale_ids)
                connection.execute(f'DELETE FROM book_chunks WHERE book_id IN ({placeholders})', stale_ids)
                connection.execute(f'DELETE FROM books WHERE id IN ({placeholders})', stale_ids)
            connection.commit()

    def purge_generated_records(self, corpus: str) -> None:
        with self._connect() as connection:
            rows = []
            for pattern in GENERATED_PATTERNS:
                rows.extend(
                    connection.execute(
                        'SELECT id FROM books WHERE corpus = ? AND source_path LIKE ?',
                        (corpus, pattern),
                    ).fetchall()
                )
            stale_ids = [row['id'] for row in rows]
            if stale_ids:
                placeholders = ','.join('?' for _ in stale_ids)
                connection.execute(f'DELETE FROM book_categories WHERE book_id IN ({placeholders})', stale_ids)
                connection.execute(f'DELETE FROM book_chunks WHERE book_id IN ({placeholders})', stale_ids)
                connection.execute(f'DELETE FROM books WHERE id IN ({placeholders})', stale_ids)
            connection.commit()

    def list_books(self, corpus: Optional[str] = None) -> List[Dict[str, object]]:
        query = 'SELECT * FROM books WHERE 1=1'
        params: List[object] = []
        if corpus:
            query += ' AND corpus = ?'
            params.append(corpus)
        for pattern in GENERATED_PATTERNS:
            query += ' AND source_path NOT LIKE ?'
            params.append(pattern)
        query += ' ORDER BY title COLLATE NOCASE'
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def list_books_with_categories(self, corpus: str) -> List[Dict[str, object]]:
        with self._connect() as connection:
            query = 'SELECT * FROM books WHERE corpus = ?'
            params: List[object] = [corpus]
            for pattern in GENERATED_PATTERNS:
                query += ' AND source_path NOT LIKE ?'
                params.append(pattern)
            query += ' ORDER BY title COLLATE NOCASE'
            books = connection.execute(query, tuple(params)).fetchall()
            category_query = """
                SELECT b.source_path, c.category, c.confidence, c.source
                FROM books b
                JOIN book_categories c ON c.book_id = b.id
                WHERE b.corpus = ?
            """
            category_params: List[object] = [corpus]
            for pattern in GENERATED_PATTERNS:
                category_query += ' AND b.source_path NOT LIKE ?'
                category_params.append(pattern)
            category_query += ' ORDER BY b.title COLLATE NOCASE, c.confidence DESC, c.category'
            category_rows = connection.execute(category_query, tuple(category_params)).fetchall()
        categories_by_path: Dict[str, List[Dict[str, object]]] = {}
        for row in category_rows:
            categories_by_path.setdefault(row['source_path'], []).append(dict(row))
        result = []
        for book in books:
            item = dict(book)
            item['categories'] = categories_by_path.get(book['source_path'], [])
            result.append(item)
        return result

    def category_summary(self, corpus: str) -> List[Dict[str, object]]:
        with self._connect() as connection:
            query = """
                SELECT c.category, COUNT(*) AS count, AVG(c.confidence) AS avg_confidence
                FROM books b
                JOIN book_categories c ON c.book_id = b.id
                WHERE b.corpus = ?
            """
            params: List[object] = [corpus]
            for pattern in GENERATED_PATTERNS:
                query += ' AND b.source_path NOT LIKE ?'
                params.append(pattern)
            query += ' GROUP BY c.category ORDER BY count DESC, category'
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def corpus_summary(self, corpus: str) -> Dict[str, object]:
        with self._connect() as connection:
            query = """
                SELECT
                    COUNT(*) AS total_books,
                    SUM(CASE WHEN status IN ('text_extracted', 'ocr_extracted') THEN 1 ELSE 0 END) AS extracted_books,
                    SUM(CASE WHEN status = 'ocr_pending' THEN 1 ELSE 0 END) AS pending_ocr,
                    SUM(text_length) AS total_text_length
                FROM books
                WHERE corpus = ?
            """
            params: List[object] = [corpus]
            for pattern in GENERATED_PATTERNS:
                query += ' AND source_path NOT LIKE ?'
                params.append(pattern)
            row = connection.execute(query, tuple(params)).fetchone()

            ext_query = 'SELECT extension, COUNT(*) AS count FROM books WHERE corpus = ?'
            ext_params: List[object] = [corpus]
            for pattern in GENERATED_PATTERNS:
                ext_query += ' AND source_path NOT LIKE ?'
                ext_params.append(pattern)
            ext_query += ' GROUP BY extension ORDER BY count DESC, extension'
            extension_rows = connection.execute(ext_query, tuple(ext_params)).fetchall()
        total_books = int(row['total_books'] or 0)
        extracted_books = int(row['extracted_books'] or 0)
        pending_ocr = int(row['pending_ocr'] or 0)
        total_text_length = int(row['total_text_length'] or 0)
        readiness = 'empty'
        if total_books:
            readiness = 'seeded'
        if total_books >= 10 or extracted_books >= 5:
            readiness = 'research-ready'
        return {
            'total_books': total_books,
            'extracted_books': extracted_books,
            'pending_ocr': pending_ocr,
            'total_text_length': total_text_length,
            'extensions': [dict(r) for r in extension_rows],
            'readiness': readiness,
        }

    # ── Book Rules helpers ──────────────────────────────────────────────

    def save_book_rule(self, corpus: str, concept_key: str, concept_label: str,
                       calc_method: str, interpretation_rules: str,
                       source_chunks: str = "", confidence: float = 0.8,
                       cabinet_used: bool = False) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO book_rules
                    (corpus, concept_key, concept_label, calc_method,
                     interpretation_rules, source_chunks, confidence, cabinet_used,
                     created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(corpus, concept_key) DO UPDATE SET
                    calc_method=excluded.calc_method,
                    interpretation_rules=excluded.interpretation_rules,
                    confidence=excluded.confidence,
                    cabinet_used=excluded.cabinet_used,
                    updated_at=excluded.updated_at
            """, (corpus, concept_key, concept_label, calc_method,
                  interpretation_rules, source_chunks, confidence,
                  int(cabinet_used), now, now))

    def get_book_rules(self, corpus: str) -> List[Dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM book_rules WHERE corpus=? ORDER BY concept_key",
                (corpus,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_corpora_with_rules(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT corpus FROM book_rules"
            ).fetchall()
            return [r["corpus"] for r in rows]

    def set_learning_status(self, corpus: str, status: str, progress: str = "",
                            error: str = "") -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO book_learning_log (corpus, status, progress, error, started_at, finished_at, created_at)
                VALUES (?,?,?,?,?,?,?)
            """, (corpus, status, progress, error,
                  now if status == "running" else None,
                  now if status in ("done", "error") else None,
                  now))

    def get_learning_status(self, corpus: str) -> Optional[Dict[str, object]]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT * FROM book_learning_log WHERE corpus=?
                ORDER BY created_at DESC LIMIT 1
            """, (corpus,)).fetchone()
            return dict(row) if row else None

    def list_learning_log(self, corpus: str | None = None, limit: int = 50) -> List[Dict[str, object]]:
        query = 'SELECT * FROM book_learning_log'
        params: List[object] = []
        if corpus:
            query += ' WHERE corpus = ?'
            params.append(corpus)
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def prune_learning_log(self, corpus: str | None = None, keep_last: int = 20) -> int:
        keep_last = max(0, int(keep_last or 0))
        with self._connect() as conn:
            if corpus:
                ids = [
                    row["id"]
                    for row in conn.execute(
                        """
                        SELECT id
                        FROM book_learning_log
                        WHERE corpus = ?
                        ORDER BY created_at DESC, id DESC
                        LIMIT ?
                        """,
                        (corpus, keep_last),
                    ).fetchall()
                ]
                if not ids:
                    return 0
                placeholders = ",".join("?" for _ in ids)
                result = conn.execute(
                    f"DELETE FROM book_learning_log WHERE corpus = ? AND id NOT IN ({placeholders})",
                    (corpus, *ids),
                )
            else:
                ids = [
                    row["id"]
                    for row in conn.execute(
                        """
                        SELECT id
                        FROM book_learning_log
                        ORDER BY created_at DESC, id DESC
                        LIMIT ?
                        """,
                        (keep_last,),
                    ).fetchall()
                ]
                if not ids:
                    return 0
                placeholders = ",".join("?" for _ in ids)
                result = conn.execute(
                    f"DELETE FROM book_learning_log WHERE id NOT IN ({placeholders})",
                    tuple(ids),
                )
            conn.commit()
            return int(result.rowcount or 0)

    def search_memory(self, query: str, corpus: str | None = None, limit: int = 20) -> List[Dict[str, object]]:
        terms = [part.strip() for part in str(query or '').split() if part.strip()]
        if not terms:
            return []
        terms = terms[:8]
        search_limit = max(limit * 6, 24)

        def make_clause(prefix: str, fields: Sequence[str]) -> str:
            return "(" + " OR ".join(f"LOWER({prefix}{field}) LIKE ?" for field in fields) + ")"

        book_fields = ("title", "excerpt", "metadata_json", "source_path", "corpus")
        chunk_fields = ("content",)
        artifact_fields = ("content_text", "content_json")
        rule_fields = ("interpretation_rules", "concept_label", "concept_key", "calc_method")

        book_clauses = [make_clause("b.", book_fields) for _ in terms]
        chunk_clauses = [make_clause("c.", chunk_fields) + " OR LOWER(b.title) LIKE ? OR LOWER(b.source_path) LIKE ? OR LOWER(b.corpus) LIKE ?" for _ in terms]
        artifact_clauses = [make_clause("a.", artifact_fields) + " OR LOWER(b.title) LIKE ? OR LOWER(b.source_path) LIKE ? OR LOWER(b.corpus) LIKE ?" for _ in terms]
        rule_clauses = [make_clause("r.", rule_fields) for _ in terms]

        def bind_patterns(fields_per_clause: int) -> List[str]:
            params: List[str] = []
            for term in terms:
                pattern = f"%{term.lower()}%"
                params.extend([pattern] * fields_per_clause)
            return params

        rows: List[sqlite3.Row] = []
        with self._connect() as conn:
            book_sql = """
                SELECT
                    b.corpus, b.title, b.source_path, b.status, b.text_length, b.excerpt, b.updated_at,
                    b.metadata_json,
                    NULL AS chunk_text,
                    NULL AS chunk_index,
                    NULL AS artifact_type,
                    NULL AS artifact_text,
                    NULL AS artifact_json,
                    NULL AS concept_key,
                    NULL AS concept_label,
                    NULL AS interpretation_rules,
                    NULL AS confidence
                FROM books b
                WHERE {conditions}
                {corpus_filter}
                ORDER BY b.updated_at DESC, b.title ASC
                LIMIT ?
            """.format(
                conditions=" AND ".join(book_clauses),
                corpus_filter="AND b.corpus = ?" if corpus else "",
            )
            book_params: List[object] = bind_patterns(len(book_fields))
            if corpus:
                book_params.append(corpus)
            book_params.append(search_limit)
            rows.extend(conn.execute(book_sql, tuple(book_params)).fetchall())

            chunk_sql = """
                SELECT
                    b.corpus, b.title, b.source_path, b.status, b.text_length, b.excerpt, b.updated_at,
                    b.metadata_json,
                    c.content AS chunk_text,
                    c.chunk_index,
                    NULL AS artifact_type,
                    NULL AS artifact_text,
                    NULL AS artifact_json,
                    NULL AS concept_key,
                    NULL AS concept_label,
                    NULL AS interpretation_rules,
                    NULL AS confidence
                FROM book_chunks c
                JOIN books b ON b.id = c.book_id
                WHERE {conditions}
                {corpus_filter}
                ORDER BY b.updated_at DESC, b.title ASC, c.chunk_index ASC
                LIMIT ?
            """.format(
                conditions=" AND ".join(chunk_clauses),
                corpus_filter="AND b.corpus = ?" if corpus else "",
            )
            chunk_params: List[object] = []
            for term in terms:
                pattern = f"%{term.lower()}%"
                chunk_params.extend([pattern] * len(chunk_fields))
                chunk_params.extend([pattern, pattern, pattern])
            if corpus:
                chunk_params.append(corpus)
            chunk_params.append(search_limit)
            rows.extend(conn.execute(chunk_sql, tuple(chunk_params)).fetchall())

            artifact_sql = """
                SELECT
                    b.corpus, b.title, b.source_path, b.status, b.text_length, b.excerpt, b.updated_at,
                    b.metadata_json,
                    NULL AS chunk_text,
                    NULL AS chunk_index,
                    a.artifact_type,
                    a.content_text AS artifact_text,
                    a.content_json AS artifact_json,
                    NULL AS concept_key,
                    NULL AS concept_label,
                    NULL AS interpretation_rules,
                    NULL AS confidence
                FROM book_artifacts a
                JOIN books b ON b.id = a.book_id
                WHERE {conditions}
                {corpus_filter}
                ORDER BY b.updated_at DESC, b.title ASC, a.artifact_type ASC
                LIMIT ?
            """.format(
                conditions=" AND ".join(artifact_clauses),
                corpus_filter="AND b.corpus = ?" if corpus else "",
            )
            artifact_params: List[object] = []
            for term in terms:
                pattern = f"%{term.lower()}%"
                artifact_params.extend([pattern] * len(artifact_fields))
                artifact_params.extend([pattern, pattern, pattern])
            if corpus:
                artifact_params.append(corpus)
            artifact_params.append(search_limit)
            rows.extend(conn.execute(artifact_sql, tuple(artifact_params)).fetchall())

            rule_sql = """
                SELECT
                    r.corpus,
                    COALESCE(b.title, r.concept_label) AS title,
                    COALESCE(b.source_path, 'interpretations/' || r.corpus || '/' || r.concept_key) AS source_path,
                    COALESCE(b.status, 'learned') AS status,
                    COALESCE(b.text_length, LENGTH(COALESCE(r.interpretation_rules, ''))) AS text_length,
                    COALESCE(b.excerpt, r.interpretation_rules) AS excerpt,
                    COALESCE(b.updated_at, r.updated_at) AS updated_at,
                    COALESCE(b.metadata_json, '{{}}') AS metadata_json,
                    NULL AS chunk_text,
                    NULL AS chunk_index,
                    NULL AS artifact_type,
                    NULL AS artifact_text,
                    NULL AS artifact_json,
                    r.concept_key,
                    r.concept_label,
                    r.interpretation_rules,
                    r.confidence
                FROM book_rules r
                LEFT JOIN books b
                    ON b.corpus = r.corpus
                    AND b.source_path NOT LIKE '%_books.md'
                WHERE {conditions}
                {corpus_filter}
                ORDER BY r.updated_at DESC, r.concept_key ASC
                LIMIT ?
            """.format(
                conditions=" AND ".join(rule_clauses),
                corpus_filter="AND r.corpus = ?" if corpus else "",
            )
            rule_params: List[object] = bind_patterns(len(rule_fields))
            if corpus:
                rule_params.append(corpus)
            rule_params.append(search_limit)
            rows.extend(conn.execute(rule_sql, tuple(rule_params)).fetchall())

        deduped: List[Dict[str, object]] = []
        seen: set[str] = set()
        for row in rows:
            item = dict(row)
            key = "|".join([
                str(item.get("corpus") or ""),
                str(item.get("title") or ""),
                str(item.get("source_path") or ""),
                str(item.get("concept_key") or ""),
                str(item.get("artifact_type") or ""),
                str(item.get("chunk_index") or ""),
                str(item.get("chunk_text") or "")[:120],
            ])
            if key in seen:
                continue
            seen.add(key)
            haystack = " ".join([
                str(item.get("corpus") or ""),
                str(item.get("title") or ""),
                str(item.get("source_path") or ""),
                str(item.get("status") or ""),
                str(item.get("excerpt") or ""),
                str(item.get("chunk_text") or ""),
                str(item.get("artifact_text") or ""),
                str(item.get("artifact_json") or ""),
                str(item.get("interpretation_rules") or ""),
                str(item.get("concept_label") or ""),
                str(item.get("concept_key") or ""),
                str(item.get("metadata_json") or ""),
            ]).lower()
            score = 0
            for term in terms:
                term_lower = term.lower()
                if term_lower in str(item.get("title") or "").lower():
                    score += 6
                if term_lower in str(item.get("source_path") or "").lower():
                    score += 4
                if term_lower in str(item.get("corpus") or "").lower():
                    score += 3
                if term_lower in haystack:
                    score += 1
            item["_score"] = score + min(4.0, (int(item.get("text_length") or 0) / 5000.0))
            deduped.append(item)
        deduped.sort(key=lambda row: (
            -float(row.pop("_score", 0) or 0),
            -int(row.get("text_length") or 0),
            str(row.get("title") or "").lower(),
            str(row.get("source_path") or "").lower(),
        ))
        return deduped[:limit]



