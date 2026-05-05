"""Automated weak-book review and recovery pipeline for research books.

This module sits on top of the chapter-level research pipeline and adds a
production-friendly recovery loop:

1. Detect weak chapters from live chapter artifacts
2. Re-run local extraction for weak chapters
3. Re-evaluate OCR / text / candidate quality
4. Ask AI reviewers for structured guidance only when the chapter is still weak
5. Emit a deterministic report for the user when manual intervention is needed

The goal is to support large-scale ingestion where most books are processed
automatically and only the genuinely problematic ones are escalated.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_THIS_FILE = Path(__file__).resolve()
_INGESTION_DIR = _THIS_FILE.parent
_NRG_DIR = _INGESTION_DIR.parent
_PROJECT_ROOT = _NRG_DIR.parent
_AI_AGENTS_ROOT = _PROJECT_ROOT
_OCR_DIR = _PROJECT_ROOT / "ocr"

for _bootstrap_path in (_PROJECT_ROOT, _NRG_DIR, _OCR_DIR):
    _s = str(_bootstrap_path)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from interpretation_layout import RESEARCH_ROOT, research_book_dir

from .book_ingestion_runner import BookIngestionRunner
from .research_book_pipeline import _chapter_slug, _chapter_title, run_research_book_pipeline

try:
    from core.ai_manager import ai_engine
    from core.config import MODELS_CONFIG
except Exception:  # pragma: no cover - optional during standalone use
    ai_engine = None
    MODELS_CONFIG = {}

logger = logging.getLogger(__name__)

try:
    import fitz  # type: ignore
    _FITZ_AVAILABLE = True
except Exception:  # pragma: no cover - optional
    fitz = None
    _FITZ_AVAILABLE = False

_PAGE_MARKER_RE = re.compile(r"---\s*Page\s*\d+[^\n]*---", re.IGNORECASE)
_OCR_ERROR_RE = re.compile(r"\[OCR [^\]]+\]", re.IGNORECASE)

_MIN_TEXT_LENGTH = 1200
_MIN_CALCULATIONS = 2
_MIN_AVG_HEB_RATIO = 0.30
_MAX_RESCAN_PAGES = 0

_FREE_MODEL_SEQUENCE = [
    "groq_llama3",
    "gemini_2_flash",
    "google_gemini",
    "openrouter_free",
    "openrouter_mistral_free",
    "hf_gemma4_31b",
    "hf_qwen_coder",
    "hf_deepseek_r1",
    "ollama_gemma4_31b",
    "groq_instant",
]

_PAID_MODEL_SEQUENCE = [
    "deepseek_v3",
    "deepseek_reasoner",
    "claude_haiku",
    "claude_haiku_35",
    "openai_gpt4o",
]

_USER_HOME = Path.home()
_SKILL_ROOT_CANDIDATES = [
    _AI_AGENTS_ROOT / ".codex" / "skills",
    _AI_AGENTS_ROOT.parent / ".codex" / "skills",
    _AI_AGENTS_ROOT / ".claude" / "skills",
    _AI_AGENTS_ROOT.parent / ".claude" / "skills",
    _USER_HOME / ".codex" / "skills",
    _USER_HOME / ".claude" / "skills",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _clean_corpus_text(text: str) -> str:
    stripped = _PAGE_MARKER_RE.sub("", text or "")
    stripped = _OCR_ERROR_RE.sub("", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def _find_skill_dir(skill_name: str) -> Optional[Path]:
    for root in _SKILL_ROOT_CANDIDATES:
        candidate = root / skill_name
        if candidate.exists():
            return candidate
    return None


def _find_executable(names: List[str]) -> str:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return ""


def _find_tesseract_executable() -> str:
    resolved = _find_executable(["tesseract", "tesseract.exe"])
    if resolved:
        return resolved
    common_paths = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe",
    ]
    for path in common_paths:
        if path.exists():
            return str(path)
    return ""


def _split_corpus_pages(raw_text: str) -> Dict[int, str]:
    pages: Dict[int, str] = {}
    current_page: Optional[int] = None
    current_lines: List[str] = []
    for line in str(raw_text or "").splitlines():
        marker = re.match(r"---\s*Page\s*(\d+)[^\n]*---", line.strip(), re.IGNORECASE)
        if marker:
            if current_page is not None:
                pages[current_page] = "\n".join(current_lines).strip()
            current_page = int(marker.group(1))
            current_lines = []
            continue
        if current_page is not None:
            current_lines.append(line)
    if current_page is not None:
        pages[current_page] = "\n".join(current_lines).strip()
    return pages


def _join_corpus_pages(pages: Dict[int, str], page_order: List[int], *, marker_suffix: str = "") -> str:
    parts: List[str] = []
    for page_num in page_order:
        suffix = f" {marker_suffix.strip()}" if marker_suffix.strip() else ""
        parts.append(f"--- Page {page_num}{suffix} ---")
        page_text = str(pages.get(page_num) or "").strip()
        if page_text:
            parts.append(page_text)
    return "\n".join(parts).strip() + "\n"


def _ocr_hebrew_ratio(text: str) -> float:
    chars = [ch for ch in str(text or "") if not ch.isspace()]
    if not chars:
        return 0.0
    heb = sum(1 for ch in chars if "\u0590" <= ch <= "\u05FF")
    return round(heb / max(1, len(chars)), 3)


def _browser_review_candidates(book_root: Path, chapter_state: Dict[str, Any]) -> Dict[str, Any]:
    pdf_path = str(chapter_state.get("pdf_path") or "")
    local_pdf = Path(pdf_path) if pdf_path else None
    local_url = ""
    if local_pdf and local_pdf.exists():
        local_url = local_pdf.resolve().as_uri()
    command = ""
    dev_browser = _find_executable(["dev-browser", "dev-browser.cmd"])
    if dev_browser and local_url:
        command = (
            f'@"\n'
            f'const page = await browser.getPage("{str(chapter_state.get("chapter_key") or "weak-review")}");\n'
            f'await page.goto("{local_url}", {{ waitUntil: "domcontentloaded" }});\n'
            f'console.log(JSON.stringify({{ url: page.url(), title: await page.title() }}, null, 2));\n'
            f'"@ | & \'{dev_browser}\' --browser weak-review --timeout 20'
        )
    return {
        "status": "ready" if local_url else "missing_target",
        "skill_installed": bool(_find_skill_dir("dev-browser")),
        "cli_available": bool(dev_browser),
        "local_pdf_path": str(local_pdf) if local_pdf and local_pdf.exists() else "",
        "local_pdf_url": local_url,
        "suggested_command": command,
    }


def _skill_ocr_recovery(
    pdf_path: Path,
    chapter_dir: Path,
    chapter_state: Dict[str, Any],
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "status": "not_run",
        "strategy": "",
        "skill_installed": bool(_find_skill_dir("hebrew-ocr-forms")),
        "preprocess_script": "",
        "tesseract_available": False,
        "pages_attempted": [],
        "patched_pages": [],
        "patched_text_length": 0,
        "notes": [],
        "patched_raw_text": "",
    }
    skill_dir = _find_skill_dir("hebrew-ocr-forms")
    preprocess_script = skill_dir / "scripts" / "preprocess_image.py" if skill_dir else None
    report["preprocess_script"] = str(preprocess_script) if preprocess_script and preprocess_script.exists() else ""
    if not _FITZ_AVAILABLE or fitz is None:
        report["status"] = "fitz_unavailable"
        report["notes"].append("PyMuPDF is unavailable, so page rendering recovery cannot run.")
        return report
    if not preprocess_script or not preprocess_script.exists():
        report["status"] = "skill_missing"
        report["notes"].append("hebrew-ocr-forms preprocess script was not found.")
        return report

    tesseract_cmd = _find_tesseract_executable()
    report["tesseract_available"] = bool(tesseract_cmd)
    if not tesseract_cmd:
        report["status"] = "tesseract_missing"
        report["notes"].append("Tesseract CLI was not found in PATH.")
        return report

    corpus_path = _find_single(chapter_dir, "*__source_corpus.txt")
    if not corpus_path or not corpus_path.exists():
        report["status"] = "missing_corpus"
        report["notes"].append("Chapter source corpus is missing.")
        return report

    raw_text = corpus_path.read_text(encoding="utf-8")
    pages_map = _split_corpus_pages(raw_text)
    page_order = sorted(pages_map) or list(range(1, 1 + int(chapter_state.get("pages_needing_rescan") or 0)))
    target_pages = list(chapter_state.get("pages_needing_rescan") or [])
    if not target_pages and page_order:
        target_pages = page_order[: min(4, len(page_order))]
    if not target_pages:
        report["status"] = "no_target_pages"
        report["notes"].append("No pages were selected for OCR recovery.")
        return report

    patched_pages = dict(pages_map)
    tmp_root = Path(tempfile.mkdtemp(prefix="weak-book-ocr-"))
    try:
        with fitz.open(str(pdf_path)) as doc:
            for page_num in target_pages[:6]:
                if page_num < 1 or page_num > len(doc):
                    continue
                report["pages_attempted"].append(page_num)
                page = doc.load_page(page_num - 1)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                raw_image = tmp_root / f"page_{page_num}.png"
                processed_image = tmp_root / f"page_{page_num}.processed.png"
                pix.save(str(raw_image))

                pre = subprocess.run(
                    [
                        sys.executable,
                        str(preprocess_script),
                        str(raw_image),
                        str(processed_image),
                        "--enhance-contrast",
                        "--remove-borders",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                )
                if pre.returncode != 0 or not processed_image.exists():
                    report["notes"].append(f"preprocess_failed_page_{page_num}: {pre.stderr.strip() or pre.stdout.strip()}")
                    continue

                ocr = subprocess.run(
                    [
                        tesseract_cmd,
                        str(processed_image),
                        "stdout",
                        "-l",
                        "heb+eng",
                        "--oem",
                        "1",
                        "--psm",
                        "6",
                        "-c",
                        "preserve_interword_spaces=1",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=90,
                )
                recovered_text = re.sub(r"\s+\n", "\n", str(ocr.stdout or "")).strip()
                if ocr.returncode != 0 or len(recovered_text) < 80:
                    report["notes"].append(f"ocr_failed_page_{page_num}: {ocr.stderr.strip() or 'empty text'}")
                    continue
                old_text = str(pages_map.get(page_num) or "").strip()
                old_ratio = _ocr_hebrew_ratio(old_text)
                new_ratio = _ocr_hebrew_ratio(recovered_text)
                if len(recovered_text) > max(120, len(old_text) + 40) or new_ratio > old_ratio + 0.08:
                    patched_pages[page_num] = recovered_text
                    report["patched_pages"].append(
                        {
                            "page": page_num,
                            "old_length": len(old_text),
                            "new_length": len(recovered_text),
                            "old_heb_ratio": old_ratio,
                            "new_heb_ratio": new_ratio,
                        }
                    )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    if not report["patched_pages"]:
        report["status"] = "no_improvement"
        report["notes"].append("Skill OCR recovery did not improve any target page.")
        return report

    patched_text = _join_corpus_pages(patched_pages, sorted(set(page_order or patched_pages.keys())), marker_suffix="(OCR heb-skill)")
    patched_path = chapter_dir / f"{chapter_state.get('chapter_title') or chapter_dir.name}__source_corpus.skill_ocr.txt"
    patched_path.write_text(patched_text, encoding="utf-8")
    report["status"] = "patched"
    report["strategy"] = "hebrew-ocr-forms+tesseract"
    report["patched_text_length"] = len(patched_text)
    report["patched_raw_text"] = patched_text
    report["patched_corpus_path"] = str(patched_path)
    return report


def _list_research_books() -> List[Path]:
    base = research_book_dir("")
    if not base.exists():
        return []
    return sorted(
        folder for folder in base.iterdir()
        if folder.is_dir() and folder.name != "raw_books"
    )


def _select_book_dir(book_dir: str | Path | None) -> Path:
    if book_dir:
        return Path(book_dir).resolve()
    books = _list_research_books()
    if not books:
        raise FileNotFoundError("No research books found under interpretations/research")
    return books[0]


def _find_single(chapter_dir: Path, pattern: str) -> Optional[Path]:
    return next(iter(sorted(chapter_dir.glob(pattern))), None)


def _safe_model_display(model_key: str) -> str:
    conf = dict(MODELS_CONFIG.get(model_key) or {})
    return str(conf.get("display_name") or model_key)


def _available_model_sequence(keys: Iterable[str]) -> List[str]:
    return [key for key in keys if key in MODELS_CONFIG]


def _call_model_direct(model_key: str, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
    if ai_engine is None:
        raise RuntimeError("AI engine is not available in this environment.")
    result = ai_engine._call_provider(model_key, messages, temperature=temperature)  # noqa: SLF001
    provider = str((MODELS_CONFIG.get(model_key) or {}).get("provider") or "")
    if provider:
        try:
            ai_engine._track_cost(provider)  # noqa: SLF001
        except Exception:
            pass
    return str(result or "").strip()


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    cleaned = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except Exception:
        return None


def _chapter_snapshot(chapter_dir: Path) -> Dict[str, Any]:
    manifest_path = _find_single(chapter_dir, "*__source_manifest.json")
    draft_path = _find_single(chapter_dir, "*__draft_catalog.json")
    corpus_path = _find_single(chapter_dir, "*__source_corpus.txt")
    quality_path = _find_single(chapter_dir, "*__ocr_quality_report.json")

    if not manifest_path or not draft_path or not corpus_path:
        return {
            "artifact_dir": str(chapter_dir),
            "artifact_status": "missing_artifacts",
            "weak_reasons": ["missing_artifacts"],
            "is_weak": True,
            "text_length": 0,
            "calculation_count": 0,
            "avg_heb_ratio": None,
            "pages_needing_rescan": [],
            "probe_status": "",
            "extraction_strategy": "",
            "chapter_title": chapter_dir.name,
        }

    manifest = _load_json(manifest_path)
    draft = _load_json(draft_path)
    quality = _load_json(quality_path) if quality_path and quality_path.exists() else {}
    raw_text = corpus_path.read_text(encoding="utf-8")
    clean_text = _clean_corpus_text(raw_text)

    extraction_meta = dict(manifest.get("extraction_metadata") or {})
    calculations = list(draft.get("calculations") or [])
    text_length = len(clean_text)
    avg_heb_ratio = quality.get("avg_heb_ratio")
    pages_needing_rescan = list(quality.get("pages_needing_rescan") or [])

    weak_reasons: List[str] = []
    if text_length < _MIN_TEXT_LENGTH:
        weak_reasons.append("text_too_short")
    if not calculations:
        weak_reasons.append("no_calculations_detected")
    elif len(calculations) < _MIN_CALCULATIONS and text_length < (_MIN_TEXT_LENGTH * 2):
        weak_reasons.append("too_few_calculations_for_short_text")
    if pages_needing_rescan and len(pages_needing_rescan) > _MAX_RESCAN_PAGES:
        weak_reasons.append("pages_need_rescan")
    if avg_heb_ratio is not None and float(avg_heb_ratio) < _MIN_AVG_HEB_RATIO:
        weak_reasons.append("poor_hebrew_ratio")

    artifact_status = "ready" if not weak_reasons else "weak"
    return {
        "artifact_dir": str(chapter_dir),
        "artifact_status": artifact_status,
        "weak_reasons": weak_reasons,
        "is_weak": bool(weak_reasons),
        "text_length": text_length,
        "calculation_count": len(calculations),
        "avg_heb_ratio": avg_heb_ratio,
        "pages_needing_rescan": pages_needing_rescan,
        "probe_status": str(extraction_meta.get("probe_status") or ""),
        "extraction_strategy": str(extraction_meta.get("extraction_strategy") or ""),
        "chapter_title": str(manifest.get("book_title") or chapter_dir.name),
        "source_file": str(manifest.get("source_file") or ""),
        "excerpt": clean_text[:2200],
    }


def _sync_book_markdown(book_root: Path, chapter_states: List[Dict[str, Any]]) -> Path:
    book_title = book_root.name
    catalog_path = book_root / f"{book_title}_books.md"
    lines = ["# Research Catalog", "", f"סה\"כ פרקים: {len(chapter_states)}", ""]
    for item in chapter_states:
        lines.append(f"## {item['chapter_title']}")
        lines.append(f"- סטטוס: {'weak' if item['is_weak'] else 'ready'}")
        lines.append(f"- אורך טקסט: {item['text_length']}")
        lines.append(f"- חישובים שזוהו: {item['calculation_count']}")
        if item.get("avg_heb_ratio") is not None:
            lines.append(f"- avg_heb_ratio: {item['avg_heb_ratio']}")
        if item.get("pages_needing_rescan"):
            lines.append(f"- pages_needing_rescan: {', '.join(str(v) for v in item['pages_needing_rescan'])}")
        lines.append(f"- אסטרטגיית חילוץ: {item.get('extraction_strategy') or '-'}")
        lines.append(f"- Probe: {item.get('probe_status') or '-'}")
        if item["weak_reasons"]:
            lines.append(f"- בעיות: {', '.join(item['weak_reasons'])}")
        source_file = str(item.get("source_file") or "")
        if source_file:
            lines.append(f"- נתיב: {source_file}")
        excerpt = str(item.get("excerpt") or "").strip()
        if excerpt:
            lines.append(f"- excerpt: {excerpt[:300]}")
        lines.append("")
    catalog_path.write_text("\n".join(lines), encoding="utf-8")
    return catalog_path


def _sync_global_research_markdown() -> Path:
    report_path = RESEARCH_ROOT / "research_books.md"
    lines = ["# Research Books Overview", ""]
    books = _list_research_books()
    if not books:
        lines.append("No live research books were found.")
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path

    lines.append(f"סה\"כ ספרי מחקר: {len(books)}")
    lines.append("")
    for book_root in books:
        chapters_root = book_root / "artifacts" / "chapters"
        chapter_states = []
        if chapters_root.exists():
            for chapter_dir in sorted(p for p in chapters_root.iterdir() if p.is_dir()):
                chapter_states.append(_chapter_snapshot(chapter_dir))
        weak_count = sum(1 for item in chapter_states if item.get("is_weak"))
        total_calcs = sum(int(item.get("calculation_count") or 0) for item in chapter_states)
        total_text = sum(int(item.get("text_length") or 0) for item in chapter_states)
        lines.append(f"## {book_root.name}")
        lines.append(f"- chapters: {len(chapter_states)}")
        lines.append(f"- weak_chapters: {weak_count}")
        lines.append(f"- calculations_detected: {total_calcs}")
        lines.append(f"- text_length_total: {total_text}")
        lines.append(f"- source: {book_root}")
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


class WeakBookReviewOrchestrator:
    def __init__(
        self,
        book_dir: str | Path,
        *,
        allow_paid_fallback: bool = True,
        sync_book_pipeline: bool = True,
    ) -> None:
        self.book_root = Path(book_dir).resolve()
        self.allow_paid_fallback = allow_paid_fallback
        self.sync_book_pipeline = sync_book_pipeline
        self.book_title = self.book_root.name
        self.book_id = re.sub(r"\W+", "_", self.book_title, flags=re.UNICODE).strip("_").lower()
        self.chapters_root = self.book_root / "artifacts" / "chapters"
        self.report_json_path = self.book_root / f"{self.book_title}__weak_review_report.json"
        self.report_md_path = self.book_root / f"{self.book_title}__weak_review_report.md"

    def _iter_pdf_chapters(self) -> List[Tuple[Path, Path, str, str]]:
        pdf_paths = sorted(self.book_root.glob("*.pdf"))
        pairs: List[Tuple[Path, Path, str, str]] = []
        for pdf_path in pdf_paths:
            chapter_key = _chapter_slug(pdf_path.name)
            chapter_title = _chapter_title(pdf_path)
            chapter_dir = self.chapters_root / chapter_key
            pairs.append((pdf_path, chapter_dir, chapter_key, chapter_title))
        return pairs

    def _evaluate_all(self) -> List[Dict[str, Any]]:
        states: List[Dict[str, Any]] = []
        for pdf_path, chapter_dir, chapter_key, chapter_title in self._iter_pdf_chapters():
            state = _chapter_snapshot(chapter_dir)
            state.update(
                {
                    "chapter_key": chapter_key,
                    "chapter_title": chapter_title,
                    "pdf_path": str(pdf_path),
                }
            )
            states.append(state)
        return states

    def _rerun_chapter(self, pdf_path: Path, chapter_dir: Path, chapter_title: str, chapter_key: str) -> Dict[str, Any]:
        chapter_dir.mkdir(parents=True, exist_ok=True)
        runner = BookIngestionRunner(
            book_title=chapter_title,
            book_id=f"{self.book_id}__{chapter_key}",
            pdf_path=str(pdf_path),
            output_dir=str(chapter_dir),
            corpus=self.book_id,
        )
        runner.stage_5_ingest_db = lambda: {"skipped": True}  # type: ignore[method-assign]
        return runner.run()

    def _rerun_chapter_with_override(
        self,
        pdf_path: Path,
        chapter_dir: Path,
        chapter_title: str,
        chapter_key: str,
        raw_text: str,
        strategy: str,
    ) -> Dict[str, Any]:
        chapter_dir.mkdir(parents=True, exist_ok=True)
        runner = BookIngestionRunner(
            book_title=chapter_title,
            book_id=f"{self.book_id}__{chapter_key}",
            pdf_path=str(pdf_path),
            output_dir=str(chapter_dir),
            corpus=self.book_id,
            source_text_override=raw_text,
            source_override_strategy=strategy,
        )
        runner.stage_5_ingest_db = lambda: {"skipped": True}  # type: ignore[method-assign]
        return runner.run()

    def _ai_review(self, chapter_state: Dict[str, Any]) -> Dict[str, Any]:
        review_base = {
            "review_status": "not_run",
            "successful_model": "",
            "issue_summary": "",
            "recommended_user_action": "",
            "recommended_inputs": [],
            "notes": [],
            "attempted_models": [],
        }
        if ai_engine is None or not MODELS_CONFIG:
            review_base["review_status"] = "engine_unavailable"
            review_base["issue_summary"] = "AI review engine unavailable in current environment."
            review_base["recommended_user_action"] = "בדוק את הפרק ידנית או הרץ את ה-review מתוך ai_agents."
            return review_base

        messages = [
            {
                "role": "system",
                "content": (
                    "You review OCR and research extraction quality for Hebrew numerology books. "
                    "Return strict JSON only with keys: "
                    "review_status, issue_summary, recommended_user_action, recommended_inputs, notes. "
                    "review_status must be one of: recovered, needs_user_input, weak_but_usable."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "book_title": self.book_title,
                        "chapter_title": chapter_state.get("chapter_title"),
                        "weak_reasons": chapter_state.get("weak_reasons"),
                        "text_length": chapter_state.get("text_length"),
                        "calculation_count": chapter_state.get("calculation_count"),
                        "avg_heb_ratio": chapter_state.get("avg_heb_ratio"),
                        "pages_needing_rescan": chapter_state.get("pages_needing_rescan"),
                        "probe_status": chapter_state.get("probe_status"),
                        "extraction_strategy": chapter_state.get("extraction_strategy"),
                        "excerpt": chapter_state.get("excerpt") or "",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

        attempted_models: List[Dict[str, str]] = []
        model_sequence = _available_model_sequence(_FREE_MODEL_SEQUENCE)
        if self.allow_paid_fallback:
            model_sequence.extend(_available_model_sequence(_PAID_MODEL_SEQUENCE))

        for model_key in model_sequence:
            attempted_models.append(
                {"model_key": model_key, "display_name": _safe_model_display(model_key), "status": "attempted"}
            )
            try:
                raw = _call_model_direct(model_key, messages, temperature=0.1)
                parsed = _extract_json_block(raw)
                if not parsed:
                    attempted_models[-1]["status"] = "invalid_json"
                    continue
                review_base.update(
                    {
                        "review_status": str(parsed.get("review_status") or "weak_but_usable"),
                        "successful_model": model_key,
                        "issue_summary": str(parsed.get("issue_summary") or "").strip(),
                        "recommended_user_action": str(parsed.get("recommended_user_action") or "").strip(),
                        "recommended_inputs": list(parsed.get("recommended_inputs") or []),
                        "notes": list(parsed.get("notes") or []),
                        "attempted_models": attempted_models,
                    }
                )
                return review_base
            except Exception as exc:
                attempted_models[-1]["status"] = f"failed: {exc}"
                continue

        review_base["review_status"] = "all_models_failed"
        review_base["issue_summary"] = "All free and paid review attempts failed."
        review_base["recommended_user_action"] = (
            "צלם או יצא מחדש את הפרק כ-PDF נקי ב-300 DPI או הדבק את הטקסט כ-DOCX/TXT."
        )
        review_base["recommended_inputs"] = [
            "PDF מיושר וחד",
            "Google Docs export",
            "TXT/DOCX נקי ללא מספור עמודים",
        ]
        review_base["attempted_models"] = attempted_models
        return review_base

    def run(self) -> Dict[str, Any]:
        if not self.book_root.exists():
            raise FileNotFoundError(f"Book directory not found: {self.book_root}")

        before = self._evaluate_all()
        weak_before = [item for item in before if item["is_weak"]]
        chapter_runs: List[Dict[str, Any]] = []

        for chapter in weak_before:
            pdf_path = Path(chapter["pdf_path"])
            chapter_dir = Path(chapter["artifact_dir"])
            rerun_summary = self._rerun_chapter(
                pdf_path=pdf_path,
                chapter_dir=chapter_dir,
                chapter_title=str(chapter["chapter_title"]),
                chapter_key=str(chapter["chapter_key"]),
            )
            after_state = _chapter_snapshot(chapter_dir)
            after_state.update(
                {
                    "chapter_key": chapter["chapter_key"],
                    "chapter_title": chapter["chapter_title"],
                    "pdf_path": chapter["pdf_path"],
                }
            )
            skill_ocr = _skill_ocr_recovery(pdf_path, chapter_dir, after_state) if after_state["is_weak"] else {
                "status": "not_needed",
                "strategy": "",
                "skill_installed": bool(_find_skill_dir("hebrew-ocr-forms")),
                "pages_attempted": [],
                "patched_pages": [],
                "notes": [],
            }
            skill_rerun_summary: Dict[str, Any] = {}
            if after_state["is_weak"] and skill_ocr.get("status") == "patched" and skill_ocr.get("patched_raw_text"):
                skill_rerun_summary = self._rerun_chapter_with_override(
                    pdf_path=pdf_path,
                    chapter_dir=chapter_dir,
                    chapter_title=str(chapter["chapter_title"]),
                    chapter_key=str(chapter["chapter_key"]),
                    raw_text=str(skill_ocr.get("patched_raw_text") or ""),
                    strategy=str(skill_ocr.get("strategy") or "hebrew-ocr-forms+tesseract"),
                )
                after_state = _chapter_snapshot(chapter_dir)
                after_state.update(
                    {
                        "chapter_key": chapter["chapter_key"],
                        "chapter_title": chapter["chapter_title"],
                        "pdf_path": chapter["pdf_path"],
                    }
                )
            browser_review = _browser_review_candidates(self.book_root, after_state)
            browser_bundle_path = chapter_dir / f"{str(chapter['chapter_title'])}__browser_recovery.json"
            _write_json(browser_bundle_path, browser_review)
            ai_review = self._ai_review(after_state) if after_state["is_weak"] else {
                "review_status": "recovered_locally",
                "successful_model": "",
                "issue_summary": "Recovered by local OCR / extraction pipeline.",
                "recommended_user_action": "",
                "recommended_inputs": [],
                "notes": [],
                "attempted_models": [],
            }
            chapter_runs.append(
                {
                    "chapter_key": chapter["chapter_key"],
                    "chapter_title": chapter["chapter_title"],
                    "before": chapter,
                    "rerun_summary": rerun_summary,
                    "skill_ocr_recovery": {k: v for k, v in skill_ocr.items() if k != "patched_raw_text"},
                    "skill_rerun_summary": skill_rerun_summary,
                    "after": after_state,
                    "browser_review": browser_review,
                    "browser_bundle_path": str(browser_bundle_path),
                    "ai_review": ai_review,
                }
            )

        if self.sync_book_pipeline and chapter_runs:
            run_research_book_pipeline(self.book_root, force=False, run_weak_review=False)

        after = self._evaluate_all()
        weak_after = [item for item in after if item["is_weak"]]
        catalog_path = _sync_book_markdown(self.book_root, after)

        report = {
            "book_title": self.book_title,
            "book_root": str(self.book_root),
            "generated_at": _utc_now(),
            "allow_paid_fallback": self.allow_paid_fallback,
            "initial_weak_chapter_count": len(weak_before),
            "final_weak_chapter_count": len(weak_after),
            "recovered_chapter_count": max(0, len(weak_before) - len(weak_after)),
            "initial_weak_chapters": [
                {
                    "chapter_key": item["chapter_key"],
                    "chapter_title": item["chapter_title"],
                    "weak_reasons": item["weak_reasons"],
                    "text_length": item["text_length"],
                    "calculation_count": item["calculation_count"],
                    "avg_heb_ratio": item["avg_heb_ratio"],
                    "pages_needing_rescan": item["pages_needing_rescan"],
                }
                for item in weak_before
            ],
            "final_weak_chapters": [
                {
                    "chapter_key": item["chapter_key"],
                    "chapter_title": item["chapter_title"],
                    "weak_reasons": item["weak_reasons"],
                    "text_length": item["text_length"],
                    "calculation_count": item["calculation_count"],
                    "avg_heb_ratio": item["avg_heb_ratio"],
                    "pages_needing_rescan": item["pages_needing_rescan"],
                }
                for item in weak_after
            ],
            "chapter_runs": chapter_runs,
            "catalog_path": str(catalog_path),
            "global_catalog_path": str(_sync_global_research_markdown()),
            "next_actions": [
                "No manual action required." if not weak_after else "Review the weak chapters listed in this report.",
                "If a chapter still fails, prefer a clean 300 DPI PDF or pasted DOCX/TXT text.",
            ],
        }

        _write_json(self.report_json_path, report)
        self.report_md_path.write_text(self._markdown_report(report), encoding="utf-8")
        return report

    def _markdown_report(self, report: Dict[str, Any]) -> str:
        lines = [
            f"# Weak Review Report - {self.book_title}",
            "",
            f"- generated_at: {report['generated_at']}",
            f"- initial_weak_chapter_count: {report['initial_weak_chapter_count']}",
            f"- final_weak_chapter_count: {report['final_weak_chapter_count']}",
            f"- recovered_chapter_count: {report['recovered_chapter_count']}",
            f"- catalog_path: {report['catalog_path']}",
            "",
            "## Initial weak chapters",
            "",
        ]
        if not report["initial_weak_chapters"]:
            lines.append("No weak chapters were detected from live chapter artifacts.")
            lines.append("")
        else:
            for item in report["initial_weak_chapters"]:
                lines.append(f"### {item['chapter_title']}")
                lines.append(f"- reasons: {', '.join(item['weak_reasons']) or '-'}")
                lines.append(f"- text_length: {item['text_length']}")
                lines.append(f"- calculation_count: {item['calculation_count']}")
                lines.append(f"- avg_heb_ratio: {item['avg_heb_ratio']}")
                lines.append("")

        if report["chapter_runs"]:
            lines.append("## Recovery runs")
            lines.append("")
            for run in report["chapter_runs"]:
                lines.append(f"### {run['chapter_title']}")
                lines.append(f"- before: {', '.join(run['before']['weak_reasons'])}")
                lines.append(f"- after: {', '.join(run['after']['weak_reasons']) or 'ready'}")
                if run.get("skill_ocr_recovery"):
                    lines.append(f"- skill_ocr_status: {run['skill_ocr_recovery'].get('status')}")
                    patched_pages = run["skill_ocr_recovery"].get("patched_pages") or []
                    if patched_pages:
                        lines.append(
                            "- skill_ocr_patched_pages: "
                            + ", ".join(str(item.get("page")) for item in patched_pages if item.get("page") is not None)
                        )
                if run.get("browser_review"):
                    lines.append(f"- browser_review_status: {run['browser_review'].get('status')}")
                    if run["browser_review"].get("suggested_command"):
                        lines.append("- browser_review_command: available")
                lines.append(f"- ai_review_status: {run['ai_review']['review_status']}")
                if run["ai_review"].get("successful_model"):
                    lines.append(f"- successful_model: {run['ai_review']['successful_model']}")
                if run["ai_review"].get("issue_summary"):
                    lines.append(f"- summary: {run['ai_review']['issue_summary']}")
                if run["ai_review"].get("recommended_user_action"):
                    lines.append(f"- user_action: {run['ai_review']['recommended_user_action']}")
                lines.append("")

        lines.append("## Final weak chapters")
        lines.append("")
        if not report["final_weak_chapters"]:
            lines.append("All chapters are currently usable according to the automated checks.")
            lines.append("")
        else:
            for item in report["final_weak_chapters"]:
                lines.append(f"### {item['chapter_title']}")
                lines.append(f"- reasons: {', '.join(item['weak_reasons']) or '-'}")
                lines.append(f"- text_length: {item['text_length']}")
                lines.append(f"- calculation_count: {item['calculation_count']}")
                lines.append(f"- avg_heb_ratio: {item['avg_heb_ratio']}")
                lines.append("")

        lines.append("## Next actions")
        lines.append("")
        for item in report["next_actions"]:
            lines.append(f"- {item}")
        lines.append("")
        return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run automated weak-book recovery and AI review.")
    parser.add_argument("--book-dir", help="Path to interpretations/research/<book>. Defaults to first live research book.")
    parser.add_argument("--no-paid", action="store_true", help="Disable paid fallback models.")
    parser.add_argument("--no-sync", action="store_true", help="Do not re-run aggregate research pipeline after recoveries.")
    return parser


def main() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = _build_arg_parser()
    args = parser.parse_args()
    book_dir = _select_book_dir(args.book_dir)
    orchestrator = WeakBookReviewOrchestrator(
        book_dir,
        allow_paid_fallback=not args.no_paid,
        sync_book_pipeline=not args.no_sync,
    )
    report = orchestrator.run()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
