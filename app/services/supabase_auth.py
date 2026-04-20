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
