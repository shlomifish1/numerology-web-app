from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interpretation_layout import normalize_corpus_key, research_book_dir, sanitize_folder_name

from .book_ingestion_runner import BookIngestionRunner
from .scaffold_new_book import (
    _build_definition_candidate_stub,
    _build_review_report_stub,
    _build_reviewed_catalog_stub,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _chapter_slug(name: str) -> str:
    text = Path(name).stem.strip()
    text = normalize_corpus_key(text)
    return text or "chapter"


def _chapter_title(pdf_path: Path) -> str:
    title = pdf_path.stem.strip()
    title = re.sub(r"\s+", " ", title)
    return title or pdf_path.stem


def _chapter_artifacts_exist(chapter_dir: Path, chapter_title: str) -> bool:
    required_suffixes = (
        "__source_manifest.json",
        "__source_corpus.txt",
        "__chapter_inventory.json",
        "__calc_candidates.json",
        "__draft_catalog.json",
    )
    for suffix in required_suffixes:
        if not (chapter_dir / f"{chapter_title}{suffix}").exists():
            return False
    return True


def _merge_quality(values: list[str]) -> str:
    rank = {"interpretation_only": 1, "numeric_reference": 2, "possible_formula": 3}
    best = "interpretation_only"
    for value in values:
        if rank.get(str(value), 0) > rank.get(best, 0):
            best = str(value)
    return best


def _confidence_label(values: list[str]) -> str:
    rank = {"low": 1, "medium": 2, "high": 3}
    best = "low"
    for value in values:
        if rank.get(str(value), 0) > rank.get(best, 0):
            best = str(value)
    return best


def _aggregate_calculations(
    book_title: str,
    book_id: str,
    chapter_results: list[dict[str, Any]],
) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    chapter_summary: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    combined_corpus_parts: list[str] = []

    for chapter in chapter_results:
        chapter_key = str(chapter["chapter_key"])
        chapter_title = str(chapter["chapter_title"])
        chapter_summary.append(
            {
                "chapter_key": chapter_key,
                "chapter_title": chapter_title,
                "pdf_path": chapter["pdf_path"],
                "artifact_dir": chapter["artifact_dir"],
                "draft_count": int(chapter["draft_count"]),
                "candidate_count": int(chapter["candidate_count"]),
            }
        )
        combined_corpus_parts.append(f"# {chapter_title}\n\n{chapter.get('source_corpus', '').strip()}\n")
        for cand in list(chapter.get("calc_candidates") or []):
            item = dict(cand)
            item["chapter_key"] = chapter_key
            item["chapter_title"] = chapter_title
            all_candidates.append(item)

        for calc in list(chapter.get("draft_calculations") or []):
            calc_key = str(calc.get("calc_key") or "").strip()
            if not calc_key:
                continue
            bucket = merged.setdefault(
                calc_key,
                {
                    "calc_key": calc_key,
                    "label_he": calc.get("label_he"),
                    "short_explanation": calc.get("short_explanation"),
                    "formula_text": calc.get("formula_text") or "",
                    "formula_steps": list(calc.get("formula_steps") or []),
                    "interpretation": str(calc.get("interpretation") or ""),
                    "interpretation_excerpt": str(calc.get("interpretation_excerpt") or ""),
                    "interpretations_by_value": dict(calc.get("interpretations_by_value") or {}),
                    "input_dependencies": [],
                    "required_inputs": [],
                    "optional_inputs": [],
                    "ambiguous_inputs": [],
                    "input_type_hints": {},
                    "input_dependency_confidence_values": [],
                    "ambiguous_input_dependency": False,
                    "allowed_result_values": list(calc.get("allowed_result_values") or []),
                    "result_values": list(calc.get("result_values") or []),
                    "book_name": book_title,
                    "book_id": book_id,
                    "enabled_in_full_map": False,
                    "needs_review": True,
                    "missing_formula": True,
                    "confidence_values": [],
                    "evidence_count": 0,
                    "chapter_refs": [],
                    "source_refs": [],
                    "source_excerpt_candidates": [],
                    "extraction_quality_values": [],
                },
            )
            if not str(bucket.get("formula_text") or "").strip() and str(calc.get("formula_text") or "").strip():
                bucket["formula_text"] = str(calc.get("formula_text") or "").strip()
            if not list(bucket.get("formula_steps") or []) and list(calc.get("formula_steps") or []):
                bucket["formula_steps"] = list(calc.get("formula_steps") or [])
            if not str(bucket.get("interpretation") or "").strip() and str(calc.get("interpretation") or "").strip():
                bucket["interpretation"] = str(calc.get("interpretation") or "").strip()
            if not str(bucket.get("interpretation_excerpt") or "").strip() and str(calc.get("interpretation_excerpt") or "").strip():
                bucket["interpretation_excerpt"] = str(calc.get("interpretation_excerpt") or "").strip()
            for field in ("input_dependencies", "required_inputs", "optional_inputs", "ambiguous_inputs", "allowed_result_values", "result_values"):
                existing = list(bucket.get(field) or [])
                for item in list(calc.get(field) or []):
                    if item not in existing:
                        existing.append(item)
                bucket[field] = existing
            by_value = dict(bucket.get("interpretations_by_value") or {})
            for value_key, meaning in dict(calc.get("interpretations_by_value") or {}).items():
                if str(value_key).strip() and str(meaning or "").strip() and str(value_key) not in by_value:
                    by_value[str(value_key)] = str(meaning or "").strip()
            bucket["interpretations_by_value"] = by_value
            hints = dict(bucket.get("input_type_hints") or {})
            hints.update(dict(calc.get("input_type_hints") or {}))
            bucket["input_type_hints"] = hints
            bucket["ambiguous_input_dependency"] = bool(bucket["ambiguous_input_dependency"] or calc.get("ambiguous_input_dependency"))
            bucket["input_dependency_confidence_values"].append(str(calc.get("input_dependency_confidence") or ""))
            bucket["confidence_values"].append(float(calc.get("confidence") or 0.0))
            bucket["evidence_count"] += int(calc.get("evidence_count") or 0)
            bucket["extraction_quality_values"].append(str(calc.get("extraction_quality") or "interpretation_only"))
            bucket["missing_formula"] = bool(bucket["missing_formula"] and calc.get("missing_formula", True))
            source_excerpt = str(calc.get("source_excerpt") or "").strip()
            if source_excerpt:
                bucket["source_excerpt_candidates"].append(source_excerpt)
            for source_ref in list(calc.get("source_refs") or []):
                if source_ref not in bucket["source_refs"]:
                    bucket["source_refs"].append(source_ref)
            chapter_ref = str(calc.get("chapter_ref") or chapter_key)
            if chapter_ref and chapter_ref not in bucket["chapter_refs"]:
                bucket["chapter_refs"].append(chapter_ref)

    aggregated_calculations: list[dict[str, Any]] = []
    for calc_key in sorted(merged):
        item = merged[calc_key]
        aggregated_calculations.append(
            {
                "calc_key": item["calc_key"],
                "label_he": item["label_he"],
                "short_explanation": item["short_explanation"],
                "formula_text": item["formula_text"],
                "formula_steps": item["formula_steps"],
                "interpretation": item["interpretation"],
                "interpretation_excerpt": item["interpretation_excerpt"],
                "interpretations_by_value": item["interpretations_by_value"],
                "input_dependencies": item["input_dependencies"],
                "required_inputs": item["required_inputs"],
                "optional_inputs": item["optional_inputs"],
                "ambiguous_inputs": item["ambiguous_inputs"],
                "input_type_hints": item["input_type_hints"],
                "input_dependency_confidence": _confidence_label(item["input_dependency_confidence_values"]),
                "ambiguous_input_dependency": item["ambiguous_input_dependency"],
                "allowed_result_values": item["allowed_result_values"],
                "result_values": item["result_values"],
                "chapter_ref": item["chapter_refs"][0] if item["chapter_refs"] else "",
                "chapter_refs": item["chapter_refs"],
                "book_name": book_title,
                "source_refs": item["source_refs"],
                "source_excerpt": max(item["source_excerpt_candidates"], key=len) if item["source_excerpt_candidates"] else "",
                "enabled_in_full_map": False,
                "needs_review": True,
                "extraction_quality": _merge_quality(item["extraction_quality_values"]),
                "missing_formula": item["missing_formula"],
                "confidence": round(sum(item["confidence_values"]) / max(1, len(item["confidence_values"])), 3),
                "evidence_count": item["evidence_count"],
                "chapter_hits": len(item["chapter_refs"]),
            }
        )

    extraction_metadata = {
        "source_type": "chapter_folder",
        "chapter_count": len(chapter_results),
        "generated_at": _utc_now(),
        "chapters_with_candidates": sum(1 for item in chapter_results if int(item["candidate_count"]) > 0),
        "total_candidate_paragraphs": len(all_candidates),
        "total_aggregated_calculations": len(aggregated_calculations),
    }

    return {
        "book_id": book_id,
        "book_name": book_title,
        "status": "draft_needs_review",
        "generated_at": _utc_now(),
        "generated_by": "ResearchBookPipeline",
        "extraction_metadata": extraction_metadata,
        "chapter_summary": chapter_summary,
        "calculations": aggregated_calculations,
        "_warning": (
            "AGGREGATED RESEARCH DRAFT - merged from chapter-level artifacts. "
            "Manual review is required before promotion."
        ),
        "_combined_source_corpus": "\n\n".join(part.strip() for part in combined_corpus_parts if part.strip()),
        "_all_calc_candidates": all_candidates,
    }


def run_research_book_pipeline(
    book_dir: str | Path,
    *,
    force: bool = False,
    run_weak_review: bool = True,
) -> dict[str, Any]:
    source_dir = Path(book_dir).resolve()
    if not source_dir.exists():
        raise FileNotFoundError(f"Book directory not found: {source_dir}")
    book_title = source_dir.name
    book_id = normalize_corpus_key(book_title)
    book_root = research_book_dir(book_title)
    artifacts_root = book_root / "artifacts"
    chapters_root = artifacts_root / "chapters"
    chapters_root.mkdir(parents=True, exist_ok=True)

    pdf_paths = sorted(source_dir.glob("*.pdf"))
    chapter_results: list[dict[str, Any]] = []

    for pdf_path in pdf_paths:
        chapter_title = _chapter_title(pdf_path)
        chapter_key = _chapter_slug(pdf_path.name)
        chapter_dir = chapters_root / chapter_key
        chapter_dir.mkdir(parents=True, exist_ok=True)

        if force or not _chapter_artifacts_exist(chapter_dir, chapter_title):
            runner = BookIngestionRunner(
                book_title=chapter_title,
                book_id=f"{book_id}__{chapter_key}",
                pdf_path=str(pdf_path),
                output_dir=str(chapter_dir),
                corpus=book_id,
            )
            runner.stage_5_ingest_db = lambda: {"skipped": True}  # type: ignore[method-assign]
            runner.run()

        manifest_path = chapter_dir / f"{chapter_title}__source_manifest.json"
        corpus_path = chapter_dir / f"{chapter_title}__source_corpus.txt"
        inventory_path = chapter_dir / f"{chapter_title}__chapter_inventory.json"
        candidates_path = chapter_dir / f"{chapter_title}__calc_candidates.json"
        draft_path = chapter_dir / f"{chapter_title}__draft_catalog.json"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        calc_candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        chapter_results.append(
            {
                "chapter_key": chapter_key,
                "chapter_title": chapter_title,
                "pdf_path": str(pdf_path),
                "artifact_dir": str(chapter_dir),
                "manifest": manifest,
                "inventory": inventory,
                "calc_candidates": calc_candidates,
                "draft": draft,
                "draft_calculations": list(draft.get("calculations") or []),
                "draft_count": len(list(draft.get("calculations") or [])),
                "candidate_count": len(list(calc_candidates or [])),
                "source_corpus": corpus_path.read_text(encoding="utf-8"),
            }
        )

    aggregate = _aggregate_calculations(book_title, book_id, chapter_results)
    aggregate_manifest = {
        "book_id": book_id,
        "book_title": book_title,
        "generated_at": _utc_now(),
        "source_type": "research_book_pipeline",
        "source_dir": str(source_dir),
        "chapter_count": len(chapter_results),
        "chapters": [
            {
                "chapter_key": chapter["chapter_key"],
                "chapter_title": chapter["chapter_title"],
                "pdf_path": chapter["pdf_path"],
                "artifact_dir": chapter["artifact_dir"],
                "draft_count": chapter["draft_count"],
                "candidate_count": chapter["candidate_count"],
            }
            for chapter in chapter_results
        ],
        "extraction_metadata": dict(aggregate.get("extraction_metadata") or {}),
    }

    top_prefix = book_root / f"{book_title}"
    (top_prefix.with_name(f"{book_title}__source_manifest.json")).write_text(
        json.dumps(aggregate_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (top_prefix.with_name(f"{book_title}__source_corpus.txt")).write_text(
        str(aggregate.pop("_combined_source_corpus", "")),
        encoding="utf-8",
    )
    (top_prefix.with_name(f"{book_title}__chapter_inventory.json")).write_text(
        json.dumps(
            {
                "book_id": book_id,
                "book_title": book_title,
                "chapters": [chapter["inventory"] for chapter in chapter_results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (top_prefix.with_name(f"{book_title}__calc_candidates.json")).write_text(
        json.dumps(aggregate.pop("_all_calc_candidates", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (top_prefix.with_name(f"{book_title}__draft_catalog.json")).write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    reviewed = _build_reviewed_catalog_stub(book_title, book_id, aggregate)
    definition_candidate = _build_definition_candidate_stub(book_title, book_id, aggregate)
    review_report = _build_review_report_stub(book_title, book_id, aggregate, aggregate_manifest)
    (top_prefix.with_name(f"{book_title}__reviewed_catalog.json")).write_text(
        json.dumps(reviewed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (top_prefix.with_name(f"{book_title}__definition_candidate.json")).write_text(
        json.dumps(definition_candidate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (top_prefix.with_name(f"{book_title}__review_report.json")).write_text(
        json.dumps(review_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (artifacts_root / "chapters_manifest.json").write_text(
        json.dumps(aggregate_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "book_id": book_id,
        "book_title": book_title,
        "chapter_count": len(chapter_results),
        "aggregated_calculation_count": len(list(aggregate.get("calculations") or [])),
        "artifacts_root": str(artifacts_root),
        "book_root": str(book_root),
    }
    if run_weak_review:
        from .weak_book_review import WeakBookReviewOrchestrator

        review_summary = WeakBookReviewOrchestrator(book_root).run()
        summary["weak_review_report"] = str(
            book_root / f"{book_title}__weak_review_report.json"
        )
        summary["weak_review_final_count"] = int(review_summary.get("final_weak_chapter_count") or 0)
    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run chapter-by-chapter research pipeline for a research book folder.")
    parser.add_argument("--book-dir", required=True, help="Path to interpretations/research/<book>")
    parser.add_argument("--force", action="store_true", help="Rebuild chapter artifacts even if they already exist")
    parser.add_argument("--skip-weak-review", action="store_true", help="Skip the automated weak-chapter review stage")
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    summary = run_research_book_pipeline(
        args.book_dir,
        force=args.force,
        run_weak_review=not args.skip_weak_review,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
