"""Refresh active research corpora and regenerate catalogs from live folders only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

from .astrology_blueprint import AstrologyBlueprint
from .astrology_mapper import AstrologyCorpusMapper
from .book_processor import BookProcessor
from .chapter_mapper import GreenChapterMapper
from .ocr_batch import PendingOCRRunner
from .ocr_planner import OCRPlanner
from .raw_book_router import RawBookRouter
from .spirit_mapper import SpiritCorpusMapper
from interpretation_layout import (
    RESEARCH_RAW_BOOKS_ROOT,
    RESEARCH_ROOT,
    ensure_layout_dirs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERPRETATIONS_ROOT = PROJECT_ROOT / "interpretations"
DISCOVERY_ROOT = RESEARCH_ROOT
RAW_BOOKS_FOLDER = RESEARCH_RAW_BOOKS_ROOT
RAW_BOOKS_REPORT = RAW_BOOKS_FOLDER / "raw_books_intake.md"
SKIP_FOLDERS = {"__pycache__", ".git", ".idea", "raw_books"}
PRIORITY_SOURCE_PATTERNS = (
    "num_astro_json.json",
    "*__final_schema.json",
    "*__strict_schema.json",
    "*__normalized.json",
)

KNOWN_FOLDER_CONFIGS: Dict[str, Dict[str, object]] = {
    "ספר הנומרולוגיה השלם": {
        "corpus": "green",
        "method": "green",
        "extras": {
            "map": "green_category_map.md",
        },
    },
    "spirit": {
        "corpus": "spirit",
        "method": "spirit",
        "extras": {
            "queue": "spirit_ocr_queue.md",
            "runtime": "spirit_ocr_runtime.md",
            "map": "spirit_category_map.md",
        },
    },
    "more_books": {
        "corpus": "more_books",
        "method": "generic",
    },
    "astrology": {
        "corpus": "astrology",
        "method": "astrology",
        "extras": {
            "taxonomy": "astrology_taxonomy.md",
            "seed": "astrology_seed_plan.md",
            "map": "astrology_category_map.md",
        },
    },
}


def normalize_corpus_key(folder_name: str) -> str:
    return (
        str(folder_name or "")
        .strip()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("'", "")
        .lower()
    )


def _first_match(folder: Path, patterns: Iterable[str]) -> Optional[Path]:
    for pattern in patterns:
        matches = sorted(folder.glob(pattern))
        if matches:
            return matches[0]
    return None


def _build_folder_config(folder: Path) -> Dict[str, str]:
    template = KNOWN_FOLDER_CONFIGS.get(folder.name, {})
    corpus = str(template.get("corpus") or normalize_corpus_key(folder.name))
    config: Dict[str, str] = {
        "corpus": corpus,
        "folder": str(folder),
        "catalog": str(folder / f"{corpus}_books.md"),
        "method": str(template.get("method") or "generic"),
    }
    if "index" in template:
        config["index"] = bool(template.get("index"))
    for key, filename in dict(template.get("extras") or {}).items():
        config[str(key)] = str(folder / str(filename))
    return config


def _discover_folder_corpora() -> Dict[str, Dict[str, str]]:
    discovered: Dict[str, Dict[str, str]] = {}
    if not DISCOVERY_ROOT.exists():
        return discovered
    for folder in sorted(DISCOVERY_ROOT.iterdir()):
        if not folder.is_dir() or folder.name in SKIP_FOLDERS:
            continue
        config = _build_folder_config(folder)
        corpus = str(config.pop("corpus"))
        discovered[corpus] = config
    return discovered


def _default_source_corpus(source_file: Path) -> tuple[str, str]:
    if source_file.name == "num_astro_json.json":
        return "astrology_mediation", "astrology_mediation"
    if re.fullmatch(r".*__final_schema\.json", source_file.name):
        return "sifur_hanumerology_hashalem", "generic"
    return normalize_corpus_key(source_file.parent.name), "generic"


def _discover_json_corpora() -> Dict[str, Dict[str, str]]:
    discovered: Dict[str, Dict[str, str]] = {}
    if not DISCOVERY_ROOT.exists():
        return discovered
    for folder in sorted(DISCOVERY_ROOT.iterdir()):
        if not folder.is_dir() or folder.name in SKIP_FOLDERS:
            continue
        source_file = _first_match(folder, PRIORITY_SOURCE_PATTERNS)
        if not source_file:
            continue
        corpus, method = _default_source_corpus(source_file)
        try:
            payload = json.loads(source_file.read_text(encoding="utf-8"))
            book_id = str(payload.get("book_id") or "").strip()
            if book_id:
                corpus = book_id
        except Exception:
            pass
        if corpus in discovered:
            continue
        discovered[corpus] = {
            "source": str(source_file),
            "catalog": str(folder / f"{corpus}_books.md"),
            "method": method,
        }
    return discovered


def discover_active_corpora() -> Dict[str, Dict[str, str]]:
    corpora = _discover_folder_corpora()
    for corpus, config in _discover_json_corpora().items():
        if corpus not in corpora:
            corpora[corpus] = config
    return corpora


def corpus_aliases(corpus: str, config: Dict[str, str]) -> Set[str]:
    aliases = {str(corpus).strip()}
    location = config.get("folder") or config.get("source")
    if location:
        path = Path(location)
        parent = path if path.is_dir() else path.parent
        folder_name = parent.name.strip()
        if folder_name:
            aliases.add(folder_name)
            aliases.add(normalize_corpus_key(folder_name))
    return {
        alias
        for alias in aliases
        if str(alias or "").strip()
    }


def _source_path(config: Dict[str, str]) -> Path:
    base_path = Path(config.get("source") or config["folder"])
    if base_path.is_dir():
        source_subdir = base_path / "source"
        if source_subdir.exists() and source_subdir.is_dir():
            return source_subdir
    return base_path


def refresh_all() -> Dict[str, int]:
    ensure_layout_dirs()
    processor = BookProcessor()
    summary: Dict[str, int] = {}
    corpora = discover_active_corpora()
    active_aliases = {
        alias
        for corpus, config in corpora.items()
        for alias in corpus_aliases(corpus, config)
    }
    processor.store.prune_to_active_corpora(sorted(active_aliases))

    for corpus, config in corpora.items():
        source_path = _source_path(config)
        if not source_path.exists():
            continue
        if config.get("index", True):
            processor.index_corpus(corpus, str(source_path), method=config["method"])
            processor.export_markdown_catalog(corpus, config["catalog"])
        summary[corpus] = len(processor.store.list_books(corpus=corpus))

    processor.store.dedupe_artifacts()

    if "green" in corpora and corpora["green"].get("map"):
        green_mapper = GreenChapterMapper(processor.store)
        green_mapper.classify_corpus("green")
        green_mapper.export_markdown_map("green", corpora["green"]["map"])

    if "spirit" in corpora:
        spirit_mapper = SpiritCorpusMapper(processor.store)
        spirit_mapper.classify_corpus("spirit")
        if corpora["spirit"].get("map"):
            spirit_mapper.export_markdown_map("spirit", corpora["spirit"]["map"])

        planner = OCRPlanner(processor.store)
        if corpora["spirit"].get("queue"):
            planner.export_markdown_queue("spirit", corpora["spirit"]["queue"])

        runner = PendingOCRRunner(store=processor.store, engine=processor.engine, processor=processor)
        if corpora["spirit"].get("runtime"):
            runner.export_runtime_report("spirit", corpora["spirit"]["runtime"])

    if "astrology" in corpora:
        astrology_blueprint = AstrologyBlueprint()
        if corpora["astrology"].get("taxonomy"):
            astrology_blueprint.export_taxonomy(corpora["astrology"]["taxonomy"])
        if corpora["astrology"].get("seed"):
            astrology_blueprint.export_seed_plan(corpora["astrology"]["seed"])

        astrology_mapper = AstrologyCorpusMapper(processor.store)
        astrology_mapper.classify_corpus("astrology")
        if corpora["astrology"].get("map"):
            astrology_mapper.export_markdown_map("astrology", corpora["astrology"]["map"])

    if RAW_BOOKS_FOLDER.exists():
        raw_router = RawBookRouter(processor.engine)
        raw_router.export_markdown_report(str(RAW_BOOKS_FOLDER), str(RAW_BOOKS_REPORT))

    return summary


if __name__ == "__main__":
    print(refresh_all())
