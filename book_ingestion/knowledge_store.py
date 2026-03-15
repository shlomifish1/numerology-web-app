"""SQLite persistence for ingested book metadata, chunks, and chapter categories."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


GENERATED_PATTERNS = ('%_books.md', '%_category_map.md', '%_ocr_queue.md', '%_runtime.md', '%_seed_plan.md', '%_taxonomy.md', '%_intake.md')


class KnowledgeStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or Path(__file__).with_name('numerology_books.db'))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
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
                """
            )
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



