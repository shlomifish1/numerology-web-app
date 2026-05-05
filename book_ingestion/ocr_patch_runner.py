"""ocr_patch_runner.py — apply a rescan patch PDF to an existing book corpus.

Workflow
--------
1. Read ``{title}__ocr_quality_report.json`` → get ``pages_needing_rescan`` list.
2. OCR each page of the patch PDF with the Hebrew-optimised pipeline.
3. Map: patch page i → original page ``pages_needing_rescan[i]``.
4. Replace each patched page's content in ``{title}__source_corpus.txt``.
5. Re-run stages 3 (structural split), 4 (candidates), and 6 (draft catalog)
   on the updated corpus so all downstream artifacts stay in sync.
6. Re-save a fresh OCR quality report reflecting the patched ratios.

The patch PDF **must** have exactly ``len(pages_needing_rescan)`` pages,
or fewer — in which case only the first N bad pages in the list are patched.

Returns
-------
dict with keys:
  ok                  – True on success
  patched_pages       – list of original page numbers that were replaced
  patch_heb_ratios    – {page_num: heb_ratio} for each replaced page
  new_avg_heb_ratio   – updated average over all OCR pages (post-patch)
  new_rescan_count    – number of pages still below threshold after patching
  artifacts_updated   – paths to re-written artifacts
  warnings            – list of warning strings (non-fatal issues)
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path bootstrap — make sure ocr/ and NumerologyReportGenerator are importable
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_INGESTION_DIR = _THIS_FILE.parent          # .../book_ingestion/
_NRG_DIR = _INGESTION_DIR.parent            # .../NumerologyReportGenerator/
_PROJECT_ROOT = _NRG_DIR.parent             # .../ai_agents/
_OCR_DIR = _PROJECT_ROOT / "ocr"

for _p in (_PROJECT_ROOT, _NRG_DIR, _OCR_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# ---------------------------------------------------------------------------
# Optional: PIL + pytesseract (same pipeline as text_extractor)
# ---------------------------------------------------------------------------
try:
    from text_extractor import (  # type: ignore
        _preprocess_for_hebrew_ocr,
        _ocr_image,
        _heb_ratio as _calc_heb_ratio,
        DEFAULT_LANG as _DEFAULT_LANG,
        DEFAULT_TESSERACT_TIMEOUT_SEC as _DEFAULT_TIMEOUT,
    )
    _EXTRACTOR_AVAILABLE = True
except ImportError:
    _EXTRACTOR_AVAILABLE = False

try:
    import fitz  # type: ignore  (PyMuPDF)
    _FITZ_AVAILABLE = True
except ImportError:
    fitz = None
    _FITZ_AVAILABLE = False

try:
    from PIL import Image  # type: ignore
    import io as _io
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Regex for splitting corpus by page markers
# ---------------------------------------------------------------------------
# Matches ALL page marker variants (with or without quality annotation):
#   "--- Page 5 ---"
#   "--- Page 5 (OCR heb=33%) ---"
#   "--- Page 5 (Empty) ---"
#   "--- Page 5 (OCR heb=41% patched) ---"
_CORPUS_SPLIT_RE = re.compile(
    r"(---\s*Page\s*\d+[^\n]*---)",
    re.IGNORECASE,
)

# Extracts page number from a marker line
_PAGE_NUM_RE = re.compile(r"Page\s*(\d+)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ocr_pdf_pages(pdf_path: Path) -> List[Tuple[str, float]]:
    """OCR every page in *pdf_path* using the Hebrew-optimised pipeline.

    Returns list of (text, heb_ratio) tuples, one per page.
    Raises RuntimeError if required libraries are not available.
    """
    if not _FITZ_AVAILABLE:
        raise RuntimeError("PyMuPDF (fitz) is not installed — cannot OCR patch PDF.")
    if not _EXTRACTOR_AVAILABLE or not _PIL_AVAILABLE:
        raise RuntimeError(
            "text_extractor (ocr/text_extractor.py) or Pillow is not available."
        )

    doc = fitz.open(str(pdf_path))
    results: List[Tuple[str, float]] = []
    try:
        for page_idx, page in enumerate(doc):
            # Try native text first (unlikely in a rescan but handle it)
            native = (page.get_text("text") or "").strip()
            if len(native) >= 50:
                ratio = _calc_heb_ratio(native)
                results.append((native, ratio))
                logger.debug("Patch page %d: native text (heb=%.0f%%)", page_idx + 1, ratio * 100)
                continue

            # Render at 300 DPI (PNG roundtrip to avoid MemoryError)
            pix = page.get_pixmap(dpi=300)
            try:
                img = Image.open(_io.BytesIO(pix.tobytes("png")))
            except Exception:
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            finally:
                pix = None  # free fitz memory before OCR

            img = _preprocess_for_hebrew_ocr(img)
            text = _ocr_image(img, lang=_DEFAULT_LANG, psm=6, timeout=_DEFAULT_TIMEOUT)
            ratio = _calc_heb_ratio(text)
            logger.debug("Patch page %d: OCR heb=%.0f%%", page_idx + 1, ratio * 100)
            results.append((text, ratio))
    finally:
        doc.close()

    return results


def _replace_pages_in_corpus(
    corpus_text: str,
    replacements: Dict[int, Tuple[str, float]],
) -> str:
    """Replace specific pages in *corpus_text* with new (text, heb_ratio) pairs.

    ``replacements`` maps original_page_number → (new_text, new_heb_ratio).
    The page marker for each replaced page is updated to reflect the new ratio
    and is tagged with " patched" so auditing is easy.

    Untouched pages are passed through unchanged.
    """
    # Split into [pre_text, marker1, content1, marker2, content2, ...]
    parts = _CORPUS_SPLIT_RE.split(corpus_text)

    result: List[str] = [parts[0]] if parts else []
    i = 1
    while i < len(parts):
        marker = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""

        m = _PAGE_NUM_RE.search(marker)
        if m:
            page_num = int(m.group(1))
            if page_num in replacements:
                new_text, new_ratio = replacements[page_num]
                heb_pct = round(new_ratio * 100)
                new_marker = f"--- Page {page_num} (OCR heb={heb_pct}% patched) ---"
                result.append(new_marker)
                result.append(f"\n{new_text.strip()}\n")
                i += 2
                continue

        result.append(marker)
        result.append(content)
        i += 2

    return "".join(result)


def _find_quality_report(book_dir: Path) -> Path:
    """Locate the __ocr_quality_report.json inside *book_dir*."""
    candidates = list(book_dir.glob("*__ocr_quality_report.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No __ocr_quality_report.json found in {book_dir}. "
            "Run Phase B first to generate the OCR quality report."
        )
    return candidates[0]  # there should be exactly one


def _find_corpus(book_dir: Path) -> Path:
    """Locate the __source_corpus.txt inside *book_dir*."""
    candidates = list(book_dir.glob("*__source_corpus.txt"))
    if not candidates:
        raise FileNotFoundError(
            f"No __source_corpus.txt found in {book_dir}. "
            "Run Phase B first to generate the corpus."
        )
    return candidates[0]


def _find_manifest(book_dir: Path) -> Path:
    candidates = list(book_dir.glob("*__source_manifest.json"))
    if not candidates:
        raise FileNotFoundError(f"No __source_manifest.json found in {book_dir}.")
    return candidates[0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_ocr_patch(
    book_dir: str,
    patch_pdf_path: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply a rescan patch PDF to an existing book corpus.

    Parameters
    ----------
    book_dir:
        Path to the book's output directory (contains ``__`` artifacts).
    patch_pdf_path:
        Path to the uploaded rescan PDF.  Each page corresponds to one entry
        in ``pages_needing_rescan`` from the quality report (in order).
    dry_run:
        If True, compute everything but write nothing.

    Returns
    -------
    dict — see module docstring for key list.
    """
    book_dir_path = Path(book_dir).resolve()
    patch_pdf = Path(patch_pdf_path).resolve()
    warnings: List[str] = []

    if not book_dir_path.is_dir():
        raise FileNotFoundError(f"book_dir does not exist: {book_dir_path}")
    if not patch_pdf.is_file():
        raise FileNotFoundError(f"patch_pdf does not exist: {patch_pdf}")

    # ── 1. Load quality report ────────────────────────────────────────────
    qr_path = _find_quality_report(book_dir_path)
    quality_report: Dict[str, Any] = json.loads(
        qr_path.read_text(encoding="utf-8")
    )
    pages_needing_rescan: List[int] = quality_report.get("pages_needing_rescan", [])

    if not pages_needing_rescan:
        return {
            "ok": True,
            "patched_pages": [],
            "patch_heb_ratios": {},
            "new_avg_heb_ratio": quality_report.get("avg_heb_ratio"),
            "new_rescan_count": 0,
            "artifacts_updated": [],
            "warnings": ["No pages needed rescan — nothing to patch."],
            "dry_run": dry_run,
        }

    # ── 2. OCR every page of the patch PDF ───────────────────────────────
    logger.info("[OCR Patch] OCRing patch PDF: %s", patch_pdf.name)
    patch_pages = _ocr_pdf_pages(patch_pdf)

    if len(patch_pages) > len(pages_needing_rescan):
        warnings.append(
            f"Patch PDF has {len(patch_pages)} pages but only "
            f"{len(pages_needing_rescan)} pages need rescan. "
            f"Extra pages at the end are ignored."
        )
        patch_pages = patch_pages[:len(pages_needing_rescan)]
    elif len(patch_pages) < len(pages_needing_rescan):
        warnings.append(
            f"Patch PDF has only {len(patch_pages)} pages; "
            f"{len(pages_needing_rescan)} pages need rescan. "
            f"Only the first {len(patch_pages)} bad pages will be patched."
        )

    # ── 3. Build replacement map: original_page_num → (text, ratio) ───────
    pages_to_patch = pages_needing_rescan[:len(patch_pages)]
    replacements: Dict[int, Tuple[str, float]] = {
        orig_page: patch_pages[i]
        for i, orig_page in enumerate(pages_to_patch)
    }
    patch_heb_ratios = {pg: round(r, 3) for pg, (_, r) in replacements.items()}
    logger.info(
        "[OCR Patch] Patching %d pages: %s",
        len(replacements),
        pages_to_patch,
    )

    # ── 4. Update corpus text ─────────────────────────────────────────────
    corpus_path = _find_corpus(book_dir_path)
    corpus_text = corpus_path.read_text(encoding="utf-8")
    new_corpus = _replace_pages_in_corpus(corpus_text, replacements)

    # ── 5. Re-run stages 3+4+6 ───────────────────────────────────────────
    # Import runner components (lazy, so the path bootstrap above is in effect)
    from book_ingestion.book_ingestion_runner import (  # noqa: E402
        BookIngestionRunner,
        _split_into_sections,
        _extract_candidates,
        _build_draft_catalog,
        _write_json,
        _write_text,
        _parse_per_page_quality,
        _OCR_QUALITY_THRESHOLD,
        _now_iso as _runner_now_iso,
    )

    manifest_path = _find_manifest(book_dir_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    book_id = manifest.get("book_id", "unknown")
    book_title = manifest.get("book_title", "unknown")
    extraction_meta = manifest.get("extraction_metadata", {})

    # Artifact paths follow the same naming convention as BookIngestionRunner
    _t = book_title
    inventory_path = book_dir_path / f"{_t}__chapter_inventory.json"
    candidates_path = book_dir_path / f"{_t}__calc_candidates.json"
    draft_catalog_path = book_dir_path / f"{_t}__draft_catalog.json"
    updated_qr_path = qr_path  # overwrite in-place

    artifacts_updated: List[str] = []

    if not dry_run:
        # Write updated corpus
        _write_text(corpus_path, new_corpus)
        artifacts_updated.append(str(corpus_path))

        # Stage 3: structural split
        sections = _split_into_sections(new_corpus, book_id)
        _write_json(inventory_path, sections)
        artifacts_updated.append(str(inventory_path))

        # Stage 4: candidates
        candidates = _extract_candidates(new_corpus, sections)
        _write_json(candidates_path, candidates)
        artifacts_updated.append(str(candidates_path))

        # Stage 6: draft catalog
        draft = _build_draft_catalog(
            book_title=book_title,
            book_id=book_id,
            sections=sections,
            candidates=candidates,
            extraction_meta=extraction_meta,
        )
        _write_json(draft_catalog_path, draft)
        artifacts_updated.append(str(draft_catalog_path))
    else:
        # Dry run: still compute sections+candidates for reporting
        sections = _split_into_sections(new_corpus, book_id)
        candidates = _extract_candidates(new_corpus, sections)

    # ── 6. Update quality report ──────────────────────────────────────────
    updated_pages = _parse_per_page_quality(new_corpus)
    still_bad = [p["page"] for p in updated_pages if p["needs_rescan"]]
    ocr_pages_new = [p for p in updated_pages if p["source"] in ("ocr", "empty")]
    new_avg: Optional[float] = None
    if ocr_pages_new:
        new_avg = sum(p["heb_ratio"] for p in ocr_pages_new) / len(ocr_pages_new)

    updated_qr: Dict[str, Any] = {
        **quality_report,
        "generated_at": _now_iso(),
        "patch_applied": True,
        "patch_pdf": str(patch_pdf),
        "patched_pages": pages_to_patch,
        "pages_needing_rescan": still_bad,
        "rescan_count": len(still_bad),
        "avg_heb_ratio": round(new_avg, 3) if new_avg is not None else None,
        "pages": updated_pages,
    }
    if not dry_run:
        _write_json(updated_qr_path, updated_qr)
        artifacts_updated.append(str(updated_qr_path))

    logger.info(
        "[OCR Patch] Done.  Patched %d pages; %d still need rescan.",
        len(pages_to_patch),
        len(still_bad),
    )

    return {
        "ok": True,
        "patched_pages": pages_to_patch,
        "patch_heb_ratios": patch_heb_ratios,
        "new_avg_heb_ratio": round(new_avg, 3) if new_avg is not None else None,
        "new_rescan_count": len(still_bad),
        "still_needing_rescan": still_bad,
        "sections_found": len(sections),
        "candidates_found": len(candidates),
        "artifacts_updated": artifacts_updated,
        "warnings": warnings,
        "dry_run": dry_run,
    }
