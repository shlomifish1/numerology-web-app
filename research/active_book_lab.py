from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import streamlit as st

from interpretation_layout import RESEARCH_ROOT, normalize_corpus_key
from book_ingestion import WeakBookReviewOrchestrator

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None

from .stale_cleanup import cleanup_stale_research_state


_PAGE_MARKER_RE = re.compile(
    r"^---\s*Page\s*(\d+)(?:\s*\((.*?)\))?\s*---\s*$",
    re.MULTILINE,
)

_BASELINE_RULES = [
    {"key": "destiny", "label_he": "שביל גורל", "aliases": {"destiny", "life_path", "destiny_path", "shvil_goral", "שביל_הגורל"}},
    {"key": "birth_day", "label_he": "יום לידה", "aliases": {"birth_day", "birth_number", "מספר_לידה_אזרחי", "חישוב_מספר_הלידה"}},
    {"key": "name_total", "label_he": "מספר השם", "aliases": {"name_total", "human_aspiration", "full_name", "expression", "expression_of_the_soul"}},
    {"key": "outer", "label_he": "ביטוי חיצוני", "aliases": {"outer", "consonants", "personality_number", "outward_behavior", "outer_behavior"}},
    {"key": "soul", "label_he": "ביטוי פנימי", "aliases": {"soul", "vowels", "soul_expression", "soul_expression_number", "expression_of_the_soul"}},
    {"key": "personal_year", "label_he": "שנה אישית", "aliases": {"personal_year", "annual_influence", "yearly_life_path_number"}},
    {"key": "hidden_year", "label_he": "שנה נסתרת", "aliases": {"hidden_year"}},
    {"key": "peaks", "label_he": "פסגות", "aliases": {"peaks", "pinnacle", "pinnacles"}},
    {"key": "challenges", "label_he": "אתגרים", "aliases": {"challenge", "challenges"}},
    {"key": "peak_challenge_comb", "label_he": "שילוב פסגה-אתגר", "aliases": {"peak_challenge_comb", "peak_challenge", "balance_point"}},
    {"key": "quarters", "label_he": "רבעונים", "aliases": {"quarters", "quarterly_division", "bi_monthly_division", "tri_monthly_division"}},
]

_SUBJECT_RESOLVERS = {
    "destiny": lambda calc: calc.final_number_destiny,
    "life_path": lambda calc: calc.final_number_destiny,
    "destiny_path": lambda calc: calc.final_number_destiny,
    "shvil_goral": lambda calc: calc.final_number_destiny,
    "birth_day": lambda calc: calc.p_day,
    "birth_number": lambda calc: calc.p_day,
    "name_total": lambda calc: calc.full_name_val,
    "human_aspiration": lambda calc: calc.full_name_val,
    "outer": lambda calc: calc.itzurim_val,
    "consonants": lambda calc: calc.itzurim_val,
    "personality_number": lambda calc: calc.itzurim_val,
    "soul": lambda calc: calc.aiv_val,
    "vowels": lambda calc: calc.aiv_val,
    "expression_of_the_soul": lambda calc: calc.aiv_val,
    "soul_expression": lambda calc: calc.aiv_val,
    "soul_expression_number": lambda calc: calc.aiv_val,
    "personal_year": lambda calc: calc.shana_ishit,
    "annual_influence": lambda calc: calc.shana_ishit,
    "hidden_year": lambda calc: calc.shana_nisteret,
    "peaks": lambda calc: [calc.peak1_reduced, calc.peak2_reduced, calc.peak3_reduced, calc.peak4_reduced],
    "pinnacle": lambda calc: [calc.peak1_reduced, calc.peak2_reduced, calc.peak3_reduced, calc.peak4_reduced],
    "challenge": lambda calc: [calc.challenge1_reduced, calc.challenge2_reduced, calc.challenge3_reduced, calc.challenge4_reduced],
    "challenges": lambda calc: [calc.challenge1_reduced, calc.challenge2_reduced, calc.challenge3_reduced, calc.challenge4_reduced],
    "quarters": lambda calc: [calc.first_quarter_reduced, calc.second_quarter_reduced, calc.third_quarter_reduced, calc.forth_quarter_reduced],
}


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize_corpus_key(value)).strip("_")


def _artifact_path(book_root: Path, suffix: str) -> Path:
    return book_root / f"{book_root.name}{suffix}"


def _ensure_valid_session_choice(session_key: str, options: Iterable[Any]) -> None:
    valid_values = {str(item) for item in options}
    if session_key in st.session_state and str(st.session_state.get(session_key)) not in valid_values:
        del st.session_state[session_key]


def _book_dir_candidates() -> list[Path]:
    if not RESEARCH_ROOT.exists():
        return []
    return sorted(
        path
        for path in RESEARCH_ROOT.iterdir()
        if path.is_dir() and path.name != "raw_books"
    )


def _list_active_books() -> list[dict[str, Any]]:
    books: list[dict[str, Any]] = []
    for book_root in _book_dir_candidates():
        draft = _read_json(_artifact_path(book_root, "__draft_catalog.json"), {})
        reviewed = _read_json(_artifact_path(book_root, "__reviewed_catalog.json"), {})
        review_report = _read_json(_artifact_path(book_root, "__review_report.json"), {})
        chapter_inventory = _read_json(_artifact_path(book_root, "__chapter_inventory.json"), {})
        books.append(
            {
                "book_id": normalize_corpus_key(book_root.name),
                "book_title": book_root.name,
                "book_root": book_root,
                "chapter_count": len(list(chapter_inventory.get("chapters") or [])),
                "draft_count": len(list(draft.get("calculations") or [])),
                "reviewed_count": len(list(reviewed.get("calculations") or [])),
                "report_ready": bool(review_report),
            }
        )
    return books


def _resolve_book_root(book_key: str) -> Path | None:
    normalized = normalize_corpus_key(book_key)
    for book_root in _book_dir_candidates():
        aliases = {
            book_root.name,
            normalize_corpus_key(book_root.name),
        }
        if book_key in aliases or normalized in aliases:
            return book_root
    return None


def _merge_calc_entry(draft_entry: dict[str, Any], reviewed_entry: dict[str, Any]) -> dict[str, Any]:
    merged = dict(draft_entry)
    merged.update({key: value for key, value in reviewed_entry.items() if key != "_draft_ref"})
    merged["_draft_ref"] = dict(reviewed_entry.get("_draft_ref") or {})
    return merged


def _formula_present(entry: dict[str, Any]) -> bool:
    if str(entry.get("formula_text") or "").strip():
        return True
    return bool(list(entry.get("formula_steps") or []))


def _interpretations_present(entry: dict[str, Any]) -> bool:
    result_values = list(entry.get("result_values") or [])
    if result_values:
        return True
    definition_rows = list(((entry.get("interpretations_by_value") or {}) or {}).items())
    return bool(definition_rows)


def _result_values_present(entry: dict[str, Any]) -> bool:
    return bool(list(entry.get("allowed_result_values") or []))


def _status_for_calc(entry: dict[str, Any]) -> str:
    review_bucket = str(entry.get("review_bucket") or "").strip().lower()
    if review_bucket == "false_positive":
        return "סומן כלא רלוונטי"

    formula_present = _formula_present(entry)
    interpretations_present = _interpretations_present(entry)
    result_values_present = _result_values_present(entry)
    needs_review = bool(entry.get("needs_review", True))

    if formula_present and interpretations_present and result_values_present and not needs_review:
        return "נמצא"
    if formula_present and not interpretations_present:
        return "חסר פירושים"
    if formula_present and interpretations_present and not result_values_present:
        return "חסר ערכי תוצאה"
    if not formula_present and (interpretations_present or result_values_present or int(entry.get("evidence_count") or 0) > 0):
        return "חסר נוסחה"
    if needs_review:
        return "נדרש review"
    return "נמצא"


def _catalog_rows(book_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    draft_by_key = {
        str(item.get("calc_key") or "").strip(): dict(item)
        for item in list((book_bundle.get("draft_catalog") or {}).get("calculations") or [])
        if str(item.get("calc_key") or "").strip()
    }
    reviewed_by_key = {
        str(item.get("calc_key") or "").strip(): dict(item)
        for item in list((book_bundle.get("reviewed_catalog") or {}).get("calculations") or [])
        if str(item.get("calc_key") or "").strip()
    }
    keys = sorted(set(draft_by_key) | set(reviewed_by_key))
    rows: list[dict[str, Any]] = []
    for calc_key in keys:
        merged = _merge_calc_entry(draft_by_key.get(calc_key, {}), reviewed_by_key.get(calc_key, {}))
        rows.append(
            {
                "calc_key": calc_key,
                "label_he": str(merged.get("label_he") or calc_key),
                "status": _status_for_calc(merged),
                "needs_review": bool(merged.get("needs_review", True)),
                "formula_present": _formula_present(merged),
                "interpretations_present": _interpretations_present(merged),
                "result_values_present": _result_values_present(merged),
                "source_refs": list(merged.get("source_refs") or []),
                "chapter_refs": list(merged.get("chapter_refs") or ([merged.get("chapter_ref")] if merged.get("chapter_ref") else [])),
                "entry": merged,
            }
        )
    return rows


def _baseline_gap_rows(book_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _catalog_rows(book_bundle)
    by_normalized = {
        _normalize_key(row["calc_key"]): row
        for row in rows
    }
    gaps: list[dict[str, Any]] = []
    for rule in _BASELINE_RULES:
        matched_rows = [
            by_normalized[alias]
            for alias in {_normalize_key(item) for item in rule["aliases"]}
            if alias in by_normalized
        ]
        if not matched_rows:
            gaps.append(
                {
                    "baseline_key": rule["key"],
                    "label_he": rule["label_he"],
                    "status": "לא זוהה בספר",
                    "matched_calc_keys": "",
                }
            )
            continue
        preferred = next((row for row in matched_rows if row["status"] == "נמצא"), matched_rows[0])
        gaps.append(
            {
                "baseline_key": rule["key"],
                "label_he": rule["label_he"],
                "status": preferred["status"],
                "matched_calc_keys": ", ".join(sorted({row["calc_key"] for row in matched_rows})),
            }
        )
    return gaps


def _internal_gap_rows(book_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "calc_key": row["calc_key"],
            "label_he": row["label_he"],
            "status": row["status"],
            "chapter_refs": ", ".join(row["chapter_refs"]),
        }
        for row in _catalog_rows(book_bundle)
        if row["status"] != "נמצא"
    ]


def _parse_pages(source_text: str) -> list[dict[str, Any]]:
    matches = list(_PAGE_MARKER_RE.finditer(source_text or ""))
    if not matches:
        clean = str(source_text or "").strip()
        return [{"page_number": 1, "header": "", "text": clean}] if clean else []

    pages: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        header = str(match.group(2) or "").strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
        text = source_text[start:end].strip()
        pages.append(
            {
                "page_number": page_number,
                "header": header,
                "text": text,
            }
        )
    return pages


def _chapter_key_from_pdf(pdf_path: Path) -> str:
    return normalize_corpus_key(pdf_path.stem)


def _chapter_bundle(book_root: Path, pdf_path: Path) -> dict[str, Any]:
    chapter_dir = book_root / "artifacts" / "chapters" / _chapter_key_from_pdf(pdf_path)
    chapter_title = pdf_path.stem.strip()
    return {
        "chapter_dir": chapter_dir,
        "chapter_title": chapter_title,
        "pdf_path": pdf_path,
        "source_manifest": _read_json(chapter_dir / f"{chapter_title}__source_manifest.json", {}),
        "source_corpus": (chapter_dir / f"{chapter_title}__source_corpus.txt").read_text(encoding="utf-8") if (chapter_dir / f"{chapter_title}__source_corpus.txt").exists() else "",
        "draft_catalog": _read_json(chapter_dir / f"{chapter_title}__draft_catalog.json", {}),
        "calc_candidates": _read_json(chapter_dir / f"{chapter_title}__calc_candidates.json", []),
    }


def _load_weak_review_report(book_root: Path) -> dict[str, Any]:
    return _read_json(_artifact_path(book_root, "__weak_review_report.json"), {})


def _render_weak_review_summary(report: dict[str, Any]) -> None:
    if not report:
        st.info("עדיין לא קיים דוח weak review עבור הספר הזה.")
        return

    cols = st.columns(4)
    cols[0].metric("Weak בתחילה", int(report.get("initial_weak_chapter_count") or 0))
    cols[1].metric("Weak כעת", int(report.get("final_weak_chapter_count") or 0))
    cols[2].metric("פרקים שהתאוששו", int(report.get("recovered_chapter_count") or 0))
    cols[3].metric("ריצות recovery", len(list(report.get("chapter_runs") or [])))

    next_actions = list(report.get("next_actions") or [])
    if next_actions:
        st.markdown("**פעולות המשך**")
        for action in next_actions:
            st.write(f"- {action}")

    final_weak = list(report.get("final_weak_chapters") or [])
    if final_weak:
        st.markdown("**פרקים שעדיין חלשים**")
        st.table(
            {
                "פרק": [item.get("chapter_title", "") for item in final_weak],
                "סיבות": [", ".join(item.get("weak_reasons") or []) for item in final_weak],
                "אורך טקסט": [item.get("text_length", 0) for item in final_weak],
                "חישובים": [item.get("calculation_count", 0) for item in final_weak],
            }
        )

    with st.expander("נתיבי דוחות weak review", expanded=False):
        book_root = Path(report.get("book_root") or "") if report.get("book_root") else None
        st.json(
            {
                "report_json": str(book_root / f"{book_root.name}__weak_review_report.json") if book_root else "",
                "catalog_path": str(report.get("catalog_path") or ""),
                "global_catalog_path": str(report.get("global_catalog_path") or ""),
            }
        )

def _load_book_bundle(book_key: str) -> dict[str, Any] | None:
    book_root = _resolve_book_root(book_key)
    if not book_root:
        return None
    pdf_paths = sorted(book_root.glob("*.pdf"))
    return {
        "book_id": normalize_corpus_key(book_root.name),
        "book_title": book_root.name,
        "book_root": book_root,
        "draft_catalog": _read_json(_artifact_path(book_root, "__draft_catalog.json"), {}),
        "reviewed_catalog": _read_json(_artifact_path(book_root, "__reviewed_catalog.json"), {}),
        "definition_candidate": _read_json(_artifact_path(book_root, "__definition_candidate.json"), {}),
        "review_report": _read_json(_artifact_path(book_root, "__review_report.json"), {}),
        "chapter_inventory": _read_json(_artifact_path(book_root, "__chapter_inventory.json"), {}),
        "pdf_paths": pdf_paths,
    }


def _page_image_bytes(pdf_path: Path, page_number: int) -> bytes | None:
    if fitz is None:
        return None
    if not pdf_path.exists():
        return None
    try:
        with fitz.open(str(pdf_path)) as document:
            if page_number < 1 or page_number > document.page_count:
                return None
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
            return pixmap.tobytes("png")
    except Exception:
        return None


def _page_related_items(chapter_bundle: dict[str, Any], page_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    compact = re.sub(r"\s+", " ", str(page_text or "")).strip()
    if not compact:
        return [], []

    page_candidates: list[dict[str, Any]] = []
    for item in list(chapter_bundle.get("calc_candidates") or []):
        snippet = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if snippet and (snippet[:100] in compact or compact[:180] in snippet):
            page_candidates.append(item)

    calc_rows = []
    for item in list((chapter_bundle.get("draft_catalog") or {}).get("calculations") or []):
        excerpt = re.sub(r"\s+", " ", str(item.get("source_excerpt") or "")).strip()
        if excerpt and (excerpt[:100] in compact or compact[:180] in excerpt):
            calc_rows.append(item)
    if not calc_rows:
        calc_rows = list((chapter_bundle.get("draft_catalog") or {}).get("calculations") or [])[:6]

    return page_candidates[:8], calc_rows[:8]


def _subject_value(calc: Any, calc_key: str) -> Any:
    resolver = _SUBJECT_RESOLVERS.get(calc_key)
    if resolver:
        return resolver(calc)
    normalized = _normalize_key(calc_key)
    for alias, candidate in _SUBJECT_RESOLVERS.items():
        if normalized == _normalize_key(alias):
            return candidate(calc)
    return None


def _subject_rows(book_bundle: dict[str, Any], calc: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for catalog_row in _catalog_rows(book_bundle):
        value = _subject_value(calc, catalog_row["calc_key"])
        if value in (None, "", [], ()):
            continue
        rows.append(
            {
                "calc_key": catalog_row["calc_key"],
                "label_he": catalog_row["label_he"],
                "status": catalog_row["status"],
                "value": " / ".join(str(item) for item in value) if isinstance(value, (list, tuple)) else str(value),
                "chapter_refs": ", ".join(catalog_row["chapter_refs"]),
            }
        )
    return rows


def _book_selectbox(prefix: str, books: list[dict[str, Any]]) -> str:
    default_book = books[0]["book_title"]
    labels = {book["book_title"]: book["book_title"] for book in books}
    options = [book["book_title"] for book in books]
    _ensure_valid_session_choice(f"{prefix}_book", options)
    return st.selectbox(
        "בחר ספר",
        options=options,
        index=options.index(default_book),
        key=f"{prefix}_book",
        format_func=lambda value: labels.get(value, value),
    )

def render_lab_panel(*, prefix: str, calc: Any | None = None) -> None:
    cleanup_summary = cleanup_stale_research_state()
    books = _list_active_books()
    if not books:
        st.warning("לא נמצאו ספרי מחקר פעילים.")
        return

    chosen_book = _book_selectbox(prefix, books)
    book_bundle = _load_book_bundle(chosen_book)
    if not book_bundle:
        st.error("לא ניתן לטעון את ספר המחקר שנבחר.")
        return

    catalog_rows = _catalog_rows(book_bundle)
    baseline_gaps = _baseline_gap_rows(book_bundle)
    internal_gaps = _internal_gap_rows(book_bundle)
    weak_review_report = _load_weak_review_report(book_bundle["book_root"])

    st.caption(
        "ניקוי אוטומטי: "
        f"הוסרו {cleanup_summary['removed_map_entries']} רשומות מפה, "
        f"{cleanup_summary['removed_map_notes']} הערות, "
        f"{cleanup_summary['removed_map_versions']} גרסאות שמורות, "
        f"ו-{cleanup_summary['removed_history_rows']} רשומות היסטוריה לא פעילות."
    )

    metrics = st.columns(4)
    metrics[0].metric("ספר נבחר", book_bundle["book_title"])
    metrics[1].metric("פרקים", len(book_bundle["pdf_paths"]))
    metrics[2].metric("חישובים בקטלוג", len(catalog_rows))
    metrics[3].metric("פערים פנימיים", len(internal_gaps))

    action_col1, action_col2 = st.columns([1, 2])
    with action_col1:
        allow_paid_fallback = st.checkbox(
            "אפשר גם API בתשלום אם החינמיים לא הצליחו",
            value=False,
            key=f"{prefix}_allow_paid_weak_review",
        )
        if st.button("הרץ ריויו אוטומטי לספר הפעיל", type="primary", key=f"{prefix}_run_weak_review"):
            with st.spinner("מריץ weak review, recovery, ועדכון דוחות חיים..."):
                try:
                    report = WeakBookReviewOrchestrator(
                        book_bundle["book_root"],
                        allow_paid_fallback=allow_paid_fallback,
                        sync_book_pipeline=True,
                    ).run()
                except Exception as exc:
                    st.error(f"הרצת weak review נכשלה: {exc}")
                else:
                    st.success(
                        "ה-weak review הושלם. "
                        f"פרקים חלשים בתחילה: {report.get('initial_weak_chapter_count', 0)} | "
                        f"נשארו חלשים: {report.get('final_weak_chapter_count', 0)}"
                    )
                    st.rerun()
    with action_col2:
        st.markdown("**דוח weak review האחרון**")
        _render_weak_review_summary(weak_review_report)

    tab_catalog, tab_missing, tab_subject = st.tabs(
        ["בונה חישובים מתוך ספר", "חוקים חסרים", "תוצאות ספר לנבדק הפעיל"]
    )

    with tab_catalog:
        st.markdown("**קטלוג מחקרי מתקדם**")
        with st.expander("Artifacts חיים של הספר", expanded=False):
            st.json(
                {
                    "draft_catalog": str(_artifact_path(book_bundle["book_root"], "__draft_catalog.json")),
                    "reviewed_catalog": str(_artifact_path(book_bundle["book_root"], "__reviewed_catalog.json")),
                    "definition_candidate": str(_artifact_path(book_bundle["book_root"], "__definition_candidate.json")),
                    "review_report": str(_artifact_path(book_bundle["book_root"], "__review_report.json")),
                }
            )
        st.table(
            {
                "calc_key": [row["calc_key"] for row in catalog_rows],
                "תווית": [row["label_he"] for row in catalog_rows],
                "סטטוס": [row["status"] for row in catalog_rows],
                "פירושים": ["כן" if row["interpretations_present"] else "לא" for row in catalog_rows],
                "נוסחה": ["כן" if row["formula_present"] else "לא" for row in catalog_rows],
            }
        )
        calc_options = [row["calc_key"] for row in catalog_rows]
        _ensure_valid_session_choice(f"{prefix}_calc", calc_options)
        selected_calc_key = st.selectbox(
            "בחר חישוב לעיון",
            options=calc_options,
            key=f"{prefix}_calc",
        )
        selected_row = next((row for row in catalog_rows if row["calc_key"] == selected_calc_key), None)
        if selected_row:
            entry = selected_row["entry"]
            st.markdown(f"**{selected_row['label_he']}**")
            st.caption(f"סטטוס: {selected_row['status']}")
            st.write(str(entry.get("short_explanation") or ""))
            st.markdown("**מקורות**")
            st.write(", ".join(selected_row["source_refs"]) or "אין")
            st.markdown("**פרקים**")
            st.write(", ".join(selected_row["chapter_refs"]) or "אין")
            st.markdown("**excerpt**")
            st.write(str(entry.get("source_excerpt") or "אין"))
            with st.expander("Raw JSON"):
                st.json(json.loads(json.dumps(entry, ensure_ascii=False)))

    with tab_missing:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**פער מול המפה הראשית**")
            st.table(
                {
                    "חישוב בסיס": [row["label_he"] for row in baseline_gaps],
                    "סטטוס": [row["status"] for row in baseline_gaps],
                    "התאמה בספר": [row["matched_calc_keys"] for row in baseline_gaps],
                }
            )
        with col2:
            st.markdown("**פער פנימי מול הספר הנבחר**")
            st.table(
                {
                    "calc_key": [row["calc_key"] for row in internal_gaps],
                    "תווית": [row["label_he"] for row in internal_gaps],
                    "סטטוס": [row["status"] for row in internal_gaps],
                    "פרקים": [row["chapter_refs"] for row in internal_gaps],
                }
            )

    with tab_subject:
        if calc is None:
            st.info("לא חושב עדיין נבדק פעיל, לכן מוצג רק הקטלוג של הספר.")
        else:
            subject_rows = _subject_rows(book_bundle, calc)
            if not subject_rows:
                st.info("לא נמצאו חישובים בספר שניתן לקשור כרגע לנבדק הפעיל.")
            else:
                st.table(
                    {
                        "חישוב": [row["label_he"] for row in subject_rows],
                        "ערך לנבדק": [row["value"] for row in subject_rows],
                        "סטטוס בספר": [row["status"] for row in subject_rows],
                        "פרקים": [row["chapter_refs"] for row in subject_rows],
                    }
                )

    book_bundle = _load_book_bundle(chosen_book)
    if not book_bundle:
        st.error("לא ניתן לטעון את הספר שנבחר.")
        return

    pdf_paths = list(book_bundle["pdf_paths"])
    if not pdf_paths:
        st.info("אין עדיין פרקי PDF תחת הספר הזה.")
        return

    _ensure_valid_session_choice(f"{prefix}_chapter", pdf_paths)
    chapter_path = st.selectbox(
        "בחר פרק",
        options=pdf_paths,
        key=f"{prefix}_chapter",
        format_func=lambda path: Path(path).stem.strip(),
    )
    chapter_bundle = _chapter_bundle(book_bundle["book_root"], Path(chapter_path))
    pages = _parse_pages(str(chapter_bundle.get("source_corpus") or ""))
    if not pages:
        st.warning("לא נמצאו עמודים מפוענחים עבור הפרק הזה.")
        return

    page_numbers = [page["page_number"] for page in pages]
    _ensure_valid_session_choice(f"{prefix}_page", page_numbers)
    selected_page_number = st.selectbox(
        "בחר עמוד",
        options=page_numbers,
        key=f"{prefix}_page",
    )
    selected_page = next(page for page in pages if page["page_number"] == selected_page_number)
    page_candidates, page_calculations = _page_related_items(chapter_bundle, selected_page["text"])
    image_bytes = _page_image_bytes(Path(chapter_path), selected_page_number)

    top_cols = st.columns(4)
    top_cols[0].metric("ספר", book_bundle["book_title"])
    top_cols[1].metric("פרק", Path(chapter_path).stem.strip())
    top_cols[2].metric("עמוד", selected_page_number)
    top_cols[3].metric("מועמדים בעמוד", len(page_candidates))

    if image_bytes:
        st.markdown("**תמונת עמוד**")
        st.image(image_bytes, use_container_width=True)
    else:
        st.caption("אין כרגע תצוגת תמונה לעמוד הזה, מוצג OCR בלבד.")

    st.markdown("**טקסט OCR**")
    if selected_page.get("header"):
        st.caption(selected_page["header"])
    st.text_area(
        "page_text",
        value=selected_page["text"],
        height=320,
        label_visibility="collapsed",
    )

    detail_col1, detail_col2 = st.columns(2)
    with detail_col1:
        st.markdown("**חישובים שזוהו בפרק/עמוד**")
        if page_calculations:
            st.table(
                {
                    "calc_key": [item.get("calc_key", "") for item in page_calculations],
                    "תווית": [item.get("label_he", "") for item in page_calculations],
                    "מקור": [", ".join(item.get("source_refs") or []) for item in page_calculations],
                }
            )
        else:
            st.info("לא זוהו חישובים קשורים לעמוד הזה.")
    with detail_col2:
        st.markdown("**קטעי מקור רלוונטיים**")
        if page_candidates:
            for item in page_candidates:
                st.caption(
                    f"פסקה {item.get('paragraph_index', '-')} | {', '.join(item.get('reasons') or [])}"
                )
                st.write(str(item.get("text") or ""))
                st.divider()
        else:
            st.info("לא נמצאו קטעי מקור ממוקדים לעמוד הזה.")

    if calc is not None:
        subject_rows = _subject_rows(book_bundle, calc)
        if subject_rows:
            st.markdown("**תוצאות רלוונטיות לנבדק הפעיל**")
            st.table(
                {
                    "חישוב": [row["label_he"] for row in subject_rows],
                    "ערך לנבדק": [row["value"] for row in subject_rows],
                    "סטטוס בספר": [row["status"] for row in subject_rows],
                }
            )
