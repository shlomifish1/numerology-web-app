"""Comparison engine for research-only numerology methods."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .approval_store import ApprovalStore
from .method_adapters import get_adapter
from .method_registry import INTERNAL_BASELINE_KEY, MethodRegistry
from book_ingestion.knowledge_store import KnowledgeStore
from interpretation_layout import (
    path_to_corpus_alias,
    research_source_label,
    source_label_to_corpus_alias,
)


DEFAULT_ROWS = [
    ("destiny", "???? ????"),
    ("name_total", "???? ???"),
    ("soul", "????? ?????"),
    ("outer", "????? ??????"),
    ("personal_year", "??? ?????"),
    ("hidden_year", "??? ?????"),
    ("missing", "?????"),
    ("beneficial", "??????"),
    ("surplus", "??????"),
]

DETAIL_LABELS = {
    "life_path": "שביל גורל",
    "destiny": "ייעוד",
    "name_total": "מספר השם",
    "soul": "ביטוי פנימי",
    "outer": "ביטוי חיצוני",
    "personal_year": "שנה אישית",
    "hidden_year": "שנה נסתרת",
    "challenge": "אתגר",
    "pinnacle": "פסגה",
    "karmic": "קרמתי",
    "master": "מאסטר",
    "missing": "חסרים",
    "surplus": "עודפים",
}


def _short_text(value: object, limit: int = 260) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _parse_json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _normalize_corpus_key(value: object) -> str:
    return (
        str(value or "")
        .strip()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("'", "")
        .lower()
    )


def _method_corpus_aliases(method: Dict[str, object]) -> set[str]:
    aliases: set[str] = set()
    for value in (
        method.get("resolved_corpus"),
        method.get("key"),
        method.get("folder"),
    ):
        text = str(value or "").strip()
        if text:
            aliases.add(text)
            aliases.add(_normalize_corpus_key(text))
    folder_path = str(method.get("folder_path") or "").strip()
    if folder_path:
        folder_name = Path(folder_path).name.strip()
        if folder_name:
            aliases.add(folder_name)
            aliases.add(_normalize_corpus_key(folder_name))
    return {
        alias
        for alias in aliases
        if alias and alias != INTERNAL_BASELINE_KEY
    }


def _build_alias_to_key(rendered_methods: List[Dict[str, object]]) -> Dict[str, str]:
    alias_to_key: Dict[str, str] = {}
    for method in rendered_methods:
        canonical = str(
            method.get("resolved_corpus")
            or method.get("key")
            or ""
        ).strip()
        if not canonical or canonical == INTERNAL_BASELINE_KEY:
            continue
        for alias in _method_corpus_aliases(method):
            alias_to_key[alias] = canonical
    return alias_to_key


def _source_to_corpus_key(source: object, alias_to_key: Dict[str, str]) -> str:
    text = str(source or "").strip()
    if not text:
        return ""
    alias = source_label_to_corpus_alias(text)
    if alias:
        return alias_to_key.get(alias) or alias_to_key.get(_normalize_corpus_key(alias)) or _normalize_corpus_key(alias)
    try:
        path = Path(text)
        if path.is_absolute():
            alias = path_to_corpus_alias(path)
            if alias:
                return alias_to_key.get(alias) or alias_to_key.get(_normalize_corpus_key(alias)) or _normalize_corpus_key(alias)
    except Exception:
        pass
    return alias_to_key.get(text) or alias_to_key.get(_normalize_corpus_key(text)) or text


def _detail_label(key: object) -> str:
    raw = str(key or "").strip()
    return DETAIL_LABELS.get(raw, raw.replace("_", " ") or "סעיף")


def _add_report_section(
    sections: List[Dict[str, object]],
    seen: set[str],
    *,
    key: str,
    title: str,
    value: object = "",
    meaning: object = "",
    source: str = "",
) -> None:
    signature = "|".join([
        str(title or "").strip(),
        str(value or "").strip(),
        str(meaning or "").strip(),
        str(source or "").strip(),
    ])
    if not signature.strip() or signature in seen:
        return
    seen.add(signature)
    sections.append({
        "key": key,
        "title": title,
        "value": value,
        "meaning": meaning,
        "source": source,
    })


def _build_book_evidence_sections(
    *,
    store: KnowledgeStore,
    rendered_methods: List[Dict[str, object]],
    active_corpora: List[str],
    pythagorean_result: Dict[str, object],
    first_name: str,
    last_name: str,
    day: int,
    month: int,
    year: int,
    gender: str,
    limit: int = 10,
) -> List[Dict[str, object]]:
    sections: List[Dict[str, object]] = []
    seen: set[str] = set()
    query_parts: List[str] = [
        first_name,
        last_name,
        gender,
        str(day),
        str(month),
        str(year),
    ]
    report_summary = dict(pythagorean_result.get("report_summary") or {})
    metrics = dict(pythagorean_result.get("metrics") or {})
    for key in ("destiny", "name_total", "soul", "outer", "personal_year", "hidden_year"):
        value = report_summary.get(key, metrics.get(key))
        if value not in (None, "", "-"):
            query_parts.extend([key, str(value)])

    for method in rendered_methods:
        method_key = str(method.get("key") or "").strip()
        display_name = str(method.get("display_name") or method_key or "ספר").strip()
        result = method.get("result") if isinstance(method.get("result"), dict) else {}
        resolved_adapter = str(method.get("resolved_adapter") or "").strip()
        summary = _short_text(result.get("summary") or "", 220)
        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        include_method_sections = resolved_adapter not in {"GenericMethodAdapter"}
        if method_key and method_key != INTERNAL_BASELINE_KEY and include_method_sections:
            query_parts.extend([method_key, display_name])
            if summary:
                _add_report_section(
                    sections,
                    seen,
                    key=f"method_summary:{method_key}",
                    title=f"{display_name} · סיכום",
                    value=summary,
                    meaning=f"ספר/קורפוס פעיל למחקר עם {len(details)} חוקים מאומתים.",
                    source=research_source_label(method_key),
                )
            for detail_key, detail in list(details.items())[:3]:
                if not isinstance(detail, dict):
                    continue
                _add_report_section(
                    sections,
                    seen,
                    key=f"method_detail:{method_key}:{detail_key}",
                    title=f"{display_name} · {_detail_label(detail_key)}",
                    value=_short_text(detail.get("calc_method") or detail_key or display_name, 120),
                    meaning=_short_text(detail.get("interpretation") or "", 420),
                    source=research_source_label(method_key, detail_key),
                )

    query = " ".join(part for part in query_parts if str(part or "").strip())
    if query:
        try:
            memory_hits = store.search_memory(
                query,
                corpora=active_corpora,
                limit=max(8, limit * 2),
            )
        except Exception:
            memory_hits = []
        outline_hits = [hit for hit in memory_hits if str(hit.get("artifact_type") or "").strip().lower() == "book_outline"]
        source_hits = outline_hits or memory_hits
        book_seen: set[str] = set()
        for hit in source_hits:
            corpus = str(hit.get("corpus") or "").strip()
            source_path = str(hit.get("source_path") or "").strip()
            title = str(hit.get("title") or "").strip() or "ספר"
            book_key = "|".join([corpus, source_path, title])
            if book_key in book_seen:
                continue
            book_seen.add(book_key)
            outline = _parse_json_object(hit.get("artifact_json"))
            headings = [str(item).strip() for item in list(outline.get("headings") or []) if str(item).strip()]
            keywords = [str(item).strip() for item in list(outline.get("keywords") or []) if str(item).strip()]
            topic_candidates = [str(item).strip() for item in list(outline.get("topic_candidates") or []) if str(item).strip()]
            summary_source = (
                outline.get("summary")
                or hit.get("artifact_text")
                or hit.get("interpretation_rules")
                or hit.get("excerpt")
                or hit.get("metadata_json")
                or ""
            )
            summary = _short_text(summary_source, 320)
            if not summary and headings:
                summary = " | ".join(headings[:2])
            primary_topic = topic_candidates[0] if topic_candidates else (headings[0] if headings else title)
            calculation_text = f"{len(headings)} כותרות · {len(keywords)} מילות מפתח · {len(summary.split())} מילים"
            if calculation_text.startswith("0 כותרות") and not keywords:
                calculation_text = "נגזר ממקור הספר, כותרות קיימות וטקסט מקורי שנשלף מהקובץ"
            frequency_text = ", ".join(keywords[:5]) if keywords else _short_text(summary or title, 120)
            _add_report_section(
                sections,
                seen,
                key=f"outline:title:{source_path or title}",
                title="כותרת",
                value=title,
                meaning=summary or title,
                source=source_path or corpus,
            )
            _add_report_section(
                sections,
                seen,
                key=f"outline:topic:{source_path or title}",
                title="נושא",
                value=primary_topic,
                meaning=summary or f"זוהו {len(headings)} כותרות מתוך הספר.",
                source=source_path or corpus,
            )
            _add_report_section(
                sections,
                seen,
                key=f"outline:calc:{source_path or title}",
                title="חישוב",
                value=calculation_text,
                meaning="החישוב נשען על כותרות, מילות מפתח ותמצית מבנית שנשלפו מהקובץ.",
                source=source_path or corpus,
            )
            _add_report_section(
                sections,
                seen,
                key=f"outline:meaning:{source_path or title}",
                title="משמעות",
                value=summary or primary_topic,
                meaning=_short_text(hit.get("interpretation_rules") or hit.get("artifact_text") or hit.get("metadata_json") or "", 360),
                source=source_path or corpus,
            )
            _add_report_section(
                sections,
                seen,
                key=f"outline:frequency:{source_path or title}",
                title="תדר",
                value=frequency_text,
                meaning=f"זוהו {len(keywords)} מילות מפתח רלוונטיות מתוך {title}.",
                source=source_path or corpus,
            )
            if len(sections) >= limit:
                break
        for hit in memory_hits:
            corpus = str(hit.get("corpus") or "").strip()
            concept = str(hit.get("concept_label") or hit.get("concept_key") or hit.get("title") or "").strip()
            source_path = str(hit.get("source_path") or "").strip()
            preview = (
                str(hit.get("chunk_text") or "").strip()
                or str(hit.get("artifact_text") or "").strip()
                or str(hit.get("interpretation_rules") or "").strip()
                or str(hit.get("excerpt") or "").strip()
            )
            if not preview:
                continue
            _add_report_section(
                sections,
                seen,
                key=f"memory:{corpus}:{concept}:{source_path}",
                title=" · ".join(bit for bit in [corpus or "קורפוס", concept or "קטע"] if bit),
                value=_short_text(preview, 160),
                meaning=_short_text(
                    hit.get("interpretation_rules") or hit.get("artifact_text") or hit.get("metadata_json") or "",
                    420,
                ),
                source=source_path or corpus,
            )
            if len(sections) >= limit:
                break

    return sections[:limit]


class ComparisonEngine:
    def __init__(
        self,
        registry: Optional[MethodRegistry] = None,
        approval_store: Optional[ApprovalStore] = None,
    ):
        self.registry = registry or MethodRegistry()
        self.approval_store = approval_store or ApprovalStore()

    def compare(
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
        store = KnowledgeStore()
        methods = self.registry.refresh()
        methods = [
            method
            for method in methods
            if method.get("enabled_for_research", True)
        ]
        self.approval_store.merge_methods(
            method
            for method in methods
            if not method.get("internal_only")
        )

        rendered_methods: List[Dict[str, object]] = []
        for method in methods:
            adapter = get_adapter(method)
            result = adapter.analyze(
                first_name=first_name,
                last_name=last_name,
                day=day,
                month=month,
                year=year,
                gender=gender,
                hebrew_birthdate=hebrew_birthdate,
            )
            method_result = dict(method)
            method_result["enabled_for_customers"] = self.approval_store.get_status(
                str(method["key"]),
                default=bool(method.get("enabled_for_customers", False)),
            )
            method_result["resolved_adapter"] = adapter.__class__.__name__
            method_result["resolved_corpus"] = str(getattr(adapter, "_corpus", "") or method.get("key") or "")
            method_result["result"] = result
            rendered_methods.append(method_result)

        baseline_result = next(
            (
                method.get("result", {})
                for method in rendered_methods
                if method.get("key") == INTERNAL_BASELINE_KEY
            ),
            {},
        )
        baseline_sections = [
            section
            for section in list(baseline_result.get("report_sections") or [])
            if str(section.get("key") or "").strip().lower() not in {"next_step", "next step"}
        ]
        public_methods = [
            method
            for method in rendered_methods
            if not method.get("internal_only") and method.get("visible_in_research_ui", True)
        ]
        active_alias_map = _build_alias_to_key(public_methods)
        active_corpora = sorted(active_alias_map.keys())
        book_evidence_sections = _build_book_evidence_sections(
            store=store,
            rendered_methods=public_methods,
            active_corpora=active_corpora,
            pythagorean_result=baseline_result,
            first_name=first_name,
            last_name=last_name,
            day=day,
            month=month,
            year=year,
            gender=gender,
            limit=10,
        )

        comparison_rows = []
        for row_key, row_label in DEFAULT_ROWS:
            comparison_rows.append(
                {
                    "key": row_key,
                    "label": row_label,
                    "values": {
                        method["key"]: method["result"]["metrics"].get(row_key, "-")
                        for method in public_methods
                    },
                }
            )

        return {
            "inputs": {
                "first_name": first_name,
                "last_name": last_name,
                "day": day,
                "month": month,
                "year": year,
                "gender": gender,
                "hebrew_birthdate": hebrew_birthdate or {},
            },
            "methods": public_methods,
            "rows": comparison_rows,
            "report_sections": baseline_sections + book_evidence_sections,
            "report_summary": {
                **dict(baseline_result.get("report_summary") or {}),
                "book_evidence_count": len(book_evidence_sections),
                "book_evidence_corpora": sorted({
                    _source_to_corpus_key(section.get("source"), active_alias_map)
                    for section in book_evidence_sections
                    if _source_to_corpus_key(section.get("source"), active_alias_map)
                }),
            },
        }
