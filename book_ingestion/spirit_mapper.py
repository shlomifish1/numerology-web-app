"""Rule-based thematic mapper for the spirit corpus."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from .knowledge_store import KnowledgeStore


CATEGORY_LABELS = {
    'intuition_psychic': 'אינטואיציה ויכולות תפיסה',
    'consciousness_awakening': 'תודעה והתעוררות',
    'healing_energy': 'ריפוי ואנרגיה',
    'manifestation_abundance': 'שפע, השפעה ובריאה',
    'astral_projection': 'אסטרל, חלימה ויציאה מהגוף',
    'channeling_guides': 'תקשור ומדריכים רוחניים',
    'meditation_presence': 'מדיטציה ונוכחות',
}

RULES = [
    {
        'category': 'astral_projection',
        'title_keywords': ['astral', 'out of body', 'obe', 'lucid', 'dream'],
        'text_keywords': ['astral', 'out of body', 'lucid dream', 'projection'],
    },
    {
        'category': 'intuition_psychic',
        'title_keywords': ['psychic', 'intuition', 'third eye', 'pineal', 'remote viewing', 'sixth sense'],
        'text_keywords': ['psychic', 'intuition', 'third eye', 'pineal', 'remote viewing', 'extrasensory'],
    },
    {
        'category': 'channeling_guides',
        'title_keywords': ['bashar', 'abraham', 'pleiadian', 'pleadian', 'seth', 'channel'],
        'text_keywords': ['bashar', 'abraham', 'pleiadian', 'pleadian', 'channeling', 'guides'],
    },
    {
        'category': 'consciousness_awakening',
        'title_keywords': ['awakening', 'consciousness', 'enlightenment', 'i am', 'tao', 'now'],
        'text_keywords': ['awakening', 'consciousness', 'enlightenment', 'presence', 'oneness', 'nondual'],
    },
    {
        'category': 'healing_energy',
        'title_keywords': ['healing', 'energy', 'light', 'medicine', 'body'],
        'text_keywords': ['healing', 'energy', 'light body', 'vibration', 'medicine'],
    },
    {
        'category': 'manifestation_abundance',
        'title_keywords': ['rich', 'abundance', 'success', 'power', 'ask and it is given', 'influence'],
        'text_keywords': ['abundance', 'rich', 'success', 'manifest', 'law of attraction', 'prosperity'],
    },
    {
        'category': 'meditation_presence',
        'title_keywords': ['meditation', 'presence', 'mindfulness', 'silence'],
        'text_keywords': ['meditation', 'presence', 'mindfulness', 'stillness', 'breath'],
    },
]


class SpiritCorpusMapper:
    def __init__(self, store: KnowledgeStore | None = None):
        self.store = store or KnowledgeStore()

    def classify_corpus(self, corpus: str = 'spirit') -> Dict[str, object]:
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
        title = str(book.get('title') or '').lower()
        excerpt = str(book.get('excerpt') or '').lower()
        source_path = str(book.get('source_path') or '').lower()
        haystack_title = f'{title} {source_path}'
        haystack_text = excerpt
        matches: List[Dict[str, object]] = []
        for rule in RULES:
            title_hits = count_hits(haystack_title, rule['title_keywords'])
            text_hits = count_hits(haystack_text, rule['text_keywords'])
            if title_hits == 0 and text_hits == 0:
                continue
            confidence = min(0.34 + (title_hits * 0.22) + (min(text_hits, 3) * 0.12), 0.96)
            source = 'title_rule' if title_hits >= text_hits else 'text_rule'
            matches.append({'category': rule['category'], 'confidence': confidence, 'source': source})
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
