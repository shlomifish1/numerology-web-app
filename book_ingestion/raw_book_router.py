"""Heuristic router for unsorted raw books before corpus placement."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .ocr_engine import OCREngine


ROUTING_RULES = {
    'green': {
        'keywords': ['numerology', 'gematria', 'שם', 'גימטריה', 'נומרולוגיה', 'מפת לידה', 'מספר'],
        'label': 'ספר הנומרולוגיה השלם / numerology',
    },
    'spirit': {
        'keywords': ['psychic', 'intuition', 'awakening', 'consciousness', 'bashar', 'meditation', 'spirit', 'third eye', 'pineal', 'lucid', 'astral', 'remote viewing', 'רוחניות', 'תודעה'],
        'label': 'spirit',
    },
    'astrology': {
        'keywords': ['astrology', 'astrological', 'zodiac', 'horoscope', 'natal', 'synastry', 'transit', 'planet', 'house', 'aspect', 'מזל', 'אסטרולוגיה', 'כוכב'],
        'label': 'astrology',
    },
}

GENERATED_SUFFIXES = ('_intake.md',)


class RawBookRouter:
    def __init__(self, engine: OCREngine | None = None):
        self.engine = engine or OCREngine()

    def scan_folder(self, folder_path: str, limit: int = 25) -> List[Dict[str, object]]:
        folder = Path(folder_path)
        if not folder.exists():
            return []
        suggestions: List[Dict[str, object]] = []
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.name.lower() == 'readme.md' or path.name.lower().endswith(GENERATED_SUFFIXES):
                continue
            suggestion = self._suggest_for_path(path)
            suggestions.append(suggestion)
            if len(suggestions) >= limit:
                break
        return suggestions

    def export_markdown_report(self, folder_path: str, output_path: str, limit: int = 25) -> str:
        suggestions = self.scan_folder(folder_path, limit=limit)
        lines = ['# Raw Books Intake', '']
        if not suggestions:
            lines.append('אין כרגע קבצים חדשים ב-raw_books.')
        else:
            lines.append(f'סך הכל קבצים מוצגים: {len(suggestions)}')
            lines.append('')
            for item in suggestions:
                lines.append(f"## {item['title']}")
                lines.append(f"- יעד מוצע: {item['target_label']}")
                lines.append(f"- confidence: {item['confidence']}")
                lines.append(f"- סיבות: {', '.join(item['reasons']) if item['reasons'] else '-'}")
                lines.append(f"- סטטוס חילוץ: {item['status']}")
                lines.append(f"- נתיב: {item['source_path']}")
                lines.append('')
        content = '\n'.join(lines)
        Path(output_path).write_text(content, encoding='utf-8')
        return content

    def _suggest_for_path(self, path: Path) -> Dict[str, object]:
        inspection = self.engine.inspect(str(path))
        title = path.stem
        excerpt = str(inspection.get('text') or '')[:800].lower()
        haystack = f'{title.lower()} {path.name.lower()} {excerpt}'
        scores: Dict[str, int] = {}
        reasons_by_target: Dict[str, List[str]] = {}
        for target, config in ROUTING_RULES.items():
            hits = [keyword for keyword in config['keywords'] if keyword in haystack]
            scores[target] = len(hits)
            reasons_by_target[target] = hits[:5]
        best_target = max(scores, key=lambda key: scores[key]) if scores else 'unknown'
        best_score = scores.get(best_target, 0)
        if best_score <= 0:
            best_target = 'unknown'
        confidence = min(0.3 + (best_score * 0.12), 0.95) if best_target != 'unknown' else 0.0
        return {
            'title': title,
            'source_path': str(path),
            'status': inspection.get('status', 'metadata_only'),
            'target_corpus': best_target,
            'target_label': ROUTING_RULES.get(best_target, {}).get('label', 'לא זוהה'),
            'confidence': round(confidence, 2),
            'reasons': reasons_by_target.get(best_target, []),
        }

