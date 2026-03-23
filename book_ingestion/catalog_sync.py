"""Refresh all configured research corpora and regenerate catalogs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .astrology_blueprint import AstrologyBlueprint
from .astrology_mapper import AstrologyCorpusMapper
from .book_processor import BookProcessor
from .chapter_mapper import GreenChapterMapper
from .ocr_batch import PendingOCRRunner
from .ocr_planner import OCRPlanner
from .raw_book_router import RawBookRouter
from .spirit_mapper import SpiritCorpusMapper


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERPRETATIONS_ROOT = PROJECT_ROOT / "interpretations"


def _find_source(pattern: str) -> Path:
    matches = list(INTERPRETATIONS_ROOT.rglob(pattern))
    if not matches:
        raise FileNotFoundError(f'Could not locate source file matching {pattern!r}')
    return matches[0]


ASTROLOGY_MEDIATION_SOURCE = _find_source("num_astro_json.json")
SIFUR_FINAL_SCHEMA_SOURCE = _find_source("*__final_schema.json")


CORPORA: Dict[str, Dict[str, str]] = {
    'green': {
        'folder': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\ספר הנומרולוגיה השלם',
        'catalog': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\ספר הנומרולוגיה השלם\green_books.md',
        'map': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\ספר הנומרולוגיה השלם\green_category_map.md',
        'method': 'green',
    },
    'spirit': {
        'folder': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\spirit',
        'catalog': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\spirit\spirit_books.md',
        'queue': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\spirit\spirit_ocr_queue.md',
        'runtime': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\spirit\spirit_ocr_runtime.md',
        'map': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\spirit\spirit_category_map.md',
        'method': 'spirit',
    },
    'men': {
        'folder': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\men',
        'catalog': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\men\men_books.md',
        'method': 'generic',
    },
    'women': {
        'folder': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\women',
        'catalog': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\women\women_books.md',
        'method': 'generic',
    },
    'more_books': {
        'folder': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\more_books',
        'catalog': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\more_books\more_books_books.md',
        'method': 'generic',
    },
    'astrology': {
        'folder': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\astrology',
        'catalog': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\astrology\astrology_books.md',
        'taxonomy': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\astrology\astrology_taxonomy.md',
        'seed': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\astrology\astrology_seed_plan.md',
        'map': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\astrology\astrology_category_map.md',
        'method': 'astrology',
    },
    'astrology_mediation': {
        'source': str(ASTROLOGY_MEDIATION_SOURCE),
        'catalog': str(ASTROLOGY_MEDIATION_SOURCE.parent / 'astrology_mediation_books.md'),
        'method': 'astrology_mediation',
    },
    'sifur_hanumerology_hashalem': {
        'source': str(SIFUR_FINAL_SCHEMA_SOURCE),
        'catalog': str(SIFUR_FINAL_SCHEMA_SOURCE.parent / 'sifur_hanumerology_hashalem_books.md'),
        'method': 'generic',
    },
    'independent_calc': {
        'folder': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\נומרולוגיה לחישוב עצמאי אסתי גוטמן חוטר גזע',
        'catalog': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\נומרולוגיה לחישוב עצמאי אסתי גוטמן חוטר גזע\independent_calc_books.md',
        'method': 'independent_calc',
    },
    'third_millennium': {
        'folder': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\נומרולוגיה של האלף השלישי',
        'catalog': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\נומרולוגיה של האלף השלישי\third_millennium_books.md',
        'method': 'third_millennium',
    },
}

RAW_BOOKS_FOLDER = r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\raw_books'
RAW_BOOKS_REPORT = r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\raw_books\raw_books_intake.md'


def _source_path(config: Dict[str, str]) -> Path:
    return Path(config.get('source') or config['folder'])


def _discover_json_corpora() -> Dict[str, Dict[str, str]]:
    discovered: Dict[str, Dict[str, str]] = {}
    priority_files = ('num_astro_json.json', '*__final_schema.json', '*__strict_schema.json', '*__normalized.json')
    for folder in sorted(INTERPRETATIONS_ROOT.iterdir()):
        if not folder.is_dir():
            continue
        source_file = None
        for pattern in priority_files:
            matches = sorted(folder.glob(pattern))
            if matches:
                source_file = matches[0]
                break
        if not source_file:
            continue
        corpus = folder.name
        try:
            payload = json.loads(source_file.read_text(encoding='utf-8'))
            book_id = str(payload.get('book_id') or '').strip()
            if book_id:
                corpus = book_id
        except Exception:
            pass
        if corpus in CORPORA or corpus in discovered:
            continue
        method = 'astrology_mediation' if source_file.name == 'num_astro_json.json' else 'generic'
        discovered[corpus] = {
            'source': str(source_file),
            'catalog': str(folder / f'{corpus}_books.md'),
            'method': method,
        }
    return discovered


def refresh_all() -> Dict[str, int]:
    processor = BookProcessor()
    summary: Dict[str, int] = {}
    corpora = dict(CORPORA)
    corpora.update(_discover_json_corpora())
    for corpus, config in corpora.items():
        source_path = _source_path(config)
        if config.get('source'):
            source_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            source_path.mkdir(parents=True, exist_ok=True)
        processor.index_corpus(corpus, str(source_path), method=config['method'])
        processor.export_markdown_catalog(corpus, config['catalog'])
        summary[corpus] = len(processor.store.list_books(corpus=corpus))

    green_mapper = GreenChapterMapper(processor.store)
    green_mapper.classify_corpus('green')
    green_mapper.export_markdown_map('green', CORPORA['green']['map'])

    spirit_mapper = SpiritCorpusMapper(processor.store)
    spirit_mapper.classify_corpus('spirit')
    spirit_mapper.export_markdown_map('spirit', CORPORA['spirit']['map'])

    planner = OCRPlanner(processor.store)
    planner.export_markdown_queue('spirit', CORPORA['spirit']['queue'])

    runner = PendingOCRRunner(store=processor.store, engine=processor.engine, processor=processor)
    runner.export_runtime_report('spirit', CORPORA['spirit']['runtime'])

    astrology_blueprint = AstrologyBlueprint()
    astrology_blueprint.export_taxonomy(CORPORA['astrology']['taxonomy'])
    astrology_blueprint.export_seed_plan(CORPORA['astrology']['seed'])

    astrology_mapper = AstrologyCorpusMapper(processor.store)
    astrology_mapper.classify_corpus('astrology')
    astrology_mapper.export_markdown_map('astrology', CORPORA['astrology']['map'])

    raw_router = RawBookRouter(processor.engine)
    raw_router.export_markdown_report(RAW_BOOKS_FOLDER, RAW_BOOKS_REPORT)
    return summary


if __name__ == '__main__':
    print(refresh_all())
