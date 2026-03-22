"""Comparison engine for research-only numerology methods."""

from __future__ import annotations

from typing import Dict, List, Optional

from .approval_store import ApprovalStore
from .method_adapters import get_adapter
from .method_registry import MethodRegistry
from book_ingestion.knowledge_store import KnowledgeStore


DEFAULT_ROWS = [
    ("destiny", "שביל גורל"),
    ("name_total", "מספר השם"),
    ("soul", "ביטוי פנימי"),
    ("outer", "ביטוי חיצוני"),
    ("personal_year", "שנה אישית / מצב"),
    ("hidden_year", "שכבה נסתרת / נפח"),
    ("missing", "פערים"),
    ("beneficial", "חוזקות"),
    ("surplus", "עודפים / עומס"),
    ("corpus_size", "חומרי מקור"),
    ("top_themes", "תמות מובילות"),
    ("media_mix", "סוגי קבצים"),
    ("readiness", "מוכנות"),
    ("next_step", "השלב הבא"),
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
        summary = _short_text(result.get("summary") or "", 220)
        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        if method_key and method_key != "pythagorean_existing":
            query_parts.extend([method_key, display_name])
            if summary:
                _add_report_section(
                    sections,
                    seen,
                    key=f"method_summary:{method_key}",
                    title=f"{display_name} · סיכום",
                    value=summary,
                    meaning=f"ספר/קורפוס פעיל למחקר עם {len(details)} חוקים מאומתים.",
                    source=f"interpretations/{method_key}",
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
                    source=f"interpretations/{method_key}/{detail_key}",
                )

    query = " ".join(part for part in query_parts if str(part or "").strip())
    if query:
        try:
            memory_hits = store.search_memory(query, corpus=None, limit=max(8, limit * 2))
        except Exception:
            memory_hits = []
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
        methods = self.registry.list_methods(research_only=True)
        self.approval_store.merge_methods(methods)

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
            method_result["result"] = result
            rendered_methods.append(method_result)

        pythagorean_result = next(
            (
                method.get("result", {})
                for method in rendered_methods
                if method.get("key") == "pythagorean_existing"
            ),
            {},
        )
        pythagorean_sections = [
            section
            for section in list(pythagorean_result.get("report_sections") or [])
            if str(section.get("key") or "").strip().lower() not in {"next_step", "next step", "השלב הבא"}
        ]
        book_evidence_sections = _build_book_evidence_sections(
            store=store,
            rendered_methods=rendered_methods,
            pythagorean_result=pythagorean_result,
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
                        for method in rendered_methods
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
            "methods": rendered_methods,
            "rows": comparison_rows,
            "report_sections": pythagorean_sections + book_evidence_sections,
            "report_summary": {
                **dict(pythagorean_result.get("report_summary") or {}),
                "book_evidence_count": len(book_evidence_sections),
                "book_evidence_corpora": sorted({
                    str(section.get("source") or "").split("/")[1]
                    if str(section.get("source") or "").startswith("interpretations/")
                    else str(section.get("source") or "").strip()
                    for section in book_evidence_sections
                    if str(section.get("source") or "").strip()
                }),
            },
        }
