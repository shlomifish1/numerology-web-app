"""Generic adapter for future books that only exist as folder content."""

from __future__ import annotations

from typing import Dict, Optional

from .adapter_base import MethodAdapter
from .corpus_tools import analyze_corpus, extensions_summary, readiness_label, theme_summary


class GenericMethodAdapter(MethodAdapter):
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
        metrics = {
            "destiny": "ממתין" if corpus["file_count"] else "0 קבצים",
            "name_total": theme_summary(corpus["theme_counts"]),
            "soul": corpus["language_mix"],
            "outer": extensions_summary(corpus["extension_counts"]),
            "personal_year": readiness_label(str(corpus["readiness"])),
            "hidden_year": corpus["total_size"],
            "missing": ", ".join(corpus["recommendations"]) if corpus["recommendations"] else "-",
            "beneficial": theme_summary(corpus["theme_counts"]),
            "surplus": "PDF-heavy" if corpus["file_count"] and corpus["extension_counts"] and corpus["extension_counts"][0]["extension"] == ".pdf" else "-",
            "corpus_size": f"{corpus['file_count']} קבצים",
            "top_themes": theme_summary(corpus["theme_counts"]),
            "media_mix": extensions_summary(corpus["extension_counts"]),
            "readiness": readiness_label(str(corpus["readiness"])),
            "next_step": corpus["recommendations"][0] if corpus["recommendations"] else "למפות adapter ייעודי לפי תוכן.",
        }
        return {
            "summary": "זוהתה תיקיית תוכן ללא מנוע חישוב ייעודי. הוצג ניתוח corpus בסיסי.",
            "metrics": metrics,
            "details": corpus,
        }
