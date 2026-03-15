"""Prioritize OCR work for corpora with many pending files."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .knowledge_store import KnowledgeStore


KEYWORD_WEIGHTS = {
    'intuition': 4,
    'psychic': 5,
    'third eye': 5,
    'pineal': 4,
    'energy': 4,
    'awakening': 4,
    'awaken': 4,
    'spirit': 3,
    'light': 3,
    'god': 3,
    'tao': 3,
    'remote viewing': 5,
    'bashar': 4,
    'pleadian': 4,
    'pleiadian': 4,
    'consciousness': 4,
    'healing': 4,
    'silva': 3,
}

EXTENSION_BASE = {
    '.pdf': 5,
    '.epub': 4,
    '.html': 2,
    '.htm': 2,
    '.mp3': 0,
}

STATUS_BONUS = {
    'ocr_pending': 4,
    'metadata_only': 2,
}

ELIGIBLE_STATUSES = {'ocr_pending', 'metadata_only'}


class OCRPlanner:
    def __init__(self, store: KnowledgeStore | None = None):
        self.store = store or KnowledgeStore()

    def build_queue(self, corpus: str, limit: int = 15) -> List[Dict[str, object]]:
        books = self.store.list_books(corpus=corpus)
        candidates = []
        for book in books:
            if str(book.get('status') or '') not in ELIGIBLE_STATUSES:
                continue
            item = self._score_book(book)
            if item['score'] <= 0:
                continue
            candidates.append(item)
        candidates.sort(key=lambda item: (-int(item['score']), str(item['title']).lower()))
        for index, item in enumerate(candidates, start=1):
            item['rank'] = index
        return candidates[:limit]

    def export_markdown_queue(self, corpus: str, output_path: str, limit: int = 15) -> str:
        queue = self.build_queue(corpus, limit=limit)
        lines = [f'# {corpus.title()} OCR Queue', '']
        if not queue:
            lines.append('אין כרגע קבצים שמחכים ל-OCR בעדיפות חיובית.')
        else:
            lines.append(f'סה"כ מועמדים מוצגים: {len(queue)}')
            lines.append('')
            for item in queue:
                lines.append(f"## {item['rank']}. {item['title']}")
                lines.append(f"- ציון: {item['score']}")
                lines.append(f"- סטטוס: {item['status']}")
                lines.append(f"- סוג קובץ: {item['extension']}")
                lines.append(f"- סיבות: {', '.join(item['reasons']) if item['reasons'] else '-'}")
                lines.append(f"- נתיב: {item['source_path']}")
                lines.append('')
        Path(output_path).write_text('\n'.join(lines), encoding='utf-8')
        return '\n'.join(lines)

    def _score_book(self, book: Dict[str, object]) -> Dict[str, object]:
        title = str(book.get('title') or '')
        lowered = title.lower()
        extension = str(book.get('extension') or '').lower()
        status = str(book.get('status') or '')
        score = EXTENSION_BASE.get(extension, 1) + STATUS_BONUS.get(status, 0)
        reasons: List[str] = []
        if extension in EXTENSION_BASE:
            reasons.append(f"format={extension}")
        if status in STATUS_BONUS:
            reasons.append(f"status={status}")
        for keyword, weight in KEYWORD_WEIGHTS.items():
            if keyword in lowered:
                score += weight
                reasons.append(keyword)
        if 'pdfdrive' in lowered:
            score += 1
            reasons.append('pdfdrive')
        if 'audio' in lowered or extension == '.mp3':
            score -= 5
            reasons.append('audio_low_priority')
        return {
            'title': title,
            'source_path': str(book.get('source_path') or ''),
            'extension': extension or '-',
            'status': status or '-',
            'score': score,
            'reasons': reasons,
        }
