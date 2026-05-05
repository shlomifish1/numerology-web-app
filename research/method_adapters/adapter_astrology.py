"""Adapter for the astrology corpus."""

from __future__ import annotations

from typing import Dict, Optional

from book_ingestion.astrology_blueprint import AstrologyBlueprint
from book_ingestion.astrology_mapper import CATEGORY_LABELS
from book_ingestion.knowledge_store import KnowledgeStore
from .adapter_base import MethodAdapter
from .corpus_tools import analyze_corpus, extensions_summary, readiness_label


class AstrologyMethodAdapter(MethodAdapter):
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
        blueprint = AstrologyBlueprint().summary()
        store = KnowledgeStore()
        category_summary = store.category_summary('astrology')

        if category_summary:
            top_summary = ', '.join(CATEGORY_LABELS.get(str(item['category']), str(item['category'])) for item in category_summary[:2])
        else:
            top_summary = ', '.join(blueprint['taxonomy_labels'][:2]) if blueprint['taxonomy_labels'] else '-'

        if corpus["file_count"]:
            summary = "נמצא corpus אסטרולוגי התחלתי, עם blueprint ומיפוי ראשון למזלות, בתים, כוכבים והיבטים."
            next_step = "להעמיק chapter mapping ולבנות adapter פרשני ראשון על בסיס הקטגוריות שנמצאו."
            missing = "chapter extraction, advanced adapter logic"
        else:
            summary = "תיקיית astrology עדיין ריקה, אבל הוגדרו taxonomy, seed plan ו-mapper כדי לאפשר בנייה מסודרת של corpus."
            next_step = blueprint['next_step']
            missing = "ספרי מקור, taxonomy-to-corpus mapping, adapter logic"

        metrics = {
            "destiny": f"{corpus['file_count']} קבצים",
            "name_total": top_summary,
            "soul": corpus["language_mix"] if corpus["file_count"] else f"{blueprint['seed_books_count']} ספרי seed",
            "outer": extensions_summary(corpus["extension_counts"]),
            "personal_year": readiness_label(str(corpus["readiness"])),
            "hidden_year": corpus["total_size"],
            "missing": missing,
            "beneficial": top_summary,
            "surplus": "אין עדיין corpus, אבל יש blueprint מוכן" if not corpus['file_count'] else '-',
            "corpus_size": f"{corpus['file_count']} קבצים",
            "top_themes": top_summary,
            "media_mix": extensions_summary(corpus["extension_counts"]),
            "readiness": readiness_label(str(corpus["readiness"])),
            "next_step": next_step,
        }
        details = dict(corpus)
        details["taxonomy"] = blueprint['taxonomy_labels']
        details["recommended_seed_books"] = blueprint['seed_book_titles']
        details["seed_books_count"] = blueprint['seed_books_count']
        details["category_summary"] = [
            {
                'key': str(item['category']),
                'label': CATEGORY_LABELS.get(str(item['category']), str(item['category'])),
                'count': int(item['count']),
            }
            for item in category_summary[:6]
        ]
        return {
            "summary": summary,
            "metrics": metrics,
            "details": details,
        }
