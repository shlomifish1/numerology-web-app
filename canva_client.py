"""Canva Connect API client for numerology map integration."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx

# ── Credentials ──────────────────────────────────────────────────────────────
CANVA_CLIENT_ID = os.getenv("CANVA_CLIENT_ID", "")
CANVA_CLIENT_SECRET = os.getenv("CANVA_CLIENT_SECRET", "")

# ── Endpoints ─────────────────────────────────────────────────────────────────
CANVA_AUTH_URL = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
CANVA_API_BASE = "https://api.canva.com/rest/v1"
CANVA_REDIRECT_URI = os.getenv(
    "CANVA_REDIRECT_URI",
    "https://mirrorforthesoul.me/numerology/canva/callback",
)

CANVA_SCOPES = (
    "design:content:write design:content:read "
    "asset:write asset:read "
    "brandtemplate:content:read brandtemplate:meta:read"
)

# ── Token storage ─────────────────────────────────────────────────────────────
_TOKEN_PATH = Path(__file__).parent.parent / "canva_tokens.json"
_PKCE_PATH = Path(__file__).parent.parent / "canva_pkce_state.json"
_CONNECTIONS_PATH = Path(__file__).parent.parent / "canva_connections.json"

DEFAULT_PROFILE_ID = "cocovanilla"
CANVA_ACCOUNT_PROFILES = {
    "cocovanilla": {
        "id": "cocovanilla",
        "label": "Cocovanilla124",
        "email": "cocovanilla124@outlook.com",
        "pro_until": "2026-12-05",
        "note": "Canva Pro account",
    },
    "shlomifish1": {
        "id": "shlomifish1",
        "label": "Shlomi Fishman",
        "email": "shlomifish1@gmail.com",
        "pro_until": "",
        "note": "Original account",
    },
}


def _default_connections() -> dict:
    return {
        "active_profile": DEFAULT_PROFILE_ID,
        "profiles": {
            key: {**profile, "tokens": {}}
            for key, profile in CANVA_ACCOUNT_PROFILES.items()
        },
    }


def _load_connections() -> dict:
    data = _default_connections()
    if _CONNECTIONS_PATH.exists():
        try:
            saved = json.loads(_CONNECTIONS_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data["active_profile"] = saved.get("active_profile") or data["active_profile"]
                for key, profile in (saved.get("profiles") or {}).items():
                    if isinstance(profile, dict):
                        base = data["profiles"].get(key, {"id": key, "label": key, "email": "", "pro_until": "", "note": ""})
                        data["profiles"][key] = {**base, **profile}
        except Exception:
            pass

    # Backward compatibility: migrate the old single-token file at runtime.
    if _TOKEN_PATH.exists() and not data["profiles"].get(DEFAULT_PROFILE_ID, {}).get("tokens"):
        try:
            old_tokens = json.loads(_TOKEN_PATH.read_text(encoding="utf-8"))
            if isinstance(old_tokens, dict) and old_tokens.get("access_token"):
                data["profiles"][DEFAULT_PROFILE_ID]["tokens"] = old_tokens
        except Exception:
            pass
    return data


def _save_connections(data: dict) -> None:
    _CONNECTIONS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _normalize_profile_id(profile_id: str | None = None) -> str:
    data = _load_connections()
    resolved = (profile_id or data.get("active_profile") or DEFAULT_PROFILE_ID).strip()
    if resolved not in data["profiles"]:
        raise ValueError(f"Unknown Canva account profile: {resolved}")
    return resolved


def list_profiles() -> list[dict]:
    data = _load_connections()
    active = data.get("active_profile") or DEFAULT_PROFILE_ID
    profiles = []
    for key, profile in data.get("profiles", {}).items():
        tokens = profile.get("tokens") or {}
        profiles.append({
            "id": key,
            "label": profile.get("label") or key,
            "email": profile.get("email") or "",
            "pro_until": profile.get("pro_until") or "",
            "note": profile.get("note") or "",
            "connected": bool(tokens.get("access_token")),
            "active": key == active,
        })
    return profiles


def get_active_profile_id() -> str:
    return _normalize_profile_id()


def set_active_profile(profile_id: str) -> dict:
    resolved = _normalize_profile_id(profile_id)
    data = _load_connections()
    data["active_profile"] = resolved
    _save_connections(data)
    return next(profile for profile in list_profiles() if profile["id"] == resolved)


def _require_oauth_credentials() -> tuple[str, str]:
    if not CANVA_CLIENT_ID or not CANVA_CLIENT_SECRET:
        raise RuntimeError("Canva OAuth credentials are not configured.")
    return CANVA_CLIENT_ID, CANVA_CLIENT_SECRET


def _load_tokens(profile_id: str | None = None) -> dict:
    data = _load_connections()
    resolved = _normalize_profile_id(profile_id)
    return data.get("profiles", {}).get(resolved, {}).get("tokens") or {}


def _save_tokens(tokens: dict, profile_id: str | None = None) -> None:
    data = _load_connections()
    resolved = _normalize_profile_id(profile_id)
    data["profiles"].setdefault(resolved, {"id": resolved, "label": resolved})
    data["profiles"][resolved]["tokens"] = tokens
    data["active_profile"] = resolved
    _save_connections(data)


def _save_pkce_state(state: str, code_verifier: str, profile_id: str) -> None:
    _PKCE_PATH.write_text(
        json.dumps({
            "state": state,
            "code_verifier": code_verifier,
            "profile_id": profile_id,
            "created_at": time.time(),
        }),
        encoding="utf-8",
    )


def _load_pkce_state() -> dict:
    if _PKCE_PATH.exists():
        try:
            return json.loads(_PKCE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ── OAuth PKCE helpers ────────────────────────────────────────────────────────

def generate_auth_url(profile_id: str | None = None) -> str:
    """Generate the Canva OAuth authorization URL and persist PKCE state."""
    client_id, _ = _require_oauth_credentials()
    resolved_profile = _normalize_profile_id(profile_id)
    code_verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)

    _save_pkce_state(state, code_verifier, resolved_profile)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CANVA_REDIRECT_URI,
        "scope": CANVA_SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "s256",
        "state": state,
    }
    query = urlencode(params)
    return f"{CANVA_AUTH_URL}?{query}"


def exchange_code(code: str, state: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    client_id, client_secret = _require_oauth_credentials()
    pkce = _load_pkce_state()
    if pkce.get("state") != state:
        raise ValueError("Invalid OAuth state parameter – possible CSRF attempt.")
    code_verifier = pkce.get("code_verifier", "")
    profile_id = _normalize_profile_id(pkce.get("profile_id"))

    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()

    r = httpx.post(
        CANVA_TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CANVA_REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    r.raise_for_status()
    tokens = r.json()
    tokens["stored_at"] = time.time()
    _save_tokens(tokens, profile_id)
    return tokens


def _refresh_access_token(refresh_token: str, profile_id: str | None = None) -> dict:
    client_id, client_secret = _require_oauth_credentials()
    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()
    r = httpx.post(
        CANVA_TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    r.raise_for_status()
    tokens = r.json()
    tokens["stored_at"] = time.time()
    _save_tokens(tokens, profile_id)
    return tokens


def _get_valid_token(profile_id: str | None = None) -> str:
    """Return a valid access token, refreshing if needed."""
    resolved_profile = _normalize_profile_id(profile_id)
    tokens = _load_tokens(resolved_profile)
    if not tokens or not tokens.get("access_token"):
        raise ConnectionError("Canva not connected. Visit /numerology/canva/auth to connect.")

    stored_at = float(tokens.get("stored_at", 0))
    expires_in = int(tokens.get("expires_in", 14400))
    # Refresh 5 minutes before expiry
    if time.time() - stored_at > expires_in - 300:
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise ConnectionError("Canva token expired and no refresh token available. Reconnect.")
        tokens = _refresh_access_token(refresh_token, resolved_profile)

    return tokens["access_token"]


def is_connected(profile_id: str | None = None) -> bool:
    tokens = _load_tokens(profile_id)
    return bool(tokens.get("access_token"))


# ── Asset upload (async job polling) ─────────────────────────────────────────

def upload_image_asset(
    image_bytes: bytes,
    name: str,
    timeout: int = 60,
    *,
    return_job: bool = False,
    profile_id: str | None = None,
) -> str | dict:
    """Upload a PNG/JPEG/etc. asset to Canva.

    Uses the current Connect API:
    - POST /rest/v1/asset-uploads
    - Content-Type: application/octet-stream
    - Asset-Upload-Metadata: {"name_base64": "..."}

    If return_job is False, waits for success and returns the asset ID.
    If return_job is True, returns the raw job response dict.
    """
    token = _get_valid_token(profile_id)
    name_b64 = base64.b64encode(name.encode("utf-8")).decode()
    metadata = json.dumps({"name_base64": name_b64}, ensure_ascii=False)

    r = httpx.post(
        f"{CANVA_API_BASE}/asset-uploads",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "Asset-Upload-Metadata": metadata,
        },
        content=image_bytes,
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()

    if return_job:
        return data

    job_id = data.get("job", {}).get("id")
    if job_id:
        return _poll_asset_job(token, job_id)

    asset = data.get("job", {}).get("asset") or data.get("asset", {})
    return asset.get("id", "")


def _poll_asset_job(token: str, job_id: str, max_wait: int = 30) -> str:
    """Poll an asset upload job until it completes; return asset ID."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        r = httpx.get(
            f"{CANVA_API_BASE}/asset-uploads/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if not r.is_success:
            time.sleep(2)
            continue
        data = r.json()
        status = data.get("job", {}).get("status") or data.get("status")
        if status == "success":
            return (
                data.get("job", {}).get("asset", {}).get("id")
                or data.get("asset", {}).get("id", "")
            )
        if status == "failed":
            raise RuntimeError(f"Canva asset upload job failed: {data}")
        time.sleep(2)
    raise TimeoutError("Canva asset upload timed out.")


def create_blank_design(
    title: str,
    width: int = 794,
    height: int = 1123,
    asset_id: str | None = None,
    profile_id: str | None = None,
) -> dict:
    """
    Create a blank custom-size design in Canva.
    Default: A4 at 96 dpi = 794×1123 px.
    Returns the design dict including urls.edit.
    """
    token = _get_valid_token(profile_id)
    payload: dict = {
        "design_type": {
            "type": "custom",
            "width": width,
            "height": height,
        },
        "title": title,
    }
    if asset_id:
        payload["asset_id"] = asset_id
    r = httpx.post(
        f"{CANVA_API_BASE}/designs",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("design", r.json())


# ── Brand template autofill ───────────────────────────────────────────────────

def create_autofill_design(
    brand_template_id: str,
    data: dict,
    title: str = "מפה נומרולוגית",
    profile_id: str | None = None,
) -> dict:
    """
    Autofill a Canva brand template with numerology data.
    Returns the generated design dict (with edit URL) once complete.
    Requires Canva for Teams / Enterprise access to autofill API.
    """
    token = _get_valid_token(profile_id)
    r = httpx.post(
        f"{CANVA_API_BASE}/autofills",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "brand_template_id": brand_template_id,
            "data": data,
            "title": title,
        },
        timeout=30,
    )
    r.raise_for_status()
    job = r.json().get("job", {})
    job_id = job.get("id")
    if not job_id:
        return job  # maybe synchronous

    return _poll_autofill_job(token, job_id)


def _poll_autofill_job(token: str, job_id: str, max_wait: int = 120) -> dict:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        r = httpx.get(
            f"{CANVA_API_BASE}/autofills/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.is_success:
            data = r.json()
            job = data.get("job", data)
            status = job.get("status")
            if status == "success":
                result = job.get("result") or {}
                return result.get("design") or job.get("design") or job
            if status == "failed":
                raise RuntimeError(f"Canva autofill failed: {data}")
        time.sleep(3)
    raise TimeoutError("Canva autofill job timed out.")


def list_brand_templates(profile_id: str | None = None) -> list:
    """List available brand templates (requires Enterprise)."""
    token = _get_valid_token(profile_id)
    r = httpx.get(
        f"{CANVA_API_BASE}/brand-templates",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("items", [])
