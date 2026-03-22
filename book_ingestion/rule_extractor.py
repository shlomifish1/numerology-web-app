"""Heuristic book rule extraction for numerology corpora.

This module keeps the route-level API stable while turning book ingestion into
something that can preserve provenance, page hints, and reusable rules.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .knowledge_store import KnowledgeStore

try:
    from vector_memory import vector_memory
except Exception:  # pragma: no cover - optional dependency
    vector_memory = None

logger = logging.getLogger(__name__)

PAGE_RE = re.compile(r"---\s*Page\s*(\d+)\s*---", re.IGNORECASE)
SENTENCE_RE = re.compile(r"(?<=[\.\!\?\n])\s+")

CONCEPT_CATALOG: list[dict[str, Any]] = [
    {"key": "life_path", "label": "מסלול חיים", "patterns": [r"\blife\s*path\b", r"מסלול חיים", r"דרך החיים"]},
    {"key": "destiny", "label": "ייעוד / גורל", "patterns": [r"\bdestiny\b", r"\bgor?l\b", r"ייעוד", r"גורל"]},
    {"key": "name_total", "label": "סכום השם", "patterns": [r"סכום השם", r"name total", r"total name", r"שם מלא"]},
    {"key": "topic", "label": "נושא", "patterns": [r"\btopic\b", r"\bsubject\b", r"נושא", r"כותרת", r"chapter", r"section"]},
    {"key": "calculation", "label": "חישוב", "patterns": [r"\bcalc(?:ulation)?\b", r"\bcalculate\b", r"חישוב", r"נוסחה", r"formula", r"\bformulae?\b"]},
    {"key": "meaning", "label": "משמעות / פירוש", "patterns": [r"\bmeaning\b", r"משמעות", r"\binterpretation\b", r"פירוש", r"הסבר"]},
    {"key": "frequency", "label": "תדר / רטט", "patterns": [r"\bfrequenc(?:y|ies)\b", r"תדר", r"רטט", r"ויברציה", r"frequency"]},
    {"key": "structure", "label": "מבנה / עימוד", "patterns": [r"תוכן העניינים", r"\boutline\b", r"\bstructure\b", r"מבנה", r"עימוד"]},
    {"key": "soul", "label": "ביטוי פנימי / נשמה", "patterns": [r"\bsoul\b", r"נשמה", r"נפש", r"ביטוי פנימי"]},
    {"key": "outer", "label": "ביטוי חיצוני", "patterns": [r"\bouter\b", r"צד חיצוני", r"ביטוי חיצוני"]},
    {"key": "personal_year", "label": "שנה אישית", "patterns": [r"\bpersonal year\b", r"שנה אישית", r"מיצב", r"מצב"]},
    {"key": "hidden_year", "label": "שנה נסתרת", "patterns": [r"שנה נסתרת", r"hidden year", r"נפח"]},
    {"key": "missing", "label": "חסרים", "patterns": [r"חסרים", r"missing", r"חסר", r"חוסר"]},
    {"key": "beneficial", "label": "חיזוקים", "patterns": [r"חיזוק", r"beneficial", r"טוב", r"מחזק"]},
    {"key": "surplus", "label": "עודפים", "patterns": [r"עודף", r"surplus", r"עודפים"]},
    {"key": "challenge", "label": "אתגרים", "patterns": [r"אתגר", r"challenge", r"קשיים"]},
    {"key": "pinnacle", "label": "פסגה", "patterns": [r"פסגה", r"pinnacle"]},
    {"key": "karmic", "label": "קרמטי", "patterns": [r"קרמ", r"karmic", r"חוב"]},
    {"key": "master", "label": "מספרי מאסטר", "patterns": [r"11", r"22", r"33", r"מספר מאסטר", r"master"]},
    {"key": "house_number", "label": "מספר בית", "patterns": [r"מספר בית", r"number of house", r"בית"]},
    {"key": "apartment_number", "label": "מספר דירה", "patterns": [r"מספר דירה", r"apartment number", r"דירה"]},
    {"key": "address_number", "label": "מספר כתובת", "patterns": [r"מספר כתובת", r"address number", r"כתובת"]},
]


def _safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u0590-\u05FF]+", "_", str(text).strip().lower())
    slug = slug.strip("_")
    return slug or "book"


def _load_book_chunks(store: KnowledgeStore, book_id: int) -> list[str]:
    with store._connect() as conn:  # noqa: SLF001 - internal helper for ingestion
        rows = conn.execute(
            "SELECT content FROM book_chunks WHERE book_id = ? ORDER BY chunk_index",
            (book_id,),
        ).fetchall()
    return [str(row["content"] or "") for row in rows]


def _split_snippets(text: str, limit: int = 4) -> list[str]:
    sentences = [part.strip() for part in SENTENCE_RE.split(str(text or "").strip()) if part.strip()]
    if not sentences:
        text = re.sub(r"\s+", " ", str(text or "").strip())
        return [text[:360]] if text else []
    snippets: list[str] = []
    for sentence in sentences:
        if len(sentence) >= 40:
            snippets.append(sentence[:480].strip())
        if len(snippets) >= limit:
            break
    return snippets or ([re.sub(r"\s+", " ", str(text or "").strip())[:360]] if text else [])


def _find_page_hint(text: str) -> Optional[int]:
    matches = list(PAGE_RE.finditer(text or ""))
    if not matches:
        return None
    try:
        return int(matches[-1].group(1))
    except Exception:
        return None


def _vector_ingest(tenants: Iterable[str], *, text: str, metadata: Dict[str, Any]) -> None:
    if not vector_memory:
        return
    payload = text.strip()
    if not payload:
        return
    for tenant in tenants:
        tenant = str(tenant or "").strip()
        if not tenant:
            continue
        try:
            vector_memory.store(tenant, payload, metadata)
        except Exception as exc:  # pragma: no cover - optional best-effort sync
            logger.debug("vector_memory ingest failed for %s: %s", tenant, exc)


def _best_book_excerpt(book: Dict[str, Any], chunks: list[str]) -> tuple[str, list[Dict[str, Any]]]:
    evidence: list[Dict[str, Any]] = []
    text_parts: list[str] = []
    for index, chunk in enumerate(chunks[:4]):
        clean = re.sub(r"\s+", " ", chunk).strip()
        if not clean:
            continue
        text_parts.append(clean[:500])
        evidence.append(
            {
                "chunk_index": index,
                "page_hint": _find_page_hint(chunk),
                "excerpt": clean[:500],
                "source_path": str(book.get("source_path") or ""),
                "book_title": str(book.get("title") or ""),
            }
        )
    if not text_parts and book.get("excerpt"):
        excerpt = re.sub(r"\s+", " ", str(book.get("excerpt") or "")).strip()
        if excerpt:
            text_parts.append(excerpt[:500])
            evidence.append(
                {
                    "chunk_index": 0,
                    "page_hint": None,
                    "excerpt": excerpt[:500],
                    "source_path": str(book.get("source_path") or ""),
                    "book_title": str(book.get("title") or ""),
                }
            )
    return " ".join(text_parts).strip(), evidence


def _match_concepts(text: str) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = defaultdict(list)
    if not text:
        return matches
    for concept in CONCEPT_CATALOG:
        for pattern in concept["patterns"]:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                start = max(0, match.start() - 120)
                end = min(len(text), match.end() + 220)
                snippet = re.sub(r"\s+", " ", text[start:end]).strip()
                if snippet and snippet not in matches[concept["key"]]:
                    matches[concept["key"]].append(snippet[:500])
                if len(matches[concept["key"]]) >= 3:
                    break
            if len(matches[concept["key"]]) >= 3:
                break
    return matches


def _save_concept_rule(
    store: KnowledgeStore,
    corpus: str,
    concept_key: str,
    concept_label: str,
    calc_method: str,
    snippets: list[dict[str, Any]],
    *,
    confidence: float,
    cabinet_used: bool = False,
) -> None:
    summary_parts = []
    for item in snippets[:5]:
        source = str(item.get("book_title") or item.get("source_path") or "")
        page_hint = item.get("page_hint")
        excerpt = str(item.get("excerpt") or "")
        prefix = f"{source}"
        if page_hint:
            prefix += f" | page {page_hint}"
        summary_parts.append(f"{prefix}\n{excerpt}")
    interpretation_rules = "\n\n".join(summary_parts).strip()
    if not interpretation_rules:
        interpretation_rules = concept_label
    store.save_book_rule(
        corpus=corpus,
        concept_key=concept_key,
        concept_label=concept_label,
        calc_method=calc_method,
        interpretation_rules=interpretation_rules,
        source_chunks=json.dumps(snippets, ensure_ascii=False),
        confidence=confidence,
        cabinet_used=cabinet_used,
    )


def learn_book(
    corpus: str,
    store: Optional[KnowledgeStore] = None,
    tenants: Optional[Iterable[str]] = None,
    extract_rules: bool = True,
) -> Dict[str, Any]:
    """Learn a corpus into DB rules and optional vector memory tenants."""

    store = store or KnowledgeStore()
    tenant_ids = [str(tenant).strip() for tenant in (tenants or []) if str(tenant).strip()]
    books = store.list_books(corpus=corpus)

    if not books:
        return {
            "corpus": corpus,
            "books": 0,
            "rules_saved": 0,
            "concept_hits": {},
            "tenants": tenant_ids,
        }

    concept_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rules_saved = 0
    total_books = len(books)
    store.set_learning_status(corpus, "running", progress=f"0%|מכין {total_books} ספרים")

    for index, book in enumerate(books, start=1):
        chunks = _load_book_chunks(store, int(book["id"]))
        book_text, evidence = _best_book_excerpt(book, chunks)
        book_title = str(book.get("title") or "book")
        book_slug = _safe_slug(book_title)
        stage_pct = int(((index - 1) / max(total_books, 1)) * 80)
        store.set_learning_status(
            corpus,
            "running",
            progress=f"{stage_pct}%|מעבד {index}/{total_books}: {book_title}",
        )

        generic_label = f"{book_title} - תקציר"
        generic_rule_key = f"book_{book_slug}"
        if extract_rules:
            _save_concept_rule(
                store,
                corpus,
                generic_rule_key,
                generic_label,
                "book_summary",
                evidence or [{
                    "chunk_index": 0,
                    "page_hint": None,
                    "excerpt": book_text[:500],
                    "source_path": str(book.get("source_path") or ""),
                    "book_title": book_title,
                }],
                confidence=0.42 if evidence else 0.2,
                cabinet_used=False,
            )
            rules_saved += 1
            store.set_learning_status(
                corpus,
                "running",
                progress=f"{stage_pct + 10}%|שומר תקציר בסיסי: {book_title}",
            )

        if tenant_ids:
            _vector_ingest(
                tenant_ids,
                text=book_text[:4000] or str(book.get("excerpt") or ""),
                metadata={
                    "corpus": corpus,
                    "book_title": book_title,
                    "source_path": str(book.get("source_path") or ""),
                    "rule_kind": "book_summary",
                },
            )

        if not extract_rules:
            pct = int((index / max(total_books, 1)) * 100)
            store.set_learning_status(corpus, "running", progress=f"{pct}%|הושלמה למידת {index}/{total_books}")
            continue

        matched = _match_concepts(book_text)
        for concept_key, snippets in matched.items():
            concept_meta = next((item for item in CONCEPT_CATALOG if item["key"] == concept_key), None)
            concept_label = str(concept_meta["label"]) if concept_meta else concept_key
            for snippet in snippets:
                concept_bucket[concept_key].append(
                    {
                        "book_title": book_title,
                        "source_path": str(book.get("source_path") or ""),
                        "page_hint": _find_page_hint(snippet),
                        "excerpt": snippet,
                    }
                )
                _vector_ingest(
                    tenant_ids,
                    text=snippet,
                    metadata={
                        "corpus": corpus,
                        "book_title": book_title,
                        "source_path": str(book.get("source_path") or ""),
                        "concept_key": concept_key,
                        "concept_label": concept_label,
                        "rule_kind": "concept_evidence",
                    },
                )
        pct = int((index / max(total_books, 1)) * 100)
        store.set_learning_status(corpus, "running", progress=f"{pct}%|הושלמה למידת {index}/{total_books}")

    if extract_rules:
        for concept_key, snippets in concept_bucket.items():
            concept_meta = next((item for item in CONCEPT_CATALOG if item["key"] == concept_key), None)
            concept_label = str(concept_meta["label"]) if concept_meta else concept_key
            calc_method = f"derived:{concept_key}"
            confidence = min(0.95, 0.5 + (0.08 * min(len(snippets), 5)))
            _save_concept_rule(
                store,
                corpus,
                concept_key,
                concept_label,
                calc_method,
                snippets,
                confidence=confidence,
                cabinet_used=False,
            )
            rules_saved += 1

    store.set_learning_status(corpus, "done", progress=f"100%|נלמדו {total_books} ספרים, נשמרו {rules_saved} חוקים")
    return {
        "corpus": corpus,
        "books": len(books),
        "rules_saved": rules_saved,
        "concept_hits": {key: len(value) for key, value in concept_bucket.items()},
        "tenants": tenant_ids,
    }
