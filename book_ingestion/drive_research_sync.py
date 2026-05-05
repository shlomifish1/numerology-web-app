"""Sync a Google Drive research folder into interpretations/research/.

Workflow
--------
1.  Call ``DriveResearchSync.preview(folder_ref)``  →  get a ``SyncPreview``
    that lists new books and *conflicts* (books whose names already exist
    locally).  Nothing is downloaded yet.

2.  Inspect ``SyncPreview.conflicts`` and fill in a resolution for each::

        preview.resolve("נומרולוגיה של האלף השלישי", "skip")   # keep local
        preview.resolve("ספר חדש",                   "sync")   # overwrite/add

    Accepted values: ``"sync"`` | ``"skip"`` | ``"rename:<suffix>"``
    (e.g. ``"rename:_drive2"`` will download as "ספר חדש_drive2").

3.  Call ``preview.apply()``  →  downloads approved books into
    ``interpretations/research/<folder_name>/`` and returns a ``SyncResult``.

4.  After apply(), call ``catalog_sync.refresh_all()`` to reindex everything.

Duplicate detection is based on *normalised* folder/title matching so that
minor whitespace or punctuation differences are caught too.

CLI usage (interactive)
-----------------------
    python -m book_ingestion.drive_research_sync \\
        --folder "https://drive.google.com/drive/folders/1rDhkIOCHJ3Utn…" \\
        [--auto-skip-conflicts]   # non-interactive: skip all conflicts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional

from interpretation_layout import RESEARCH_ROOT

# DriveSync is imported lazily inside DriveResearchSync.__init__ so that
# this module can be imported even when google-auth is not installed.
_DriveSync = None


def _get_drive_sync_class():
    global _DriveSync
    if _DriveSync is None:
        try:
            from .drive_sync import DriveSync as _DS  # noqa: F401
            _DriveSync = _DS
        except ImportError as exc:
            raise ImportError(
                "Google Drive libraries not installed. "
                "Run: pip install google-auth google-auth-oauthlib google-api-python-client\n"
                f"Original error: {exc}"
            ) from exc
    return _DriveSync

# ────────────────────────────────────────────────────────────────────────────
# Normalisation helpers
# ────────────────────────────────────────────────────────────────────────────

_STRIP_RE = re.compile(r"[\s\-_()[\].,;:'\"/\\]+")


def _normalise(name: str) -> str:
    """Return a canonical lowercase key for fuzzy title matching."""
    text = unicodedata.normalize("NFC", str(name or ""))
    text = _STRIP_RE.sub("", text)
    return text.lower()


# ────────────────────────────────────────────────────────────────────────────
# Data classes
# ────────────────────────────────────────────────────────────────────────────

ConflictResolution = Literal["sync", "skip"] | str   # or "rename:<suffix>"


@dataclass
class DriveBook:
    """A book subfolder discovered in the Drive research folder."""
    drive_id: str
    drive_name: str                 # original Drive folder name
    safe_name: str                  # filesystem-safe name
    norm_key: str                   # normalised key for duplicate detection
    file_count: int = 0             # number of PDF/doc files inside


@dataclass
class Conflict:
    """A DriveBook whose normalised name collides with an existing local folder."""
    drive_book: DriveBook
    local_folder: Path              # existing local path
    local_norm_key: str
    resolution: Optional[ConflictResolution] = None   # set by caller


@dataclass
class SyncPreview:
    """Result of DriveResearchSync.preview().  Mutate .conflicts, then .apply()."""

    _parent: "DriveResearchSync"
    folder_ref: str
    new_books: List[DriveBook] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)

    # ── Resolution helpers ────────────────────────────────────────────────

    def resolve(self, drive_name_or_key: str, resolution: ConflictResolution) -> None:
        """Set the resolution for one conflict.

        ``drive_name_or_key`` can be the exact Drive folder name OR the
        normalised key.  ``resolution`` is one of:
          "sync"           – download, overwriting/merging into existing folder
          "skip"           – do not download this book
          "rename:<suffix>"– download into <original_name><suffix>/
        """
        key = _normalise(drive_name_or_key)
        for c in self.conflicts:
            if c.drive_book.norm_key == key or _normalise(c.drive_book.drive_name) == key:
                c.resolution = resolution
                return
        raise KeyError(f"No conflict found for {drive_name_or_key!r}")

    def resolve_all_conflicts(self, resolution: ConflictResolution) -> None:
        """Apply the same resolution to every unresolved conflict."""
        for c in self.conflicts:
            if c.resolution is None:
                c.resolution = resolution

    @property
    def unresolved_conflicts(self) -> List[Conflict]:
        return [c for c in self.conflicts if c.resolution is None]

    # ── Apply ────────────────────────────────────────────────────────────

    def apply(self) -> "SyncResult":
        """Download approved books.  Raises if any conflict is still unresolved."""
        if self.unresolved_conflicts:
            names = [c.drive_book.drive_name for c in self.unresolved_conflicts]
            raise RuntimeError(
                f"Cannot apply: {len(names)} conflict(s) still need a resolution: "
                + ", ".join(repr(n) for n in names[:5])
            )
        return self._parent._apply(self)

    # ── Pretty print ─────────────────────────────────────────────────────

    def summary(self) -> str:
        lines: List[str] = [
            f"Drive sync preview: {len(self.new_books)} new, "
            f"{len(self.conflicts)} conflict(s)."
        ]
        if self.new_books:
            lines.append("\nNew books (will be downloaded):")
            for b in self.new_books:
                lines.append(f"  + {b.drive_name}  ({b.file_count} files)")
        if self.conflicts:
            lines.append("\nConflicts (same name exists locally):")
            for c in self.conflicts:
                res = c.resolution or "⚠ UNRESOLVED"
                lines.append(
                    f"  ! {c.drive_book.drive_name}\n"
                    f"      local:  {c.local_folder}\n"
                    f"      resolution: {res}"
                )
        return "\n".join(lines)


@dataclass
class SyncResult:
    """Outcome of SyncPreview.apply()."""
    synced: List[str] = field(default_factory=list)     # folders downloaded
    skipped: List[str] = field(default_factory=list)    # skipped by user
    renamed: List[str] = field(default_factory=list)    # downloaded under new name
    errors: Dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        parts = []
        if self.synced:
            parts.append(f"Downloaded {len(self.synced)} book(s): "
                         + ", ".join(self.synced[:5]))
        if self.skipped:
            parts.append(f"Skipped {len(self.skipped)}: " + ", ".join(self.skipped[:5]))
        if self.renamed:
            parts.append(f"Renamed {len(self.renamed)}: " + ", ".join(self.renamed[:5]))
        if self.errors:
            parts.append(f"Errors ({len(self.errors)}): "
                         + ", ".join(f"{k}: {v}" for k, v in list(self.errors.items())[:3]))
        return "  |  ".join(parts) if parts else "Nothing to do."


# ────────────────────────────────────────────────────────────────────────────
# Main class
# ────────────────────────────────────────────────────────────────────────────

class DriveResearchSync:
    """High-level sync of a Drive research folder with conflict detection.

    Parameters
    ----------
    research_root:
        Local root that contains book subfolders.  Defaults to
        ``interpretations/research/`` as resolved by ``interpretation_layout``.
    """

    SKIP_LOCAL_NAMES = {"raw_books", "__pycache__", ".git", ".idea"}

    def __init__(self, research_root: Path | str | None = None) -> None:
        self.research_root = Path(research_root or RESEARCH_ROOT)
        DriveSync = _get_drive_sync_class()
        self._drive = DriveSync()
        self._drive.authenticate(interactive=False)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _local_books(self) -> Dict[str, Path]:
        """Return {normalised_key: local_folder_path} for all existing books."""
        result: Dict[str, Path] = {}
        if not self.research_root.exists():
            return result
        for item in sorted(self.research_root.iterdir()):
            if not item.is_dir() or item.name in self.SKIP_LOCAL_NAMES:
                continue
            result[_normalise(item.name)] = item
        return result

    def _list_drive_books(self, folder_id: str) -> List[DriveBook]:
        """List top-level subfolders of ``folder_id`` as DriveBook objects."""
        books: List[DriveBook] = []
        for item in self._drive._list_children(folder_id):
            if item.get("mimeType") != "application/vnd.google-apps.folder":
                continue
            name = str(item.get("name") or "unknown")
            safe = DriveSync._safe_filename(name)
            # Count PDFs/docs inside
            child_id = str(item["id"])
            try:
                children = self._drive._list_children(child_id)
                pdf_count = sum(
                    1 for c in children
                    if str(c.get("mimeType", "")).startswith("application/pdf")
                    or str(c.get("name", "")).lower().endswith(".pdf")
                )
            except Exception:
                pdf_count = 0
            books.append(DriveBook(
                drive_id=child_id,
                drive_name=name,
                safe_name=safe,
                norm_key=_normalise(name),
                file_count=pdf_count,
            ))
        return books

    # ── Public API ────────────────────────────────────────────────────────

    def preview(self, folder_ref: str) -> SyncPreview:
        """Scan Drive and local folders; return a SyncPreview with conflicts.

        Nothing is downloaded at this stage.
        """
        folder_id = DriveSync.parse_folder_id(folder_ref)
        drive_books = self._list_drive_books(folder_id)
        local_books = self._local_books()

        preview = SyncPreview(_parent=self, folder_ref=folder_ref)

        for book in drive_books:
            if book.norm_key in local_books:
                preview.conflicts.append(Conflict(
                    drive_book=book,
                    local_folder=local_books[book.norm_key],
                    local_norm_key=book.norm_key,
                ))
            else:
                # Also check partial matches (Drive name is substring of local or vice versa)
                partial_match = next(
                    (local_path for local_key, local_path in local_books.items()
                     if book.norm_key in local_key or local_key in book.norm_key
                     and len(book.norm_key) >= 4 and len(local_key) >= 4),
                    None,
                )
                if partial_match:
                    preview.conflicts.append(Conflict(
                        drive_book=book,
                        local_folder=partial_match,
                        local_norm_key=_normalise(partial_match.name),
                    ))
                else:
                    preview.new_books.append(book)

        return preview

    def _apply(self, preview: SyncPreview) -> SyncResult:
        """Internal: called by SyncPreview.apply() after resolutions are set."""
        result = SyncResult()

        # 1. Download new books
        for book in preview.new_books:
            dest = self.research_root / book.safe_name
            try:
                self._drive._sync_folder(book.drive_id, dest, [], level=0)
                result.synced.append(book.drive_name)
            except Exception as exc:
                result.errors[book.drive_name] = str(exc)

        # 2. Handle conflicts according to their resolutions
        for conflict in preview.conflicts:
            res = conflict.resolution or "skip"
            book = conflict.drive_book

            if res == "skip":
                result.skipped.append(book.drive_name)
                continue

            if res == "sync":
                dest = conflict.local_folder   # merge into existing folder
            elif res.startswith("rename:"):
                suffix = res[len("rename:"):]
                dest = self.research_root / (book.safe_name + suffix)
            else:
                # Unknown resolution — treat as skip
                result.skipped.append(book.drive_name)
                continue

            try:
                self._drive._sync_folder(book.drive_id, dest, [], level=0)
                if res == "sync":
                    result.synced.append(book.drive_name)
                else:
                    result.renamed.append(f"{book.drive_name} → {dest.name}")
            except Exception as exc:
                result.errors[book.drive_name] = str(exc)

        return result


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync a Google Drive research folder with conflict detection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive: review conflicts and decide
  python -m book_ingestion.drive_research_sync \\
      --folder "https://drive.google.com/drive/folders/1rDhkIOCH..."

  # Non-interactive: skip all conflicts automatically
  python -m book_ingestion.drive_research_sync \\
      --folder "1rDhkIOCH..." --auto-skip-conflicts

  # After sync, re-index everything:
  python -m book_ingestion.catalog_sync
""",
    )
    parser.add_argument("--folder", required=True,
                        help="Google Drive folder URL or ID")
    parser.add_argument("--auto-skip-conflicts", action="store_true",
                        help="Skip all conflicting books without asking")
    parser.add_argument("--auto-sync-conflicts", action="store_true",
                        help="Overwrite all conflicting local books")
    parser.add_argument("--research-root", default=None,
                        help="Override local research root path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show preview only, do not download anything")
    return parser


def _interactive_resolve(preview: SyncPreview) -> None:
    """Ask the user interactively for each unresolved conflict."""
    print("\n── Conflicts detected ──────────────────────────────────────────")
    for conflict in preview.conflicts:
        print(f"\n  Drive:  {conflict.drive_book.drive_name}"
              f"  ({conflict.drive_book.file_count} PDFs)")
        print(f"  Local:  {conflict.local_folder}")
        print()
        while True:
            answer = input(
                "  Resolution? [s]kip / [o]verwrite / [r]ename <suffix>  > "
            ).strip().lower()
            if answer in ("s", "skip"):
                conflict.resolution = "skip"
                break
            elif answer in ("o", "overwrite", "sync"):
                conflict.resolution = "sync"
                break
            elif answer.startswith("r"):
                parts = answer.split(None, 1)
                suffix = parts[1] if len(parts) > 1 else "_drive"
                conflict.resolution = f"rename:{suffix}"
                break
            else:
                print("  Please enter s, o, or r <suffix>")


def main() -> None:
    args = _build_arg_parser().parse_args()
    syncer = DriveResearchSync(research_root=args.research_root)

    print(f"Scanning Drive folder: {args.folder}")
    preview = syncer.preview(args.folder)
    print(preview.summary())

    if args.dry_run:
        print(chr(10) + "Dry run — nothing downloaded.")
        return

    if args.auto_skip_conflicts:
        preview.resolve_all_conflicts("skip")
    elif args.auto_sync_conflicts:
        preview.resolve_all_conflicts("sync")
    else:
        _interactive_resolve(preview)

    print(chr(10) + "Applying sync...")
    result = preview.apply()
    print(result.summary())

    if result.synced or result.renamed:
        print(chr(10) + "Re-indexing catalogs...")
        from .catalog_sync import refresh_all
        summary = refresh_all()
        print("Catalogs updated:", summary)


if __name__ == "__main__":
    main()
