"""Refresh all configured research corpora and regenerate catalogs."""

from __future__ import annotations

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
        'folder': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\נומרולוגיה בתיווך האסטרולוגיה',
        'catalog': r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator\interpretations\נומרולוגיה בתיווך האסטרולוגיה\astrology_mediation_books.md',
        'method': 'astrology_mediation',
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


def refresh_all() -> Dict[str, int]:
    processor = BookProcessor()
    summary: Dict[str, int] = {}
    for corpus, config in CORPORA.items():
        folder = Path(config['folder'])
        folder.mkdir(parents=True, exist_ok=True)
        processor.index_corpus(corpus, str(folder), method=config['method'])
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
