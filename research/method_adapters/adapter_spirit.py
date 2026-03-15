"""Adapter for the spirit corpus."""

from __future__ import annotations

from typing import Dict, Optional

from book_ingestion import OCREngine, OCRPlanner
from book_ingestion.knowledge_store import KnowledgeStore
from book_ingestion.spirit_mapper import CATEGORY_LABELS
from .adapter_base import MethodAdapter
from .corpus_tools import analyze_corpus, extensions_summary, readiness_label, theme_summary


class SpiritMethodAdapter(MethodAdapter):
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
        del first_name, last_name, day, month, year, gender, hebrew_birthdate
        corpus = analyze_corpus(str(self.method_config.get("folder_path") or ""))
        planner = OCRPlanner()
        queue = planner.build_queue('spirit', limit=5)
        store = KnowledgeStore()
        store_summary = store.corpus_summary('spirit')
        category_summary = store.category_summary('spirit')
        ocr_runtime = OCREngine().runtime_summary()
        recommendations = list(corpus["recommendations"])
        if queue and ocr_runtime['ready_for_full_ocr']:
            recommendations.insert(0, f"להריץ OCR תחילה על: {queue[0]['title']}")
        elif queue:
            recommendations.insert(0, 'להשלים Tesseract ואז להריץ את תור ה-OCR לפי סדר העדיפויות.')
        elif category_summary:
            recommendations.insert(0, 'להעמיק מיפוי פרשני בתוך התמות הרוחניות שכבר זוהו.')
        else:
            recommendations.insert(0, 'לעבור למיפוי תמות על בסיס הטקסט שכבר חולץ.')

        top_categories = [
            {
                'key': str(item['category']),
                'label': CATEGORY_LABELS.get(str(item['category']), str(item['category'])),
                'count': int(item['count']),
            }
            for item in category_summary[:4]
        ]
        category_summary_text = ', '.join(item['label'] for item in top_categories[:2]) if top_categories else '-'

        metrics = {
            "destiny": f"{corpus['file_count']} קבצים",
            "name_total": category_summary_text if top_categories else theme_summary(corpus["theme_counts"]),
            "soul": corpus["language_mix"],
            "outer": extensions_summary(corpus["extension_counts"]),
            "personal_year": readiness_label(str(corpus["readiness"])),
            "hidden_year": corpus["total_size"],
            "missing": f"OCR נותר ל-{store_summary['pending_ocr']} קבצים" if store_summary['pending_ocr'] else 'אין חסר תפעולי מיידי',
            "beneficial": category_summary_text if top_categories else theme_summary(corpus["theme_counts"]),
            "surplus": "חסר Tesseract ל-OCR מלא" if queue and not ocr_runtime['ready_for_full_ocr'] else ('ריבוי PDF ללא טקסט מחולץ' if store_summary['pending_ocr'] else '-'),
            "corpus_size": f"{corpus['file_count']} קבצים",
            "top_themes": category_summary_text if top_categories else theme_summary(corpus["theme_counts"]),
            "media_mix": extensions_summary(corpus["extension_counts"]),
            "readiness": readiness_label(str(corpus["readiness"])),
            "next_step": recommendations[0] if recommendations else "למפות adapter פרשני לפי תמות רוחניות.",
        }
        details = dict(corpus)
        details["recommendations"] = recommendations
        details["ocr_queue_top5"] = queue
        details["store_summary"] = store_summary
        details["ocr_runtime"] = ocr_runtime
        details["category_summary"] = top_categories
        return {
            "summary": "Corpus רוחני פעיל עם מספיק חומר כדי להתחיל מיפוי תמות, אינדוקס ותיעדוף OCR.",
            "metrics": metrics,
            "details": details,
        }
