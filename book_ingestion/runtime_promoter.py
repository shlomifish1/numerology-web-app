from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interpretation_layout import (
    RUNTIME_BOOKS_ROOT,
    ensure_layout_dirs,
    sanitize_folder_name,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _gender_text(entry: Any, gender: str) -> str:
    if isinstance(entry, str):
        return entry.strip()
    if not isinstance(entry, dict):
        return str(entry or "").strip()

    normalized = "women" if gender == "women" else "men"
    alias_map = {
        "men": ("men", "male", "m"),
        "women": ("women", "female", "f"),
    }
    for alias in alias_map[normalized]:
        value = entry.get(alias)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = str(value.get("meaning") or value.get("text") or "").strip()
            if nested:
                return nested

    base_text = str(entry.get("meaning") or entry.get("text") or "").strip()
    title = str(entry.get("title") or "").strip()
    if title and base_text:
        return f"{title}\n\n{base_text}".strip()
    return base_text or title


def _book_folder(definition: dict[str, Any]) -> str:
    title = str(definition.get("book_title") or definition.get("book_id") or "runtime_book").strip()
    return sanitize_folder_name(title) or "runtime_book"


def _runtime_book_gender_dir(runtime_books_root: Path, book_folder: str, gender: str) -> Path:
    return (
        runtime_books_root
        / sanitize_folder_name(book_folder)
        / sanitize_folder_name(gender)
    )


def promote_definition_to_runtime(
    definition_path: str | Path,
    *,
    runtime_root: str | Path | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    ensure_layout_dirs()
    definition_file = Path(definition_path).resolve()
    definition = json.loads(definition_file.read_text(encoding="utf-8"))
    runtime_books_root = Path(runtime_root or RUNTIME_BOOKS_ROOT)
    book_folder = _book_folder(definition)
    target_root = runtime_books_root / book_folder
    target_root.mkdir(parents=True, exist_ok=True)

    promoted_counts: dict[str, int] = {"men": 0, "women": 0}
    calculations = list(definition.get("calculations") or [])
    promoted_calculations: list[dict[str, Any]] = []

    for calc in calculations:
        calc_key = str(calc.get("calc_key") or "").strip()
        if not calc_key:
            continue
        table = dict(calc.get("interpretations_by_value") or {})
        promoted_values: list[str] = []
        for value_key, entry in table.items():
            for gender in ("men", "women"):
                text = _gender_text(entry, gender)
                if not text:
                    continue
                out_dir = _runtime_book_gender_dir(runtime_books_root, book_folder, gender) / calc_key
                out_dir.mkdir(parents=True, exist_ok=True)
                suffix = "_m" if gender == "men" else "_f"
                out_path = out_dir / f"{value_key}{suffix}.txt"
                if overwrite or not out_path.exists():
                    out_path.write_text(text.strip() + "\n", encoding="utf-8")
                promoted_counts[gender] += 1
                promoted_values.append(str(value_key))
        promoted_calculations.append(
            {
                "calc_key": calc_key,
                "label_he": calc.get("label_he"),
                "status": calc.get("status"),
                "available_for_runtime": bool(((calc.get("input_metadata") or {}).get("available_for_runtime"))),
                "promoted_value_count": len(set(promoted_values)),
                "has_formula_text": bool(str(calc.get("formula_text") or "").strip()),
            }
        )

    definition_copy = target_root / f"{definition.get('book_id')}.definition.json"
    definition_copy.write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "book_id": definition.get("book_id"),
        "book_title": definition.get("book_title"),
        "book_folder": book_folder,
        "promoted_at": _utc_now(),
        "source_definition": str(definition_file),
        "runtime_root": str(target_root),
        "calculation_count": len(calculations),
        "promoted_interpretation_files": promoted_counts,
        "calculations": promoted_calculations,
    }
    (target_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Promote a reviewed definition into runtime/books.")
    parser.add_argument("--definition", required=True, help="Path to <book>.definition.json")
    parser.add_argument("--runtime-root", default=None, help="Optional runtime/books root override")
    parser.add_argument("--no-overwrite", action="store_true", help="Do not overwrite existing interpretation files")
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    manifest = promote_definition_to_runtime(
        args.definition,
        runtime_root=args.runtime_root,
        overwrite=not args.no_overwrite,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
