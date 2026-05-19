"""Automatic discovery of research methods from live research book folders only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from interpretation_layout import (
    MAIN_MAP_BOOK_FOLDER,
    PROJECT_ROOT,
    RESEARCH_ROOT,
    ensure_layout_dirs,
    normalize_corpus_key,
)

SKIP_FOLDERS = {
    "book_ingestion",
    "__pycache__",
    ".git",
    "raw_books",
    "runtime",
    "research",
    "_trash_books",
    "_deleted_books",
    "_removed_books",
    "men",
    "women",
    MAIN_MAP_BOOK_FOLDER,
}
DEFAULT_CUSTOMER_FOLDERS: set[str] = set()
INTERNAL_BASELINE_KEY = "legacy_runtime_internal"
LEGACY_BASELINE_KEYS = {"pythagorean_existing"}
STALE_METHOD_KEYS = {"research", "runtime", "more_books", "spirit", "astrology", "men", "women"}
ADAPTER_BY_FOLDER: dict[str, str] = {}
BOOK_SOURCE_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".epub",
    ".htm",
    ".html",
    ".jpeg",
    ".jpg",
    ".json",
    ".md",
    ".pdf",
    ".png",
    ".rtf",
    ".txt",
    ".webp",
    ".xls",
    ".xlsx",
}


class MethodRegistry:
    def __init__(self, interpretations_path: Optional[str] = None):
        del interpretations_path
        research_dir = Path(__file__).resolve().parent
        ensure_layout_dirs()
        self.base_path = RESEARCH_ROOT
        self.registry_file = research_dir / "method_registry.json"
        self.local_registry_file = research_dir / "method_registry.local.json"
        self._methods: Dict[str, Dict[str, object]] = {}
        self._load_registry()
        self.refresh()

    def _load_registry(self) -> None:
        self._methods = {}
        for registry_file in (self.registry_file, self.local_registry_file):
            if registry_file.exists():
                loaded = json.loads(registry_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._methods.update(loaded)

    def _save_registry(self) -> None:
        self.local_registry_file.write_text(
            json.dumps(self._methods, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _normalize_key(self, folder_name: str) -> str:
        return normalize_corpus_key(folder_name)

    def _runtime_folder_path(self, folder_path: Path) -> str:
        try:
            relative = folder_path.resolve().relative_to(PROJECT_ROOT.resolve())
            return "/".join(relative.parts)
        except ValueError:
            return str(folder_path)

    def _build_folder_method(self, folder_path: Path) -> Dict[str, object]:
        folder_name = folder_path.name
        return {
            "key": self._normalize_key(folder_name),
            "folder": folder_name,
            "folder_path": self._runtime_folder_path(folder_path),
            "display_name": folder_name,
            "adapter": ADAPTER_BY_FOLDER.get(folder_name, "generic"),
            "enabled_for_research": True,
            "enabled_for_customers": folder_name.lower() in DEFAULT_CUSTOMER_FOLDERS,
            "internal_only": False,
            "visible_in_research_ui": True,
            "added_at": folder_path.stat().st_mtime,
            "notes": "",
        }

    def _has_book_content(self, folder_path: Path) -> bool:
        has_catalog = any(folder_path.rglob("*__draft_catalog.json"))
        if has_catalog:
            return True
        return any(
            path.is_file() and path.suffix.lower() in BOOK_SOURCE_EXTENSIONS
            for path in folder_path.rglob("*")
        )

    def _append_unique_book_folder(self, folders_by_key: Dict[str, Path], folder_path: Path) -> None:
        if not folder_path.is_dir() or folder_path.name in SKIP_FOLDERS:
            return
        if not self._has_book_content(folder_path):
            return
        key = self._normalize_key(folder_path.name)
        if not key or key in folders_by_key:
            return
        folders_by_key[key] = folder_path

    def _iter_research_book_folders(self) -> List[Path]:
        folders_by_key: Dict[str, Path] = {}
        if self.base_path.exists():
            for folder_path in sorted(self.base_path.iterdir()):
                self._append_unique_book_folder(folders_by_key, folder_path)

        folders: List[Path] = []
        for folder_path in sorted(folders_by_key.values()):
            if not folder_path.is_dir() or folder_path.name in SKIP_FOLDERS:
                continue
            folders.append(folder_path)
        return folders

    def refresh(self) -> List[Dict[str, object]]:
        changed = False
        existing_keys = set()

        for folder_path in self._iter_research_book_folders():
            key = self._normalize_key(folder_path.name)
            existing_keys.add(key)
            adapter = ADAPTER_BY_FOLDER.get(folder_path.name, "generic")
            if key not in self._methods:
                self._methods[key] = self._build_folder_method(folder_path)
                changed = True
            else:
                method = self._methods[key]
                updates = {
                    "folder": folder_path.name,
                    "folder_path": self._runtime_folder_path(folder_path),
                    "display_name": folder_path.name,
                    "adapter": adapter,
                    "enabled_for_research": True,
                    "internal_only": False,
                    "visible_in_research_ui": True,
                }
                for field, expected in updates.items():
                    if method.get(field) != expected:
                        method[field] = expected
                        changed = True

        for key in list(self._methods):
            if key in LEGACY_BASELINE_KEYS or key in STALE_METHOD_KEYS:
                del self._methods[key]
                changed = True

        built_in_method = {
            "key": INTERNAL_BASELINE_KEY,
            "folder": None,
            "folder_path": None,
            "display_name": "Internal Base Map",
            "adapter": "legacy_runtime",
            "enabled_for_research": True,
            "enabled_for_customers": False,
            "internal_only": True,
            "visible_in_research_ui": False,
            "added_at": 0,
            "notes": "Backed by the existing men/women engine without changes.",
        }
        if self._methods.get(INTERNAL_BASELINE_KEY) != built_in_method:
            self._methods[INTERNAL_BASELINE_KEY] = built_in_method
            changed = True

        for key in list(self._methods):
            method = self._methods[key]
            if key == INTERNAL_BASELINE_KEY:
                continue
            if method.get("folder") and key not in existing_keys:
                del self._methods[key]
                changed = True

        if changed:
            self._save_registry()
        return self.list_methods()

    def list_methods(self, research_only: bool = False) -> List[Dict[str, object]]:
        methods = list(self._methods.values())
        if research_only:
            methods = [method for method in methods if method.get("enabled_for_research", True)]
        return sorted(
            methods,
            key=lambda method: (
                0 if method["key"] == INTERNAL_BASELINE_KEY else 1,
                str(method["display_name"]),
            ),
        )

    def get_method(self, method_key: str) -> Optional[Dict[str, object]]:
        return self._methods.get(method_key)

    def set_customer_enabled(self, method_key: str, enabled: bool) -> Dict[str, object]:
        method = self._methods[method_key]
        method["enabled_for_customers"] = bool(enabled)
        self._save_registry()
        return method
