from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class SupabaseUser:
    id: str
    email: str | None
    user_metadata: dict[str, Any]


class SupabaseAuthError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _supabase_auth_json_request(
    path: str,
    *,
    method: str,
    access_token: str | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    supabase_url = settings.effective_supabase_url
    supabase_anon_key = settings.effective_supabase_anon_key
    if not supabase_url or not supabase_anon_key:
        raise SupabaseAuthError("Supabase Auth is not configured (missing SUPABASE_URL / SUPABASE_ANON_KEY)")

    data = None
    headers = {
        "apikey": supabase_anon_key,
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    req = urllib.request.Request(
        supabase_url.rstrip("/") + path,
        method=method,
        data=data,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise SupabaseAuthError("Supabase Auth request failed", status_code=exc.code, body=error_body) from exc
    except Exception as exc:
        raise SupabaseAuthError("Failed to reach Supabase Auth", body=str(exc)) from exc

    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SupabaseAuthError("Supabase Auth returned invalid JSON", body=raw[:500]) from exc
    if not isinstance(parsed, dict):
        raise SupabaseAuthError("Supabase Auth returned an unexpected response", body=raw[:500])
    return parsed


def fetch_supabase_user(access_token: str) -> SupabaseUser:
    """
    Validates the access token by calling Supabase Auth and returns the user.

    This avoids needing the Supabase JWT secret in the backend. For higher
    throughput, you can switch to local JWT verification later.
    """

    supabase_url = settings.effective_supabase_url
    supabase_anon_key = settings.effective_supabase_anon_key
    if not supabase_url or not supabase_anon_key:
        raise SupabaseAuthError("Supabase Auth is not configured (missing SUPABASE_URL / SUPABASE_ANON_KEY)")

    url = supabase_url.rstrip("/") + "/auth/v1/user"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "apikey": supabase_anon_key,
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise SupabaseAuthError("Supabase Auth rejected the token", status_code=exc.code, body=body) from exc
    except Exception as exc:
        raise SupabaseAuthError("Failed to reach Supabase Auth", body=str(exc)) from exc

    user_id = payload.get("id")
    if not user_id:
        raise SupabaseAuthError("Supabase Auth response missing user id")

    return SupabaseUser(
        id=user_id,
        email=payload.get("email"),
        user_metadata=payload.get("user_metadata") or {},
    )


def verify_supabase_password(email: str, password: str) -> str:
    payload = _supabase_auth_json_request(
        "/auth/v1/token?grant_type=password",
        method="POST",
        body={"email": email, "password": password},
    )
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise SupabaseAuthError("Supabase password verification did not return an access token")
    return access_token


def update_supabase_password(access_token: str, new_password: str) -> None:
    _supabase_auth_json_request(
        "/auth/v1/user",
        method="PUT",
        access_token=access_token,
        body={"password": new_password},
    )
