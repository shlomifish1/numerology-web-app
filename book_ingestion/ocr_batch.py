"""Batch utilities for refreshing pending OCR work and exporting runtime status."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .book_processor import BookProcessor
from .knowledge_store import KnowledgeStore
from .ocr_engine import OCREngine
from .ocr_planner import OCRPlanner


class PendingOCRRunner:
    def __init__(
        self,
        store: Optional[KnowledgeStore] = None,
        engine: Optional[OCREngine] = None,
        processor: Optional[BookProcessor] = None,
    ):
        self.store = store or KnowledgeStore()
        self.engine = engine or OCREngine()
        self.processor = processor or BookProcessor(store=self.store, engine=self.engine)
        self.planner = OCRPlanner(self.store)

    def refresh_pending(self, corpus: str, method: Optional[str] = None, limit: int = 10) -> Dict[str, object]:
        queue = self.planner.build_queue(corpus, limit=limit)
        books_by_path = {str(book['source_path']): book for book in self.store.list_books(corpus=corpus)}
        processed: List[Dict[str, object]] = []
        changed = 0
        for item in queue:
            source_path = str(item['source_path'])
            existing = books_by_path.get(source_path)
            if not existing:
                continue
            before_status = str(existing.get('status') or '')
            result = self.processor.add_book(
                title=str(existing.get('title') or Path(source_path).stem),
                author=str(existing.get('author') or ''),
                source_path=source_path,
                corpus=corpus,
                method=method,
            )
            after_status = str(result['record']['status'])
            if after_status != before_status:
                changed += 1
            processed.append(
                {
                    'title': str(existing.get('title') or Path(source_path).stem),
                    'source_path': source_path,
                    'before_status': before_status,
                    'after_status': after_status,
                    'text_length': int(result['record']['text_length'] or 0),
                }
            )
        return {
            'corpus': corpus,
            'requested': len(queue),
            'processed': len(processed),
            'changed': changed,
            'runtime': self.engine.runtime_summary(),
            'items': processed,
        }

    def export_runtime_report(self, corpus: str, output_path: str, limit: int = 10) -> str:
        runtime = self.engine.runtime_summary()
        queue = self.planner.build_queue(corpus, limit=limit)
        summary = self.store.corpus_summary(corpus)
        lines = [f'# {corpus.title()} OCR Runtime', '']
        lines.append(f"- ready_for_full_ocr: {runtime['ready_for_full_ocr']}")
        lines.append(f"- ready_for_text_extraction: {runtime['ready_for_text_extraction']}")
        lines.append(f"- recommended_action: {runtime['recommended_action']}")
        lines.append(f"- total_books: {summary['total_books']}")
        lines.append(f"- extracted_books: {summary['extracted_books']}")
        lines.append(f"- pending_ocr: {summary['pending_ocr']}")
        lines.append('')
        lines.append('## Capabilities')
        lines.append('')
        for key, value in runtime['capabilities'].items():
            lines.append(f'- {key}: {value}')
        lines.append('')
        lines.append('## Pending Queue')
        lines.append('')
        if not queue:
            lines.append('אין כרגע קבצים ממתינים ל-OCR.')
        else:
            for item in queue:
                lines.append(f"- {item['rank']}. {item['title']} | {item['status']} | score={item['score']}")
        content = '\n'.join(lines)
        Path(output_path).write_text(content, encoding='utf-8')
        return content
