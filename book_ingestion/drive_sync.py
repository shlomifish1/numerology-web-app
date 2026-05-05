"""Google Drive sync helpers for numerology corpora."""

from __future__ import annotations

import io
import json
import os
import pickle
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    def authenticate(self, *, interactive: bool = False) -> None:
        token_file = self._resolve_token_file()
        credentials_file = self._resolve_credentials_file()

        self.creds = None
        if token_file.exists():
            try:
                with token_file.open("rb") as token:
                    self.creds = pickle.load(token)
            except Exception:
                self.creds = None

        if not self.creds or not getattr(self.creds, "valid", False):
            if self.creds and getattr(self.creds, "expired", False) and getattr(self.creds, "refresh_token", None):
                self.creds.refresh(Request())
                self._write_token(token_file, self.creds)
            elif interactive:
                flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
                self.creds = flow.run_local_server(port=0, open_browser=True)
                self._write_token(token_file, self.creds)
            else:
                raise DriveAuthRequiredError(
                    "Google Drive authorization is required. "
                    "Start OAuth first and then retry sync."
                )

        self.service = build("drive", "v3", credentials=self.creds)

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
        flow.fetch_token(authorization_response=callback_response, scope=None)

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

    def _list_children(self, folder_id: str) -> List[Dict[str, Any]]:
        query = f"'{folder_id}' in parents and trashed = false"
        files: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            response = self.service.files().list(
                q=query,
                fields="nextPageToken, files(id,name,mimeType,modifiedTime,size)",
                pageSize=1000,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
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
                _, done = downloader.next_chunk()
        finally:
            fh.close()

    def _download_file(self, item: Dict[str, Any], destination_dir: Path) -> Path:
        file_id = str(item["id"])
        name = self._safe_filename(str(item.get("name") or "drive_file"))
        mime_type = str(item.get("mimeType") or "")

        if mime_type in GOOGLE_EXPORTS:
            export_mime, export_ext = GOOGLE_EXPORTS[mime_type]
            target_name = Path(name).stem + export_ext
            target_path = destination_dir / target_name
            self._export_media(file_id, export_mime, target_path)
            return target_path

        target_path = destination_dir / name
        self._download_media(file_id, target_path)
        return target_path

    def _sync_folder(self, folder_id: str, destination: Path, manifest: List[Dict[str, Any]], *, level: int = 0) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for item in self._list_children(folder_id):
            mime_type = str(item.get("mimeType") or "")
            name = self._safe_filename(str(item.get("name") or "drive_item"))
            if mime_type == "application/vnd.google-apps.folder":
                child_dir = destination / name
                self._sync_folder(str(item["id"]), child_dir, manifest, level=level + 1)
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
                }
            )

    def sync_folder(self, folder_ref: str, destination_dir: str | Path) -> Dict[str, Any]:
        if not self.service:
            self.authenticate()

        folder_id = self.parse_folder_id(folder_ref)
        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)

        manifest: List[Dict[str, Any]] = []
        self._sync_folder(folder_id, destination, manifest)

        manifest_path = destination / "_drive_sync_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "folder_id": folder_id,
            "destination": str(destination),
            "downloaded": len(manifest),
            "manifest_path": str(manifest_path),
            "items": manifest,
        }
