"""Google Drive sync helpers for numerology corpora."""

from __future__ import annotations

import io
import json
import os
import pickle
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
BASE_DIR = Path(__file__).resolve().parents[1]
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.pickle"

GOOGLE_EXPORTS = {
    "application/vnd.google-apps.document": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}
_CONFLICT_NAME_STRIP_RE = re.compile(r"[\s\-_()[\].,;:'\"/\\]+")
GOOGLE_WORKSPACE_MIME_PREFIX = "application/vnd.google-apps."


class DriveAuthRequiredError(RuntimeError):
    """Raised when OAuth authorization is required before Drive sync can run."""


class DriveSync:
    def __init__(self) -> None:
        self.creds = None
        self.service = None

    def _resolve_token_file(self) -> Path:
        token_file_raw = str(os.getenv("GOOGLE_DRIVE_TOKEN_FILE", "")).strip()
        return Path(token_file_raw).expanduser() if token_file_raw else TOKEN_FILE

    def _resolve_credentials_file(self) -> Path:
        credentials_candidates: list[Path] = []
        explicit_credentials = str(os.getenv("GOOGLE_DRIVE_CREDENTIALS_FILE", "")).strip()
        if explicit_credentials:
            credentials_candidates.append(Path(explicit_credentials).expanduser())
        credentials_candidates.append(CREDENTIALS_FILE)
        credentials_candidates.append(BASE_DIR.parent / "credentials.json")

        credentials_file = next((candidate for candidate in credentials_candidates if candidate.exists()), None)
        if not credentials_file:
            looked_in = ", ".join(str(candidate) for candidate in credentials_candidates)
            raise FileNotFoundError(
                "Google Drive credentials file not found. "
                f"Looked in: {looked_in}. "
                "Set GOOGLE_DRIVE_CREDENTIALS_FILE to the correct path."
            )
        return credentials_file

    def _resolve_oauth_state_file(self, token_file: Path) -> Path:
        return token_file.with_name(token_file.name + ".oauth_state.json")

    @staticmethod
    def _write_token(token_file: Path, creds) -> None:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with token_file.open("wb") as token:
            pickle.dump(creds, token)

    @staticmethod
    def _is_invalid_grant_error(exc: Exception) -> bool:
        text = str(exc or "").lower()
        return (
            "invalid_grant" in text
            or "token has been expired or revoked" in text
            or "expired or revoked" in text
            or "refresh token is invalid" in text
            or "invalid_rapt" in text
        )

    @staticmethod
    def _invalidate_token_file(token_file: Path) -> None:
        if not token_file.exists():
            return
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        invalid_path = token_file.with_name(f"{token_file.name}.invalid_{timestamp}")
        try:
            token_file.replace(invalid_path)
        except Exception:
            try:
                token_file.unlink(missing_ok=True)
            except Exception:
                pass

    def authenticate(self, *, interactive: bool = False) -> None:
        token_file = self._resolve_token_file()
        credentials_file = self._resolve_credentials_file()
        reauth_required = False

        self.creds = None
        if token_file.exists():
            try:
                with token_file.open("rb") as token:
                    self.creds = pickle.load(token)
            except Exception:
                self.creds = None

        if not self.creds or not getattr(self.creds, "valid", False):
            if self.creds and getattr(self.creds, "expired", False) and getattr(self.creds, "refresh_token", None):
                try:
                    self.creds.refresh(Request())
                    self._write_token(token_file, self.creds)
                except RefreshError as exc:
                    if self._is_invalid_grant_error(exc):
                        reauth_required = True
                        self.creds = None
                        self._invalidate_token_file(token_file)
                    else:
                        raise
                except Exception as exc:
                    if self._is_invalid_grant_error(exc):
                        reauth_required = True
                        self.creds = None
                        self._invalidate_token_file(token_file)
                    else:
                        raise
            elif interactive:
                flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
                self.creds = flow.run_local_server(port=0, open_browser=True)
                self._write_token(token_file, self.creds)
            else:
                message = (
                    "Google Drive authorization expired or was revoked. "
                    "Reconnect Drive and retry sync."
                    if reauth_required
                    else "Google Drive authorization is required. "
                    "Start OAuth first and then retry sync."
                )
                raise DriveAuthRequiredError(
                    message
                )

        self.service = build("drive", "v3", credentials=self.creds)
        try:
            # Force an authenticated call so revoked tokens fail here with a clear reauth signal.
            self.service.about().get(fields="user").execute()
        except Exception as exc:
            if self._is_invalid_grant_error(exc):
                self._invalidate_token_file(token_file)
                self.creds = None
                self.service = None
                raise DriveAuthRequiredError(
                    "Google Drive authorization expired or was revoked. "
                    "Reconnect Drive and retry sync."
                ) from exc
            raise

    def begin_oauth_web_flow(self, callback_url: str) -> Dict[str, Any]:
        callback = str(callback_url or "").strip()
        if not callback:
            raise ValueError("callback_url is required")
        credentials_file = self._resolve_credentials_file()
        token_file = self._resolve_token_file()
        state_file = self._resolve_oauth_state_file(token_file)

        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
        flow.redirect_uri = callback
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
        )

        payload = {
            "state": state,
            "redirect_uri": callback,
            "credentials_file": str(credentials_file),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "code_verifier": str(getattr(flow, "code_verifier", "") or ""),
        }
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "authorization_url": authorization_url,
            "state": state,
            "state_file": str(state_file),
            "token_file": str(token_file),
        }

    def complete_oauth_web_flow(self, authorization_response_url: str) -> Dict[str, Any]:
        callback_response = str(authorization_response_url or "").strip()
        if not callback_response:
            raise ValueError("authorization_response_url is required")

        token_file = self._resolve_token_file()
        state_file = self._resolve_oauth_state_file(token_file)
        if not state_file.exists():
            raise DriveAuthRequiredError("OAuth state file is missing. Start OAuth flow again.")

        payload = json.loads(state_file.read_text(encoding="utf-8") or "{}")
        state = str(payload.get("state") or "").strip()
        redirect_uri = str(payload.get("redirect_uri") or "").strip()
        credentials_file = Path(str(payload.get("credentials_file") or "").strip() or self._resolve_credentials_file())

        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_file),
            SCOPES,
            state=state or None,
        )
        if redirect_uri:
            flow.redirect_uri = redirect_uri
        code_verifier = str(payload.get("code_verifier") or "").strip()
        if code_verifier:
            flow.code_verifier = code_verifier
        # Google may return previously granted scopes for the same client.
        # Pass scope=None at token exchange time to avoid strict scope equality failures.
        try:
            flow.fetch_token(authorization_response=callback_response, scope=None)
        except Exception as exc:
            if self._is_invalid_grant_error(exc):
                try:
                    state_file.unlink(missing_ok=True)
                except Exception:
                    pass
                raise DriveAuthRequiredError(
                    "Google Drive authorization failed (invalid_grant). "
                    "Start the OAuth flow again and approve access."
                ) from exc
            raise

        self.creds = flow.credentials
        self._write_token(token_file, self.creds)
        try:
            state_file.unlink(missing_ok=True)
        except Exception:
            pass

        self.service = build("drive", "v3", credentials=self.creds)
        return {
            "token_file": str(token_file),
            "expiry": str(getattr(self.creds, "expiry", "") or ""),
            "scopes": list(getattr(self.creds, "scopes", []) or []),
        }

    @staticmethod
    def parse_folder_id(folder_ref: str) -> str:
        value = str(folder_ref or "").strip()
        if not value:
            raise ValueError("folder_ref is empty")
        match = re.search(r"/folders/([a-zA-Z0-9_-]+)", value)
        if match:
            return match.group(1)
        if "drive.google.com" in value and "id=" in value:
            match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", value)
            if match:
                return match.group(1)
        return value

    @staticmethod
    def _safe_filename(name: str) -> str:
        cleaned = re.sub(r'[<>:"/\\\\|?\*\x00-\x1f]', "_", name).strip().rstrip(".")
        return cleaned or "drive_file"

    @staticmethod
    def _normalise_conflict_name(name: str) -> str:
        text = unicodedata.normalize("NFC", str(name or ""))
        text = _CONFLICT_NAME_STRIP_RE.sub("", text)
        return text.lower()

    def _list_children(self, folder_id: str) -> List[Dict[str, Any]]:
        query = f"'{folder_id}' in parents and trashed = false"
        files: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            try:
                response = self.service.files().list(
                    q=query,
                    fields="nextPageToken, files(id,name,mimeType,modifiedTime,size)",
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
            except Exception as exc:
                if self._is_invalid_grant_error(exc):
                    self._invalidate_token_file(self._resolve_token_file())
                    raise DriveAuthRequiredError(
                        "Google Drive authorization expired or was revoked. "
                        "Reconnect Drive and retry sync."
                    ) from exc
                raise
            files.extend(list(response.get("files", []) or []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return files

    def _download_media(self, file_id: str, destination: Path) -> None:
        request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
        self._write_request(request, destination)

    def _export_media(self, file_id: str, export_mime: str, destination: Path) -> None:
        request = self.service.files().export_media(fileId=file_id, mimeType=export_mime)
        self._write_request(request, destination)

    def _write_request(self, request, destination: Path) -> None:
        fh = io.FileIO(str(destination), "wb")
        try:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                try:
                    _, done = downloader.next_chunk()
                except Exception as exc:
                    if self._is_invalid_grant_error(exc):
                        self._invalidate_token_file(self._resolve_token_file())
                        raise DriveAuthRequiredError(
                            "Google Drive authorization expired or was revoked. "
                            "Reconnect Drive and retry sync."
                        ) from exc
                    raise
        finally:
            fh.close()

    def _resolve_target_path(self, item: Dict[str, Any], destination_dir: Path) -> Path:
        name = self._safe_filename(str(item.get("name") or "drive_file"))
        mime_type = str(item.get("mimeType") or "")
        if mime_type in GOOGLE_EXPORTS:
            _, export_ext = GOOGLE_EXPORTS[mime_type]
            target_name = Path(name).stem + export_ext
            return destination_dir / target_name
        return destination_dir / name

    def _download_file(self, item: Dict[str, Any], destination_dir: Path) -> Path:
        file_id = str(item["id"])
        mime_type = str(item.get("mimeType") or "")
        target_path = self._resolve_target_path(item, destination_dir)

        if mime_type in GOOGLE_EXPORTS:
            export_mime, _ = GOOGLE_EXPORTS[mime_type]
            self._export_media(file_id, export_mime, target_path)
            return target_path

        self._download_media(file_id, target_path)
        return target_path

    def _is_google_workspace_type(self, mime_type: str) -> bool:
        return str(mime_type or "").startswith(GOOGLE_WORKSPACE_MIME_PREFIX)

    def _sync_folder(
        self,
        folder_id: str,
        destination: Path,
        manifest: List[Dict[str, Any]],
        *,
        level: int = 0,
        top_level_resolutions: Optional[Dict[str, str]] = None,
        is_root: bool = False,
        preserve_existing: bool = False,
    ) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for item in self._list_children(folder_id):
            mime_type = str(item.get("mimeType") or "")
            name = self._safe_filename(str(item.get("name") or "drive_item"))
            if mime_type == "application/vnd.google-apps.folder":
                child_dir_name = name
                if is_root and top_level_resolutions:
                    raw_name = str(item.get("name") or "")
                    conflict_key = self._normalise_conflict_name(raw_name)
                    resolution = str(top_level_resolutions.get(conflict_key) or "sync").strip()
                    if resolution == "skip":
                        child_dir = destination / child_dir_name
                        manifest.append(
                            {
                                "id": item.get("id"),
                                "name": item.get("name"),
                                "mimeType": mime_type,
                                "local_path": str(child_dir),
                                "modifiedTime": item.get("modifiedTime"),
                                "size": item.get("size"),
                                "level": level,
                                "action": "merged_keep_local",
                            }
                        )
                        self._sync_folder(
                            str(item["id"]),
                            child_dir,
                            manifest,
                            level=level + 1,
                            top_level_resolutions=None,
                            is_root=False,
                            preserve_existing=True,
                        )
                        continue
                    if resolution.startswith("rename:"):
                        suffix = resolution.split(":", 1)[1].strip() if ":" in resolution else ""
                        if suffix:
                            child_dir_name = f"{name}{suffix}"
                child_dir = destination / child_dir_name
                self._sync_folder(
                    str(item["id"]),
                    child_dir,
                    manifest,
                    level=level + 1,
                    top_level_resolutions=None,
                    is_root=False,
                    preserve_existing=preserve_existing,
                )
                continue

            try:
                target_path = self._resolve_target_path(item, destination)
                if preserve_existing and target_path.exists():
                    manifest.append(
                        {
                            "id": item.get("id"),
                            "name": item.get("name"),
                            "mimeType": mime_type,
                            "local_path": str(target_path),
                            "modifiedTime": item.get("modifiedTime"),
                            "size": item.get("size"),
                            "level": level,
                            "action": "kept_local_existing",
                        }
                    )
                    continue
                downloaded_path = self._download_file(item, destination)
                manifest.append(
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "mimeType": mime_type,
                        "local_path": str(downloaded_path),
                        "modifiedTime": item.get("modifiedTime"),
                        "size": item.get("size"),
                        "level": level,
                        "action": "downloaded",
                    }
                )
            except Exception as exc:
                # Google-native files without export mapping should not abort full-folder sync.
                message = str(exc or "")
                if self._is_google_workspace_type(mime_type) and (
                    "fileNotDownloadable" in message
                    or "Only files with binary content can be downloaded" in message
                ):
                    manifest.append(
                        {
                            "id": item.get("id"),
                            "name": item.get("name"),
                            "mimeType": mime_type,
                            "local_path": "",
                            "modifiedTime": item.get("modifiedTime"),
                            "size": item.get("size"),
                            "level": level,
                            "action": "skipped_unsupported_workspace_type",
                            "error": message,
                        }
                    )
                    continue
                raise

    def preview_top_level_conflicts(self, folder_ref: str, destination_dir: str | Path) -> Dict[str, Any]:
        if not self.service:
            self.authenticate()

        folder_id = self.parse_folder_id(folder_ref)
        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)

        local_folders: Dict[str, Path] = {}
        for item in destination.iterdir():
            if not item.is_dir():
                continue
            local_folders[self._normalise_conflict_name(item.name)] = item

        conflicts: List[Dict[str, Any]] = []
        new_folders: List[Dict[str, Any]] = []
        root_files: List[Dict[str, Any]] = []
        for child in self._list_children(folder_id):
            mime_type = str(child.get("mimeType") or "")
            child_name = str(child.get("name") or "").strip()
            if mime_type == "application/vnd.google-apps.folder":
                conflict_key = self._normalise_conflict_name(child_name)
                local_folder = local_folders.get(conflict_key)
                if local_folder:
                    conflicts.append(
                        {
                            "drive_id": str(child.get("id") or ""),
                            "drive_name": child_name,
                            "conflict_key": conflict_key,
                            "local_folder": str(local_folder),
                            "local_name": local_folder.name,
                        }
                    )
                else:
                    new_folders.append(
                        {
                            "drive_id": str(child.get("id") or ""),
                            "drive_name": child_name,
                            "conflict_key": conflict_key,
                        }
                    )
            else:
                root_files.append(
                    {
                        "drive_id": str(child.get("id") or ""),
                        "drive_name": child_name,
                        "mimeType": mime_type,
                    }
                )

        return {
            "folder_id": folder_id,
            "destination": str(destination),
            "conflicts": conflicts,
            "new_folders": new_folders,
            "root_files": root_files,
        }

    def sync_folder(
        self,
        folder_ref: str,
        destination_dir: str | Path,
        *,
        top_level_resolutions: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        if not self.service:
            self.authenticate()

        folder_id = self.parse_folder_id(folder_ref)
        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)

        manifest: List[Dict[str, Any]] = []
        self._sync_folder(
            folder_id,
            destination,
            manifest,
            top_level_resolutions=top_level_resolutions,
            is_root=True,
        )

        manifest_path = destination / "_drive_sync_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        downloaded_count = sum(1 for item in manifest if str(item.get("action") or "downloaded") == "downloaded")

        return {
            "folder_id": folder_id,
            "destination": str(destination),
            "downloaded": downloaded_count,
            "manifest_path": str(manifest_path),
            "items": manifest,
        }
