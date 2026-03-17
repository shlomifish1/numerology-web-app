"""Automatic discovery of research methods from the interpretations folder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


SKIP_FOLDERS = {"men", "women", "raw_books", "book_ingestion", "__pycache__", ".git"}
ADAPTER_BY_FOLDER = {
    "ספר הנומרולוגיה השלם": "green",
    "spirit": "spirit",
    "astrology": "astrology",
}


class MethodRegistry:
    def __init__(self, interpretations_path: Optional[str] = None):
        research_dir = Path(__file__).resolve().parent
        self.base_path = Path(interpretations_path or research_dir.parent / "interpretations")
        self.registry_file = research_dir / "method_registry.json"
        self._methods: Dict[str, Dict[str, object]] = {}
        self._load_registry()
        self.refresh()

    def _load_registry(self) -> None:
        if self.registry_file.exists():
            self._methods = json.loads(self.registry_file.read_text(encoding="utf-8"))

    def _save_registry(self) -> None:
        self.registry_file.write_text(
            json.dumps(self._methods, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _normalize_key(self, folder_name: str) -> str:
        return (
            folder_name.replace(" ", "_")
            .replace("-", "_")
            .replace("'", "")
            .lower()
        )

    def _build_folder_method(self, folder_path: Path) -> Dict[str, object]:
        folder_name = folder_path.name
        adapter = ADAPTER_BY_FOLDER.get(folder_name, "generic")
        return {
            "key": self._normalize_key(folder_name),
            "folder": folder_name,
            "folder_path": str(folder_path),
            "display_name": folder_name,
            "adapter": adapter,
            "enabled_for_research": True,
            "enabled_for_customers": False,
            "added_at": folder_path.stat().st_mtime,
            "notes": "",
        }

    def refresh(self) -> List[Dict[str, object]]:
        changed = False
        existing_keys = set()
        if self.base_path.exists():
            for folder_path in sorted(self.base_path.iterdir()):
                if not folder_path.is_dir() or folder_path.name in SKIP_FOLDERS:
                    continue
                key = self._normalize_key(folder_path.name)
                existing_keys.add(key)
                adapter = ADAPTER_BY_FOLDER.get(folder_path.name, "generic")
                if key not in self._methods:
                    self._methods[key] = self._build_folder_method(folder_path)
                    changed = True
                else:
                    method = self._methods[key]
                    if method.get("adapter") != adapter:
                        method["adapter"] = adapter
                        changed = True
                    if method.get("folder_path") != str(folder_path):
                        method["folder_path"] = str(folder_path)
                        changed = True
                    if method.get("folder") != folder_path.name:
                        method["folder"] = folder_path.name
                        changed = True
                    if method.get("display_name") != folder_path.name:
                        method["display_name"] = folder_path.name
                        changed = True

        built_in_method = {
            "key": "pythagorean_existing",
            "folder": None,
            "folder_path": None,
            "display_name": "שיטת פיתגורס (קיימת)",
            "adapter": "pythagorean",
            "enabled_for_research": True,
            "enabled_for_customers": True,
            "added_at": 0,
            "notes": "מסתמכת על name.py ו-numerology_calculator.py ללא שינוי.",
        }
        if self._methods.get("pythagorean_existing") != built_in_method:
            self._methods["pythagorean_existing"] = built_in_method
            changed = True

        removable = [
            key
            for key, method in self._methods.items()
            if key != "pythagorean_existing" and method.get("folder") and key not in existing_keys
        ]
        for key in removable:
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
                0 if method["key"] == "pythagorean_existing" else 1,
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
