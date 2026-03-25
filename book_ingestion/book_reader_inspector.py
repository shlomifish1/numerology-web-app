"""Read and inspect the generated book reader SQLite index inside Streamlit."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERPRETATIONS_ROOT = PROJECT_ROOT / "interpretations"

GENERIC_NAME_PATTERNS = (
    r"^pdf$",
    r"^scan$",
    r"^document$",
    r"^\d+$",
    r"^\d+\s*-\s*\d+$",
    r"^\d+\s*עד\s*\d+$",
)


def _looks_generic_book_name(pdf_name: str) -> bool:
    stem = Path(pdf_name).stem.strip().lower()
    if not stem:
        return True
    if any(re.fullmatch(pattern, stem) for pattern in GENERIC_NAME_PATTERNS):
        return True
    if len(stem) <= 3:
        return True
    if sum(ch.isdigit() for ch in stem) >= max(2, len(stem) // 2):
        return True
    return False


def _score_title_candidate(candidate: str) -> int:
    text = re.sub(r"\s+", " ", str(candidate or "")).strip()
    if not text:
        return -100
    lower = text.lower()
    hebrew = sum(1 for ch in text if "\u0590" <= ch <= "\u05FF")
    latin = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    digits = sum(1 for ch in text if ch.isdigit())
    words = len(text.split())
    score = hebrew * 5 + words * 2 - latin * 2 - digits * 2
    if len(text) > 80:
        score -= 6
    if any(token in lower for token in ("table of contents", "summary", "chapter", "page", "toc")):
        score -= 20
    if any(token in text for token in ("תוכן עניינים", "מבוא", "נומרולוגיה", "אסטרולוגיה", "הקוד")):
        score += 8
    return score


def _is_generic_folder_name(folder_name: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(folder_name or "")).strip().lower()
    if not normalized:
        return True
    generic_terms = (
        "chapter",
        "chapters",
        "part",
        "pages",
        "page",
        "ocr",
        "scan",
        "pdf",
        "txt",
        "חלק",
        "פרק",
        "עמוד",
        "עמודים",
    )
    if normalized in generic_terms:
        return True
    if re.fullmatch(r"^[\d\s\-–—_]+$", normalized):
        return True
    return False


def _find_source_file(pdf_name: str) -> Optional[Path]:
    if not INTERPRETATIONS_ROOT.exists():
        return None
    target = Path(pdf_name).name
    matches = list(INTERPRETATIONS_ROOT.rglob(target))
    if not matches:
        stem = Path(pdf_name).stem
        matches = list(INTERPRETATIONS_ROOT.rglob(f"{stem}.*"))
    if not matches:
        return None
    matches.sort(key=lambda path: (len(path.parts), str(path).lower()))
    return matches[0]


def _book_title_from_source_path(source_path: Path) -> Optional[str]:
    current = source_path.parent
    while current and current != INTERPRETATIONS_ROOT.parent:
        if current == INTERPRETATIONS_ROOT:
            break
        if not _is_generic_folder_name(current.name):
            return current.name
        current = current.parent
    return None


def _is_plausible_book_title(candidate: str) -> bool:
    text = re.sub(r"\s+", " ", str(candidate or "")).strip()
    if not text:
        return False
    hebrew = sum(1 for ch in text if "\u0590" <= ch <= "\u05FF")
    latin = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    digits = sum(1 for ch in text if ch.isdigit())
    words = len(text.split())
    if hebrew < 8 or words < 3:
        return False
    if latin > hebrew:
        return False
    if digits > 6:
        return False
    return True


def _infer_book_title(pdf_name: str) -> Optional[str]:
    source_path = _find_source_file(pdf_name)
    if source_path:
        folder_title = _book_title_from_source_path(source_path)
        if folder_title and not _looks_generic_book_name(folder_title):
            return folder_title

    best_title: Optional[str] = None
    best_score = -10_000
    with _connect() as conn:
        page_rows = conn.execute(
            "SELECT page_num, raw_text FROM pages WHERE pdf_name = ? ORDER BY page_num LIMIT 5",
            (pdf_name,),
        ).fetchall()
        entry_rows = conn.execute(
            """
            SELECT title, content
            FROM entries
            WHERE page_refs LIKE ?
            ORDER BY sort_key, number, title COLLATE NOCASE
            """,
            (f"%{pdf_name}:%",),
        ).fetchall()

    candidates: List[str] = []
    for row in page_rows:
        raw_text = str(row["raw_text"] or "")
        for line in raw_text.splitlines()[:12]:
            cleaned = re.sub(r"^\s*[\W_\d]+", "", line).strip()
            if cleaned:
                candidates.append(cleaned)
    for row in entry_rows[:40]:
        title = str(row["title"] or "").strip()
        if title:
            candidates.append(title)
        content = str(row["content"] or "").strip()
        if content:
            first_line = content.splitlines()[0].strip()
            if first_line:
                candidates.append(first_line)

    for candidate in candidates:
        score = _score_title_candidate(candidate)
        if score > best_score:
            best_title = candidate
            best_score = score

    if best_title and _score_title_candidate(best_title) > 0 and _is_plausible_book_title(best_title):
        return best_title
    return None


def _format_book_label(pdf_name: str, title_guess: Optional[str]) -> str:
    source_name = Path(pdf_name).stem or pdf_name
    if title_guess and _looks_generic_book_name(pdf_name):
        return f"{title_guess} · מקור: {source_name}"
    if title_guess and title_guess != source_name:
        return f"{title_guess} · מקור: {source_name}"
    if _looks_generic_book_name(pdf_name):
        return f"ספר לא מזוהה · מקור: {source_name}"
    return source_name


def resolve_db_path() -> Path:
    """Locate the book reader database.

    Preference order:
    1. BOOK_READER_DB_PATH env var
    2. local ai_agents project copy
    3. NumerologyReportGenerator project copy
    4. legacy desktop test-books copy
    """
    candidates = []
    env_path = os.getenv("BOOK_READER_DB_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))

    project_root = Path(__file__).resolve().parents[1]
    candidates.append(project_root.parent / "book_knowledge.db")
    candidates.append(project_root / "book_knowledge.db")

    legacy_path = project_root.parent.parent / "test books" / "book_reader" / "book_knowledge.db"
    candidates.append(legacy_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _connect() -> sqlite3.Connection:
    db_path = resolve_db_path()
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_stats() -> Dict[str, int]:
    with _connect() as conn:
        pages = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END), 0) AS done,
                COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END), 0) AS pending,
                COALESCE(SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END), 0) AS processing,
                COALESCE(SUM(CASE WHEN status='error' THEN 1 ELSE 0 END), 0) AS error_count
            FROM pages
            """
        ).fetchone()
        entries = conn.execute("SELECT COUNT(*) AS count FROM entries").fetchone()
        pages_dict = dict(pages) if pages else {}
        entries_dict = dict(entries) if entries else {}
        return {
            "total_pages": int(pages_dict.get("total", 0)),
            "done_pages": int(pages_dict.get("done", 0)),
            "pending_pages": int(pages_dict.get("pending", 0)),
            "processing_pages": int(pages_dict.get("processing", 0)),
            "error_pages": int(pages_dict.get("error_count", 0)),
            "entry_count": int(entries_dict.get("count", 0)),
        }


def list_books() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                pdf_name,
                COUNT(*) AS page_count,
                COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END), 0) AS done_pages,
                COALESCE(SUM(CASE WHEN status='error' THEN 1 ELSE 0 END), 0) AS error_pages
            FROM pages
            GROUP BY pdf_name
            ORDER BY pdf_name COLLATE NOCASE
            """
        ).fetchall()

    books: List[Dict[str, Any]] = []
    for row in rows:
        book = dict(row)
        pdf_name = str(book.get("pdf_name") or "")
        title_guess = _infer_book_title(pdf_name)
        book["title_guess"] = title_guess
        book["display_name"] = _format_book_label(pdf_name, title_guess)
        books.append(book)
    return books


def get_book_pages(pdf_name: str, limit: int = 12) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT page_num, status, error, raw_text
            FROM pages
            WHERE pdf_name = ?
            ORDER BY page_num
            LIMIT ?
            """,
            (pdf_name, limit),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["preview"] = (item.get("raw_text") or "")[:220].replace("\n", " ")
        result.append(item)
    return result


def get_page(pdf_name: str, page_num: int) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT pdf_name, page_num, raw_text, status, error, processed_at
            FROM pages
            WHERE pdf_name = ? AND page_num = ?
            """,
            (pdf_name, page_num),
        ).fetchone()
    return dict(row) if row else None


def get_entries() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM entries ORDER BY sort_key, number, title COLLATE NOCASE").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["page_refs"] = json.loads(item.get("page_refs") or "[]")
        except Exception:
            item["page_refs"] = []
        result.append(item)
    return result


def find_entries_by_page_ref(pdf_name: str, page_num: int) -> List[Dict[str, Any]]:
    ref = f"{pdf_name}:{page_num + 1}"
    matches = []
    for entry in get_entries():
        if ref in (entry.get("page_refs") or []):
            matches.append(entry)
    return matches


def render_book_reader_inspector(prefix: str = "book_reader") -> None:
    import streamlit as st

    db_path = resolve_db_path()
    if not db_path.exists():
        st.error(f"לא נמצא DB של הספרים: {db_path}")
        return

    stats = get_stats()
    metrics = st.columns(4)
    metrics[0].metric("עמודים", stats["total_pages"])
    metrics[1].metric("מוכנים", stats["done_pages"])
    metrics[2].metric("ערכים", stats["entry_count"])
    metrics[3].metric("שגיאות", stats["error_pages"])
    st.caption(f"מסד נתונים פעיל: {db_path}")

    books = list_books()
    if not books:
        st.warning("אין כרגע רשומות ב-DB.")
        return

    default_book = next(
        (book["pdf_name"] for book in books if "הקוד השנתי" in (book.get("display_name") or book["pdf_name"])),
        books[0]["pdf_name"],
    )
    book_names = [book["pdf_name"] for book in books]
    book_labels = {book["pdf_name"]: book.get("display_name") or book["pdf_name"] for book in books}
    book_key = f"{prefix}_book"
    page_key = f"{prefix}_page"
    chosen_book = st.selectbox(
        "בחר ספר",
        book_names,
        index=book_names.index(default_book) if default_book in book_names else 0,
        key=book_key,
        format_func=lambda name: book_labels.get(name, name),
    )

    book_summary = next((book for book in books if book["pdf_name"] == chosen_book), None)
    if book_summary:
        st.caption(
            f"שם מוצג: {book_summary.get('display_name') or book_summary['pdf_name']} | "
            f"שם קובץ: {book_summary['pdf_name']}"
        )

    max_pages = int(book_summary["page_count"]) if book_summary else 1
    page_options = list(range(max_pages))
    current_page = int(st.session_state.get(page_key, 0))
    if current_page not in page_options:
        current_page = 0
    page_num = st.selectbox("עמוד", page_options, index=page_options.index(current_page), key=page_key)

    selected_page = get_page(chosen_book, int(page_num))
    if not selected_page:
        st.warning("לא נמצאה רשומת עמוד לבחירה הזאת.")
        return

    page_cols = st.columns(3)
    page_cols[0].metric("סטטוס", selected_page.get("status") or "-")
    page_cols[1].metric("עמוד", int(selected_page["page_num"]) + 1)
    page_cols[2].metric("ערכים מקושרים", len(find_entries_by_page_ref(chosen_book, int(page_num))))

    st.markdown("**טקסט OCR מלא**")
    st.text_area(
        "ocr_text",
        value=selected_page.get("raw_text") or selected_page.get("error") or "",
        height=260,
        label_visibility="collapsed",
    )

    linked_entries = find_entries_by_page_ref(chosen_book, int(page_num))
    st.markdown("**ערכים שנבנו מהעמוד הזה**")
    if not linked_entries:
        st.info("אין ערכים מקושרים לעמוד הזה.")
        return

    for entry in linked_entries:
        with st.expander(f"{entry.get('title', 'ללא כותרת')} · {entry.get('entry_type', 'other')}"):
            st.caption(f"מספר: {entry.get('number', '-')}")
            st.caption(f"עמודי מקור: {', '.join(entry.get('page_refs') or [])}")
            st.write(entry.get("content") or "")
