from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath


def _resolve_project_root() -> Path:
    try:
        return Path(sys._MEIPASS)
    except Exception:
        return Path(__file__).resolve().parent


PROJECT_ROOT = _resolve_project_root()
INTERPRETATIONS_ROOT = PROJECT_ROOT / "interpretations"
RUNTIME_ROOT = INTERPRETATIONS_ROOT / "runtime"
RUNTIME_LEGACY_ROOT = RUNTIME_ROOT / "legacy"
RUNTIME_BOOKS_ROOT = RUNTIME_ROOT / "books"
RESEARCH_ROOT = INTERPRETATIONS_ROOT / "research"
RESEARCH_RAW_BOOKS_ROOT = RESEARCH_ROOT / "raw_books"


def normalize_corpus_key(value: object) -> str:
    return (
        str(value or "")
        .strip()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("'", "")
        .lower()
    )


def sanitize_folder_name(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    invalid = '<>:"/\\|?*'
    sanitized = "".join("_" if char in invalid else char for char in text)
    return sanitized.rstrip(". ").strip()


def ensure_layout_dirs() -> None:
    for path in (
        INTERPRETATIONS_ROOT,
        RUNTIME_ROOT,
        RUNTIME_LEGACY_ROOT,
        RUNTIME_BOOKS_ROOT,
        RESEARCH_ROOT,
        RESEARCH_RAW_BOOKS_ROOT,
    ):
        path.mkdir(parents=True, exist_ok=True)


def research_book_dir(book_name: object) -> Path:
    return RESEARCH_ROOT / sanitize_folder_name(book_name)


def runtime_legacy_gender_dir(gender_folder: object) -> Path:
    return RUNTIME_LEGACY_ROOT / sanitize_folder_name(gender_folder)


def runtime_book_gender_dir(book_name: object, gender_folder: object) -> Path:
    return (
        RUNTIME_BOOKS_ROOT
        / sanitize_folder_name(book_name)
        / sanitize_folder_name(gender_folder)
    )


def runtime_interpretation_file_candidates(
    gender_folder: object,
    category: object,
    file_name: object,
    *,
    nested: bool = False,
    book_name: object | None = None,
) -> list[Path]:
    gender = sanitize_folder_name(gender_folder)
    current_category = sanitize_folder_name(category)
    current_file_name = sanitize_folder_name(file_name)
    tails = (
        [Path("interpretations") / current_category / current_file_name]
        if nested
        else [Path(current_category) / current_file_name]
    )
    candidates: list[Path] = []
    if book_name:
        runtime_book_root = runtime_book_gender_dir(book_name, gender)
        candidates.extend(runtime_book_root / tail for tail in tails)
    runtime_legacy_root = runtime_legacy_gender_dir(gender)
    candidates.extend(runtime_legacy_root / tail for tail in tails)

    # Backward-compatible fallback for pre-migration layouts.
    legacy_root = INTERPRETATIONS_ROOT / gender
    candidates.extend(legacy_root / tail for tail in tails)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def runtime_source_label(
    gender_folder: object,
    category: object,
    *,
    book_name: object | None = None,
) -> str:
    gender = sanitize_folder_name(gender_folder)
    current_category = sanitize_folder_name(category)
    if book_name:
        book_folder = sanitize_folder_name(book_name)
        return str(
            PurePosixPath("interpretations")
            / "runtime"
            / "books"
            / book_folder
            / gender
            / current_category
        )
    return str(
        PurePosixPath("interpretations")
        / "runtime"
        / "legacy"
        / gender
        / current_category
    )


def research_source_label(book_name_or_key: object, detail: object | None = None) -> str:
    parts = [
        "interpretations",
        "research",
        sanitize_folder_name(book_name_or_key) or normalize_corpus_key(book_name_or_key),
    ]
    if detail is not None and str(detail).strip():
        parts.append(sanitize_folder_name(detail) or str(detail).strip())
    return str(PurePosixPath(*parts))


def source_label_to_corpus_alias(source: object) -> str:
    text = str(source or "").strip().replace("\\", "/")
    if not text.startswith("interpretations/"):
        return ""
    parts = [part for part in text.split("/") if part]
    if len(parts) >= 3 and parts[1] == "research":
        return parts[2]
    if len(parts) >= 4 and parts[1] == "runtime" and parts[2] == "legacy":
        return parts[3]
    if len(parts) >= 4 and parts[1] == "runtime" and parts[2] == "books":
        return parts[3]
    if len(parts) >= 2:
        return parts[1]
    return ""


def path_to_source_label(path_value: object) -> str:
    try:
        path = Path(path_value).resolve()
        relative = path.relative_to(PROJECT_ROOT.resolve())
        return str(PurePosixPath(*relative.parts))
    except Exception:
        return str(path_value or "").replace("\\", "/")


def path_to_corpus_alias(path_value: object) -> str:
    try:
        path = Path(path_value).resolve()
        relative = path.relative_to(INTERPRETATIONS_ROOT.resolve())
    except Exception:
        return ""

    parts = list(relative.parts)
    if len(parts) >= 2 and parts[0] == "research":
        return str(parts[1]).strip()
    if len(parts) >= 3 and parts[0] == "runtime" and parts[1] == "legacy":
        return str(parts[2]).strip()
    if len(parts) >= 3 and parts[0] == "runtime" and parts[1] == "books":
        return str(parts[2]).strip()
    if parts:
        return str(parts[0]).strip()
    return ""
