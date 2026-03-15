"""Corpus scanner and catalog generator for research books."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .knowledge_store import KnowledgeStore
from .ocr_engine import OCREngine


class BookProcessor:
    def __init__(self, store: Optional[KnowledgeStore] = None, engine: Optional[OCREngine] = None):
        self.store = store or KnowledgeStore()
        self.engine = engine or OCREngine()

    def add_book(
        self,
        title: str,
        author: str,
        source_path: str,
        corpus: str,
        method: Optional[str] = None,
    ) -> Dict[str, object]:
        inspection = self.engine.inspect(source_path)
        text = inspection.get('text', '') or ''
        metadata = dict(inspection.get('metadata', {}))
        metadata['method'] = method
        record = {
            'corpus': corpus,
            'title': title,
            'author': author,
            'source_path': str(Path(source_path)),
            'extension': Path(source_path).suffix.lower(),
            'language_hint': self._language_hint(title),
            'status': inspection.get('status', 'metadata_only'),
            'text_length': len(text),
            'excerpt': text[:500] if text else '',
            'metadata_json': json.dumps(metadata, ensure_ascii=False),
        }
        book_id = self.store.upsert_book(record)
        if text:
            self.store.replace_chunks(book_id, self._chunk_text(text))
        return {'book_id': book_id, 'record': record, 'metadata': metadata}

    def index_corpus(self, corpus: str, folder_path: str, method: Optional[str] = None) -> List[Dict[str, object]]:
        folder = Path(folder_path)
        results = []
        valid_sources: List[str] = []
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or self._should_skip(path):
                continue
            valid_sources.append(str(path))
            results.append(
                self.add_book(
                    title=path.stem,
                    author='',
                    source_path=str(path),
                    corpus=corpus,
                    method=method,
                )
            )
        self.store.sync_corpus_sources(corpus, valid_sources)
        self.store.purge_generated_records(corpus)
        return results

    def export_markdown_catalog(self, corpus: str, output_path: str) -> str:
        books = self.store.list_books(corpus=corpus)
        lines = [f'# {corpus.title()} Catalog', '', f'סה"כ ספרים/קבצים: {len(books)}', '']
        for book in books:
            lines.append(f"## {book['title']}")
            lines.append(f"- סטטוס: {book['status']}")
            lines.append(f"- סוג קובץ: {book['extension'] or '-'}")
            lines.append(f"- שפה משוערת: {book['language_hint'] or '-'}")
            lines.append(f"- אורך טקסט: {book['text_length']}")
            lines.append(f"- נתיב: {book['source_path']}")
            if book.get('excerpt'):
                excerpt = str(book['excerpt']).replace('\n', ' ').strip()
                lines.append(f"- excerpt: {excerpt[:220]}")
            lines.append('')
        content = '\n'.join(lines)
        Path(output_path).write_text(content, encoding='utf-8')
        return content

    def _chunk_text(self, text: str, chunk_size: int = 1800) -> Iterable[str]:
        clean = ' '.join(text.split())
        if not clean:
            return []
        return [clean[i:i + chunk_size] for i in range(0, len(clean), chunk_size)]

    def _language_hint(self, title: str) -> str:
        has_hebrew = any('\u0590' <= ch <= '\u05FF' for ch in title)
        has_latin = any(('A' <= ch <= 'Z') or ('a' <= ch <= 'z') for ch in title)
        if has_hebrew and has_latin:
            return 'HE+EN'
        if has_hebrew:
            return 'HE'
        if has_latin:
            return 'EN'
        return 'unknown'

    def _should_skip(self, path: Path) -> bool:
        name = path.name.lower()
        return name.endswith('_books.md') or name.endswith('_category_map.md') or name.endswith('_ocr_queue.md') or name.endswith('_runtime.md') or name.endswith('_seed_plan.md') or name.endswith('_taxonomy.md') or name.endswith('_intake.md')



