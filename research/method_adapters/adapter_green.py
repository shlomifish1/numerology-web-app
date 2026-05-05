"""Adapter for the full gematria / Green research method."""

from __future__ import annotations

from typing import Dict, Optional

from book_ingestion.knowledge_store import KnowledgeStore
from name_gematria_green import NamesDataGreen
from research.method_adapters.corpus_tools import extensions_summary, readiness_label

from .adapter_base import MethodAdapter


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


class GreenMethodAdapter(MethodAdapter):
    def analyze(
        self,
        *,
        first_name: str,
        last_name: str,
        day: int,
        month: int,
        year: int,
        gender: str,
        hebrew_birthdate: Optional[Dict[str, int]] = None,
    ) -> Dict[str, object]:
        del gender
        green = NamesDataGreen()
        analysis = green.analyze_full_name(
            first_name=first_name,
            last_name=last_name,
            day=day,
            month=month,
            year=year,
            hebrew_birthdate=hebrew_birthdate,
        )

        store = KnowledgeStore()
        corpus_summary = store.corpus_summary('green')
        category_summary = store.category_summary('green')
        top_categories = ', '.join(CATEGORY_LABELS.get(str(item['category']), str(item['category'])) for item in category_summary[:3]) or '-'
        mapped_books = sum(int(item['count']) for item in category_summary[:3]) if category_summary else 0

        name_analysis = analysis['name_analysis']['as_vowel']
        missing_info = analysis['missing_info']
        birthdate_analysis = analysis['birthdate_analysis'] or {}

        def _format_numbers(values):
            return ', '.join(str(value) for value in values) if values else '-'

        next_step = 'להריץ OCR על קבצי PDF חסרים או להמשיך סיווג פרקים.'
        if corpus_summary['total_books'] and corpus_summary['extracted_books'] == corpus_summary['total_books']:
            next_step = 'להעמיק במיפוי פרקים לקטגוריות ולהצליב אותם עם החישובים.'

        metrics = {
            'destiny': birthdate_analysis.get('destiny', '-'),
            'name_total': name_analysis['destiny_path']['final'],
            'soul': name_analysis['soul_expression']['final'],
            'outer': name_analysis['outer_behavior']['final'],
            'personal_year': birthdate_analysis.get('year', '-'),
            'hidden_year': name_analysis['destiny_path'].get('master') or '-',
            'missing': _format_numbers(missing_info['missing']),
            'beneficial': _format_numbers(missing_info['beneficial']),
            'surplus': _format_numbers(missing_info['surplus']),
            'corpus_size': f"{corpus_summary['total_books']} קבצים",
            'top_themes': top_categories,
            'media_mix': extensions_summary(corpus_summary['extensions']),
            'readiness': readiness_label(str(corpus_summary['readiness'])),
            'next_step': next_step,
        }
        details = dict(analysis)
        details['corpus_summary'] = corpus_summary
        details['category_summary'] = category_summary
        details['mapped_books_hint'] = mapped_books
        return {
            'summary': 'גימטריה מלאה לפי מיכל גרין, עם בדיקת ו\' כתנועה/עיצור ובסיס טקסטואלי ממופה לקטגוריות.',
            'metrics': metrics,
            'details': details,
        }
