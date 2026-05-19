"""Utility helpers for corpus-backed research adapters."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List

from interpretation_layout import PROJECT_ROOT


THEME_KEYWORDS = {
    "intuition": ["psychic", "intuition", "third eye", "pineal", "remote viewing", "lucid", "astral"],
    "healing": ["healing", "energy", "light", "spirit", "body", "medicine", "healer"],
    "consciousness": ["awakening", "consciousness", "god", "tao", "oneness", "fourth way", "awaken"],
    "influence": ["success", "power", "rich", "friends", "influence", "robbins", "problem solving"],
    "channeling": ["bashar", "pleadian", "alien", "pleiadian"],
}

THEME_LABELS = {
    "intuition": "אינטואיציה ותפיסה",
    "healing": "ריפוי ואנרגיה",
    "consciousness": "תודעה והתעוררות",
    "influence": "השפעה וצמיחה",
    "channeling": "תקשור ותודעות נוספות",
}

GENERATED_SUFFIXES = ('_books.md', '_category_map.md', '_ocr_queue.md', '_runtime.md', '_seed_plan.md', '_taxonomy.md', '_intake.md')


def _human_size(total_bytes: int) -> str:
    if total_bytes <= 0:
        return "0 MB"
    return f"{round(total_bytes / (1024 * 1024), 1)} MB"


def _language_mix(paths: Iterable[Path]) -> str:
    has_hebrew = False
    has_latin = False
    for path in paths:
        name = path.name
        if any("\u0590" <= ch <= "\u05FF" for ch in name):
            has_hebrew = True
        if any("A" <= ch <= "Z" or "a" <= ch <= "z" for ch in name):
            has_latin = True
    if has_hebrew and has_latin:
        return "HE+EN"
    if has_hebrew:
        return "HE"
    if has_latin:
        return "EN"
    return "לא זוהה"


def analyze_corpus(folder_path: str) -> Dict[str, object]:
    folder = Path(folder_path)
    if not folder.is_absolute():
        folder = PROJECT_ROOT / folder
    files = []
    if folder.exists():
        for path in folder.rglob('*'):
            if path.is_file() and not _is_generated(path):
                files.append(path)
        files.sort()
    extension_counts = Counter(path.suffix.lower() or "[none]" for path in files)
    total_bytes = sum(path.stat().st_size for path in files)
    theme_counts = Counter()
    for path in files:
        lowered = path.name.lower()
        for theme, keywords in THEME_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                theme_counts[theme] += 1

    top_themes = [
        {"key": key, "label": THEME_LABELS.get(key, key), "count": count}
        for key, count in theme_counts.most_common(3)
    ]
    extensions = [{"extension": ext, "count": count} for ext, count in extension_counts.most_common(5)]
    sample_titles = [path.name for path in files[:8]]
    readiness = "empty" if not files else "seeded" if len(files) < 10 else "research-ready"
    recommendations: List[str] = []
    if not files:
        recommendations.append("להוסיף לפחות 3-5 ספרי מקור לפני כתיבת adapter פרשני.")
    if extension_counts.get(".pdf", 0) == len(files) and files:
        recommendations.append("כדאי להוסיף טקסטים מחולצים או אינדקס תוכן כדי לאפשר חיפוש מהיר.")
    if not top_themes and files:
        recommendations.append("נדרש מיפוי ידני של תמות ראשיות לפי כותרות הספרים.")

    return {
        "folder_path": str(folder),
        "file_count": len(files),
        "total_size": _human_size(total_bytes),
        "extension_counts": extensions,
        "theme_counts": top_themes,
        "sample_titles": sample_titles,
        "language_mix": _language_mix(files),
        "readiness": readiness,
        "recommendations": recommendations,
    }


def readiness_label(readiness: str) -> str:
    labels = {
        "empty": "ריק",
        "seeded": "בסיסי",
        "research-ready": "מוכן למחקר",
    }
    return labels.get(readiness, readiness)


def extensions_summary(extensions: List[Dict[str, object]]) -> str:
    if not extensions:
        return "-"
    return " / ".join(f"{item['count']} {str(item['extension']).lstrip('.').upper()}" for item in extensions[:3])


def theme_summary(themes: List[Dict[str, object]]) -> str:
    if not themes:
        return "-"
    return ", ".join(item["label"] for item in themes[:2])


def _is_generated(path: Path) -> bool:
    return path.name.lower().endswith(GENERATED_SUFFIXES)



