from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from interpretation_layout import (
    RUNTIME_BOOKS_ROOT,
    normalize_corpus_key,
    sanitize_folder_name,
)


def _gender_suffix(gender: str) -> str:
    normalized = normalize_corpus_key(gender)
    return "_f" if normalized in {"female", "women", "woman", "f"} else "_m"


class RuntimeBookLoader:
    def __init__(self, runtime_root: Path | None = None):
        self.runtime_root = Path(runtime_root or RUNTIME_BOOKS_ROOT)

    def _book_gender_dir(self, book_folder: str, gender: str) -> Path:
        return (
            self.runtime_root
            / sanitize_folder_name(book_folder)
            / sanitize_folder_name(gender)
        )

    def list_books(self) -> list[dict[str, Any]]:
        if not self.runtime_root.exists():
            return []
        books: list[dict[str, Any]] = []
        for folder in sorted(self.runtime_root.iterdir()):
            if not folder.is_dir():
                continue
            manifest_path = folder / "manifest.json"
            if manifest_path.exists():
                try:
                    books.append(json.loads(manifest_path.read_text(encoding="utf-8")))
                    continue
                except Exception:
                    pass
            books.append(
                {
                    "book_folder": folder.name,
                    "book_id": normalize_corpus_key(folder.name),
                    "book_title": folder.name,
                    "runtime_root": str(folder),
                }
            )
        return books

    def _candidate_roots(self, book_key: str) -> Iterable[Path]:
        if not self.runtime_root.exists():
            return []
        normalized = normalize_corpus_key(book_key)
        candidates: list[Path] = []
        for folder in sorted(self.runtime_root.iterdir()):
            if not folder.is_dir():
                continue
            manifest_path = folder / "manifest.json"
            manifest: dict[str, Any] = {}
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    manifest = {}
            aliases = {
                folder.name,
                normalize_corpus_key(folder.name),
                str(manifest.get("book_id") or "").strip(),
                normalize_corpus_key(manifest.get("book_id") or ""),
                str(manifest.get("book_title") or "").strip(),
                normalize_corpus_key(manifest.get("book_title") or ""),
            }
            if book_key in aliases or normalized in aliases:
                candidates.append(folder)
        return candidates

    def resolve_book_root(self, book_key: str) -> Path:
        candidates = list(self._candidate_roots(book_key))
        if not candidates:
            raise FileNotFoundError(f"Runtime book not found: {book_key}")
        return candidates[0]

    def load_manifest(self, book_key: str) -> dict[str, Any]:
        root = self.resolve_book_root(book_key)
        manifest_path = root / "manifest.json"
        if not manifest_path.exists():
            return {
                "book_folder": root.name,
                "book_id": normalize_corpus_key(root.name),
                "book_title": root.name,
                "runtime_root": str(root),
            }
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def load_definition(self, book_key: str) -> dict[str, Any]:
        root = self.resolve_book_root(book_key)
        candidates = sorted(root.glob("*.definition.json"))
        if not candidates:
            raise FileNotFoundError(f"Definition not found for runtime book: {book_key}")
        return json.loads(candidates[0].read_text(encoding="utf-8"))

    def get_supported_calculations(self, book_key: str) -> list[dict[str, Any]]:
        definition = self.load_definition(book_key)
        return list(definition.get("calculations") or [])

    def get_formula(self, book_key: str, calc_key: str) -> dict[str, Any]:
        definition = self.load_definition(book_key)
        calc = next(
            (item for item in definition.get("calculations", []) if str(item.get("calc_key") or "") == calc_key),
            None,
        )
        if calc is None:
            raise KeyError(f"Calculation not found: {calc_key}")
        return {
            "calc_key": calc.get("calc_key"),
            "label_he": calc.get("label_he"),
            "formula_text": calc.get("formula_text"),
            "formula_steps": list(calc.get("formula_steps") or []),
            "input_metadata": dict(calc.get("input_metadata") or {}),
            "allowed_result_values": list(calc.get("allowed_result_values") or []),
            "source_refs": list(calc.get("source_refs") or []),
        }

    def get_interpretation(self, book_key: str, calc_key: str, value: Any, gender: str = "men") -> str:
        root = self.resolve_book_root(book_key)
        manifest = self.load_manifest(book_key)
        book_folder = str(manifest.get("book_folder") or root.name)
        normalized_gender = "women" if normalize_corpus_key(gender) in {"female", "women", "woman", "f"} else "men"
        category_dir = self._book_gender_dir(book_folder, normalized_gender) / calc_key
        suffix = _gender_suffix(normalized_gender)
        candidate_files = [
            category_dir / f"{value}{suffix}.txt",
            category_dir / f"{value}.txt",
        ]
        for candidate in candidate_files:
            if candidate.exists():
                return candidate.read_text(encoding="utf-8").strip()

        definition = self.load_definition(book_key)
        calc = next(
            (item for item in definition.get("calculations", []) if str(item.get("calc_key") or "") == calc_key),
            None,
        )
        if calc is None:
            raise KeyError(f"Calculation not found: {calc_key}")
        table = dict(calc.get("interpretations_by_value") or {})
        entry = table.get(str(value))
        if isinstance(entry, dict):
            return str(entry.get("meaning") or entry.get("text") or "").strip()
        return str(entry or "").strip()
