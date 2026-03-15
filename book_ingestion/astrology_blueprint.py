"""Blueprint and taxonomy exports for the astrology corpus."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List


ASTROLOGY_TAXONOMY = [
    {
        'key': 'signs_elements_modalities',
        'label': 'מזלות, יסודות ואיכויות',
        'topics': ['12 המזלות', 'יסודות אש/אדמה/אוויר/מים', 'קרדינלי/קבוע/משתנה'],
    },
    {
        'key': 'planets_luminaries',
        'label': 'כוכבים ומאורות',
        'topics': ['שמש וירח', 'מרקורי עד פלוטו', 'כירון והצומת הצפוני'],
    },
    {
        'key': 'houses_axes',
        'label': 'בתים וצירים',
        'topics': ['12 הבתים', 'ASC/DSC', 'MC/IC'],
    },
    {
        'key': 'aspects_patterns',
        'label': 'זוויות ותבניות',
        'topics': ['צמידות, ריבוע, אופוזיציה, טריין, סקסטיל', 'T-square', 'Grand Trine', 'Yod'],
    },
    {
        'key': 'chart_synthesis',
        'label': 'סינתזת מפה',
        'topics': ['שליט מפה', 'דומיננטות', 'איזון יסודות', 'קריאת מפה שלמה'],
    },
    {
        'key': 'relationship_work',
        'label': 'סינאסטרי והתאמות',
        'topics': ['סינאסטרי', 'Composite', 'ונוס/מרס', 'ירח בקשר'],
    },
    {
        'key': 'timing_prediction',
        'label': 'זמנים וחיזוי',
        'topics': ['טרנזיטים', 'פרוגרסיות', 'Solar Return', 'לוחות זמנים'],
    },
    {
        'key': 'spiritual_karmic',
        'label': 'אסטרולוגיה רוחנית/קרמתית',
        'topics': ['צמתים', 'שבתאי', 'קרמה וייעוד', 'אסטרולוגיה אבולוציונית'],
    },
]

SEED_BOOKS = [
    {
        'title': 'The Only Astrology Book You Will Ever Need',
        'author': 'Joanna Martine Woolfolk',
        'reason': 'בסיס רחב למזלות, כוכבים, בתים והיבטים.',
    },
    {
        'title': 'Parker\'s Astrology',
        'author': 'Julia and Derek Parker',
        'reason': 'ספר יסוד שיטתי למפה, היבטים וקריאת chart.',
    },
    {
        'title': 'The Inner Sky',
        'author': 'Steven Forrest',
        'reason': 'גישה פרשנית נגישה עם דגש על סינתזה.',
    },
    {
        'title': 'Aspects in Astrology',
        'author': 'Sue Tompkins',
        'reason': 'עוגן מקצועי להבנת היבטים ותבניות.',
    },
    {
        'title': 'Planets in Transit',
        'author': 'Robert Hand',
        'reason': 'ספר בסיס מצוין לעבודה עם טרנזיטים ותזמון.',
    },
    {
        'title': 'Astrology for the Soul',
        'author': 'Jan Spiller',
        'reason': 'רלוונטי לשכבה רוחנית וקרמתית דרך הצמתים.',
    },
]


class AstrologyBlueprint:
    def summary(self) -> Dict[str, object]:
        return {
            'taxonomy_count': len(ASTROLOGY_TAXONOMY),
            'taxonomy_labels': [item['label'] for item in ASTROLOGY_TAXONOMY],
            'seed_books_count': len(SEED_BOOKS),
            'seed_book_titles': [item['title'] for item in SEED_BOOKS],
            'next_step': 'להכניס 3-6 ספרי יסוד לפי ה-seed plan ואז למפות אותם לטקסונומיה.',
        }

    def export_taxonomy(self, output_path: str) -> str:
        lines: List[str] = ['# Astrology Taxonomy', '']
        for section in ASTROLOGY_TAXONOMY:
            lines.append(f"## {section['label']}")
            for topic in section['topics']:
                lines.append(f'- {topic}')
            lines.append('')
        content = '\n'.join(lines)
        Path(output_path).write_text(content, encoding='utf-8')
        return content

    def export_seed_plan(self, output_path: str) -> str:
        lines: List[str] = ['# Astrology Seed Plan', '', f"סה\"כ ספרי יסוד מומלצים: {len(SEED_BOOKS)}", '']
        for index, book in enumerate(SEED_BOOKS, start=1):
            lines.append(f"## {index}. {book['title']}")
            lines.append(f"- מחבר: {book['author']}")
            lines.append(f"- למה: {book['reason']}")
            lines.append('')
        content = '\n'.join(lines)
        Path(output_path).write_text(content, encoding='utf-8')
        return content
