"""Rule-based mapper for future astrology corpus ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from .astrology_blueprint import ASTROLOGY_TAXONOMY
from .knowledge_store import KnowledgeStore


CATEGORY_LABELS = {item['key']: item['label'] for item in ASTROLOGY_TAXONOMY}

RULES = [
    {
        'category': 'signs_elements_modalities',
        'keywords': ['sign', 'zodiac', 'aries', 'taurus', 'gemini', 'cancer', 'leo', 'virgo', 'libra', 'scorpio', 'sagittarius', 'capricorn', 'aquarius', 'pisces', 'element', 'modality'],
    },
    {
        'category': 'planets_luminaries',
        'keywords': ['sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune', 'pluto', 'chiron', 'node'],
    },
    {
        'category': 'houses_axes',
        'keywords': ['house', 'houses', 'ascendant', 'rising', 'midheaven', 'mc', 'ic', 'descendant'],
    },
    {
        'category': 'aspects_patterns',
        'keywords': ['aspect', 'square', 'opposition', 'conjunction', 'trine', 'sextile', 'yod', 't-square'],
    },
    {
        'category': 'chart_synthesis',
        'keywords': ['chart', 'synthesis', 'interpretation', 'natal', 'birth chart', 'dominant'],
    },
    {
        'category': 'relationship_work',
        'keywords': ['synastry', 'relationship', 'composite', 'compatibility', 'venus', 'mars'],
    },
    {
        'category': 'timing_prediction',
        'keywords': ['transit', 'progression', 'solar return', 'forecast', 'prediction', 'timing'],
    },
    {
        'category': 'spiritual_karmic',
        'keywords': ['karmic', 'karma', 'soul', 'evolutionary', 'node', 'saturn return', 'destiny'],
    },
]


class AstrologyCorpusMapper:
    def __init__(self, store: KnowledgeStore | None = None):
        self.store = store or KnowledgeStore()

    def classify_corpus(self, corpus: str = 'astrology') -> Dict[str, object]:
        books = self.store.list_books(corpus=corpus)
        classified = 0
        for book in books:
            categories = self._classify_book(book)
            self.store.replace_categories(int(book['id']), categories)
            if categories:
                classified += 1
        return {
            'corpus': corpus,
            'books': len(books),
            'classified': classified,
            'category_summary': self.store.category_summary(corpus),
        }

    def export_markdown_map(self, corpus: str, output_path: str) -> str:
        books = self.store.list_books_with_categories(corpus)
        summary = self.store.category_summary(corpus)
        lines: List[str] = [f'# {corpus.title()} Category Map', '']
        lines.append('## Summary')
        if summary:
            for item in summary:
                label = CATEGORY_LABELS.get(str(item['category']), str(item['category']))
                lines.append(f"- {label}: {item['count']} קבצים")
        else:
            lines.append('- אין קטגוריות עדיין')
        lines.append('')
        lines.append('## Books')
        lines.append('')
        for book in books:
            lines.append(f"### {book['title']}")
            lines.append(f"- נתיב: {book['source_path']}")
            lines.append(f"- סטטוס: {book['status']}")
            if book['categories']:
                labels = []
                for category in book['categories']:
                    label = CATEGORY_LABELS.get(str(category['category']), str(category['category']))
                    labels.append(f"{label} ({round(float(category['confidence']), 2)})")
                lines.append(f"- קטגוריות: {', '.join(labels)}")
            else:
                lines.append('- קטגוריות: לא סווג')
            lines.append('')
        content = '\n'.join(lines)
        Path(output_path).write_text(content, encoding='utf-8')
        return content

    def _classify_book(self, book: Dict[str, object]) -> List[Dict[str, object]]:
        haystack = ' '.join(
            [
                str(book.get('title') or '').lower(),
                str(book.get('excerpt') or '').lower(),
                str(book.get('source_path') or '').lower(),
            ]
        )
        matches: List[Dict[str, object]] = []
        for rule in RULES:
            hits = count_hits(haystack, rule['keywords'])
            if hits <= 0:
                continue
            confidence = min(0.34 + (min(hits, 4) * 0.14), 0.9)
            matches.append({'category': rule['category'], 'confidence': confidence, 'source': 'rule'})
        matches = dedupe_matches(matches)
        matches.sort(key=lambda item: (-float(item['confidence']), str(item['category'])))
        return matches[:3]


def count_hits(haystack: str, keywords: Iterable[str]) -> int:
    return sum(1 for keyword in keywords if keyword and keyword in haystack)


def dedupe_matches(matches: List[Dict[str, object]]) -> List[Dict[str, object]]:
    best: Dict[str, Dict[str, object]] = {}
    for match in matches:
        category = str(match['category'])
        if category not in best or float(match['confidence']) > float(best[category]['confidence']):
            best[category] = match
    return list(best.values())
