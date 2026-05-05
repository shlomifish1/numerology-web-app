"""Rule-based chapter mapper for the Green corpus."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from .knowledge_store import KnowledgeStore


CATEGORY_LABELS = {
    'name_gematria': 'שם וגימטריה',
    'birthdate_core': 'ליבה מתאריך לידה',
    'character_traits': 'קווי אופי',
    'career': 'מקצוע וייעוד',
    'relationships': 'יחסים והתאמות',
    'annual_cycles': 'מחזורים שנתיים ומעברים',
    'life_cycles': 'מחזורי חיים',
    'engineering': 'נומרולוגיה הנדסית',
    'master_numbers': 'מספרי מאסטר ומספרים מתקדמים',
    'number_meanings': 'פירושי מספרים',
    'symbols_and_colors': 'צבעים, אבנים וסמלים',
    'missing_numbers': 'מספרים חסרים/עודפים/מיטיבים',
    'case_studies': 'מקרי בדיקה',
    'value_messages': 'מסרים וערכים',
}

RULES = [
    {
        'category': 'case_studies',
        'title_keywords': ['מקרה בדיקה'],
        'text_keywords': [],
        'exclusive': True,
    },
    {
        'category': 'engineering',
        'title_keywords': ['נומרולוגיה הנדסית'],
        'text_keywords': [],
        'exclusive': True,
    },
    {
        'category': 'master_numbers',
        'title_keywords': ['מספרי מאסטר', 'מספרים מקודמים', 'מספרים זמניים'],
        'text_keywords': ['שליחות', 'מאסטר'],
        'exclusive': True,
    },
    {
        'category': 'relationships',
        'title_keywords': ['התאמת בני זוג', 'קשרים בין ילדים והורים'],
        'text_keywords': [],
        'exclusive': True,
    },
    {
        'category': 'career',
        'title_keywords': ['בחירת מקצוע'],
        'text_keywords': ['קריירה', 'מקצוע'],
        'exclusive': True,
    },
    {
        'category': 'character_traits',
        'title_keywords': ['קווי אופי', 'האני האוטומטי', 'האני ההגיוני'],
        'text_keywords': ['מודעות עצמית', 'אופי'],
        'exclusive': True,
    },
    {
        'category': 'missing_numbers',
        'title_keywords': ['מספרים חסרים', 'עודפים', 'מיטיבים'],
        'text_keywords': ['מספרים חסרים', 'מיטיבים', 'עודפים'],
        'exclusive': True,
    },
    {
        'category': 'value_messages',
        'title_keywords': ['המסרים', 'ערכיים'],
        'text_keywords': ['בראשית', 'חוקי היקום'],
        'exclusive': True,
    },
    {
        'category': 'symbols_and_colors',
        'title_keywords': ['צבעים', 'אבנים'],
        'text_keywords': ['צבעים', 'אבנים'],
        'exclusive': True,
    },
    {
        'category': 'number_meanings',
        'title_keywords': ['ביטוי הנשמה', 'התנהגות מוחצנת', 'שביל הגורל', 'תרגום כללי של המספרים', 'פירושי המספרים'],
        'text_keywords': ['ביטוי נשמה', 'שביל הגורל', 'התנהגות מוחצנת'],
        'exclusive': True,
    },
    {
        'category': 'name_gematria',
        'title_keywords': ['המרת אותיות', 'שם לידה', 'נגזרות משם', 'שינויי שם', 'שם חיבה', 'האות הראשונה בשם'],
        'text_keywords': ['גימטריה', 'שם לידה', 'אות ראשונה בשם'],
        'exclusive': False,
    },
    {
        'category': 'birthdate_core',
        'title_keywords': ['תאריכי לידה', 'מפת לידה', 'שיעורי חיים', 'מספרים מזהים'],
        'text_keywords': ['תאריך לידה', 'שיעור חיים', 'לידה אזרחי', 'לידה עברי'],
        'exclusive': False,
    },
    {
        'category': 'annual_cycles',
        'title_keywords': ['טווח שנתי', 'חלוקות מישנה', 'השפעות תקופתיות', 'עונות חיים', 'מעברים', 'אותיות בהשפעה תקופתית'],
        'text_keywords': ['שנה אישית', 'מעברים', 'רבעונים'],
        'exclusive': False,
    },
    {
        'category': 'life_cycles',
        'title_keywords': ['מחזוריות חיים', 'מחזורי חיים', 'להיוולד מחדש'],
        'text_keywords': ['מחזורי חיים', 'גלגול'],
        'exclusive': False,
    },
]

PAIRINGS = {
    'annual_cycles': {'name_gematria': ['אותיות בהשפעה תקופתית', 'משמעות האותיות במעברים']},
    'birthdate_core': {'missing_numbers': ['חקירה מעמידה של מפת לידה', 'חקירה מעמיקה של מפת הלידה']},
}


class GreenChapterMapper:
    def __init__(self, store: KnowledgeStore | None = None):
        self.store = store or KnowledgeStore()

    def classify_corpus(self, corpus: str = 'green') -> Dict[str, object]:
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
        title = str(book.get('title') or '')
        excerpt = str(book.get('excerpt') or '')
        source_path = str(book.get('source_path') or '')
        title_haystack = f"{title} {source_path}"
        text_haystack = excerpt

        exclusive_matches = self._exclusive_matches(title_haystack, text_haystack)
        if exclusive_matches:
            return exclusive_matches

        matches: List[Dict[str, object]] = []
        for rule in RULES:
            if rule.get('exclusive'):
                continue
            title_hits = count_hits(title_haystack, rule['title_keywords'])
            text_hits = count_hits(text_haystack, rule['text_keywords'])
            if title_hits == 0 and text_hits == 0:
                continue
            confidence = min(0.42 + (title_hits * 0.25) + (min(text_hits, 2) * 0.12), 0.97)
            matches.append({'category': rule['category'], 'confidence': confidence, 'source': 'rule'})

        matches.extend(self._paired_matches(title_haystack))
        matches = dedupe_matches(matches)
        matches.sort(key=lambda item: (-item['confidence'], item['category']))

        if not matches:
            return []
        return matches[:3]

    def _exclusive_matches(self, title_haystack: str, text_haystack: str) -> List[Dict[str, object]]:
        for rule in RULES:
            if not rule.get('exclusive'):
                continue
            title_hits = count_hits(title_haystack, rule['title_keywords'])
            text_hits = count_hits(text_haystack, rule['text_keywords'])
            if title_hits > 0:
                return [{'category': rule['category'], 'confidence': min(0.78 + title_hits * 0.08, 0.99), 'source': 'title_rule'}]
            if text_hits >= 2:
                return [{'category': rule['category'], 'confidence': min(0.58 + text_hits * 0.1, 0.88), 'source': 'text_rule'}]
        return []

    def _paired_matches(self, title_haystack: str) -> List[Dict[str, object]]:
        matches: List[Dict[str, object]] = []
        for base_category, extras in PAIRINGS.items():
            for extra_category, phrases in extras.items():
                if any(phrase in title_haystack for phrase in phrases):
                    matches.append({'category': base_category, 'confidence': 0.76, 'source': 'pairing'})
                    matches.append({'category': extra_category, 'confidence': 0.72, 'source': 'pairing'})
        return matches


def count_hits(haystack: str, keywords: Iterable[str]) -> int:
    return sum(1 for keyword in keywords if keyword and keyword in haystack)


def dedupe_matches(matches: List[Dict[str, object]]) -> List[Dict[str, object]]:
    best: Dict[str, Dict[str, object]] = {}
    for match in matches:
        category = str(match['category'])
        if category not in best or float(match['confidence']) > float(best[category]['confidence']):
            best[category] = match
    return list(best.values())
