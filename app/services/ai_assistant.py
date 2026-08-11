from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Optional
from urllib import error, request

from sqlalchemy import and_, desc, func, select, text as sql_text
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.models import (
    Offer,
    OfferActivation,
    OfferStatus,
    RewardLedgerEntry,
    RewardPreference,
    RewardState,
    StockConversion,
    SupportTicket,
    TicketStatus,
    Transaction,
    User,
    UserRole,
)
from app.services.audit import log_action
from app.services.la_restaurant_knowledge import build_ai_restaurant_context, is_restaurant_discovery_query
from app.services.local_discovery import (
    build_local_discovery_context,
    is_current_confirmed_offer,
    should_attempt_local_discovery_context,
)


class AIServiceError(RuntimeError):
    pass


@dataclass
class AIChatResult:
    answer: str
    model: str
    role_context: str


_ALLOWED_CONTEXTS = {"consumer", "merchant", "admin", "public", "home_local_guide"}
_DETERMINISTIC_MODEL_NAME = "perk-deterministic"
_NEMOTRON_SPARK_CONTEXTS = {"home_local_guide", "public", "consumer", "merchant", "admin"}
_SPARK_INPUT_TOKEN_BUDGET = 3600
_SPARK_MESSAGE_OVERHEAD_TOKENS = 8
_NFL_SCHEDULE_DATA_FILE = (
    Path(__file__).resolve().parents[1]
    / "web"
    / "home_portal"
    / "assets"
    / "nfl-2026-schedules.json"
)


def resolve_context(user_role: Optional[UserRole], requested_context: Optional[str]) -> str:
    requested = (requested_context or "").strip().lower()
    if requested not in _ALLOWED_CONTEXTS:
        requested = ""

    if requested == "home_local_guide":
        return "home_local_guide"

    if user_role is None:
        return "public"

    if user_role == UserRole.admin:
        return requested or "admin"

    if user_role == UserRole.merchant:
        if requested in {"merchant", "public"}:
            return requested
        return "merchant"

    if requested in {"consumer", "public"}:
        return requested
    return "consumer"


def _select_ai_provider() -> str:
    provider = (settings.ai_provider or "").strip().lower()
    if provider in {"ollama", "openai", "spark"}:
        return provider
    if settings.openai_api_key:
        return "openai"
    if (settings.spark_public_base_url or "").strip():
        return "spark"
    return "ollama"


def _configured_model_for_provider(provider: str) -> str:
    if provider == "openai":
        return settings.openai_model
    if provider == "spark":
        return (settings.home_local_guide_model or settings.ollama_model).strip() or settings.ollama_model
    return settings.ollama_model


def chat_with_assistant(
    *,
    message: str,
    history: Optional[list[dict[str, str]]],
    db: Optional[Session] = None,
    current_user: Optional[User] = None,
    user_role: Optional[UserRole] = None,
    requested_context: Optional[str] = None,
    page_path: Optional[str] = None,
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
) -> AIChatResult:
    provider = _select_ai_provider()
    resolved_role = current_user.role if current_user else user_role
    role_context = resolve_context(resolved_role, requested_context)

    # Deterministic action hooks (safety-gated by explicit "confirm ..." phrase).
    action_result = _execute_confirmed_action_if_requested(
        db=db,
        current_user=current_user,
        role_context=role_context,
        message=message,
    )
    if action_result:
        snapshot = _build_live_snapshot(db=db, current_user=current_user, role_context=role_context)
        answer = action_result
        if snapshot:
            answer += "\n\nUpdated live account snapshot:\n" + snapshot
        return AIChatResult(
            answer=answer,
            model=_configured_model_for_provider(provider),
            role_context=role_context,
        )

    # Live data query hooks. When AI is enabled, we inject this as context so
    # the model can keep a natural multi-turn conversation instead of returning
    # a single deterministic block response.
    query_result = _execute_live_query_if_requested(
        db=db,
        current_user=current_user,
        role_context=role_context,
        message=message,
    )
    if query_result and (not settings.ai_enabled or _should_return_live_query_directly(message, role_context)):
        return AIChatResult(
            answer=query_result,
            model=_configured_model_for_provider(provider),
            role_context=role_context,
        )

    if not settings.ai_enabled:
        return AIChatResult(
            answer=_fallback_assistant_response(
                db=db,
                current_user=current_user,
                role_context=role_context,
                unavailable_reason="Hosted AI is not enabled on this backend yet.",
            ),
            model=_DETERMINISTIC_MODEL_NAME,
            role_context=role_context,
        )

    system_prompt = _system_prompt_for_context(role_context)
    normalized_history = _normalize_history(history or [])
    include_live_context = _should_include_live_context(
        message=message,
        role_context=role_context,
        query_result=query_result,
    )
    include_home_local_guide = role_context == "home_local_guide"
    include_restaurant_context = db is not None and is_restaurant_discovery_query(message)
    include_public_review_context = _should_include_public_review_context(message, role_context)
    include_public_directory_context = (
        db is not None
        and role_context in {"public", "home_local_guide"}
        and _is_public_directory_search_query(message)
    )
    include_local_discovery_context = (
        db is not None
        and not include_public_directory_context
        and should_attempt_local_discovery_context(message)
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    normalized_page_path = re.sub(r"[^a-zA-Z0-9/_-]", "", (page_path or "").strip())[:300]
    if normalized_page_path and role_context in {"public", "home_local_guide"}:
        messages.append(
            {
                "role": "system",
                "content": (
                    f"PUBLIC PAGE CONTEXT: The visitor is currently viewing {normalized_page_path}. "
                    "Use the page category to interpret short follow-up questions, but use only "
                    "authoritative live or editorial context for factual claims."
                ),
            }
        )

    if include_home_local_guide:
        messages.append(
            {
                "role": "system",
                "content": _home_local_guide_context(db=db),
            }
        )

    if include_live_context:
        snapshot = _build_live_snapshot(db=db, current_user=current_user, role_context=role_context)
        if snapshot:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "LIVE ACCOUNT DATA (authoritative):\n"
                        f"{snapshot}\n\n"
                        "Use this live data directly when answering account/balance/offer questions."
                    ),
                }
            )

        if query_result:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "LIVE QUERY RESULT (authoritative):\n"
                        f"{query_result}\n\n"
                        "Use this to answer naturally in conversation. "
                        "Do not repeat raw blocks unless the user asks for full details."
                    ),
                }
            )

    if include_restaurant_context and db is not None:
        restaurant_context = build_ai_restaurant_context(db, message=message, limit=10)
        if restaurant_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"{restaurant_context}\n\n"
                        "Use this context to answer restaurant discovery questions naturally. "
                        "If user asks for recommendations, suggest top matches and ask one focused "
                        "follow-up question (neighborhood, cuisine, budget, or vibe)."
                    ),
                }
            )

    if include_public_review_context:
        messages.append(
            {
                "role": "system",
                "content": _public_review_coverage_context(),
            }
        )

    if include_public_directory_context and db is not None:
        directory_context = _build_public_directory_context(db, message=message, limit=12)
        if directory_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"{directory_context}\n\n"
                        "Use public business-directory matches for listing/category/ZIP questions. "
                        "A directory listing is not automatically a PerkNation promotion."
                    ),
                }
            )

    if include_local_discovery_context and db is not None:
        local_discovery_limit = 6 if role_context == "home_local_guide" else 12
        local_discovery_context = build_local_discovery_context(
            db,
            message=message,
            user_latitude=user_latitude,
            user_longitude=user_longitude,
            limit=local_discovery_limit,
        )
        if local_discovery_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"{local_discovery_context}\n\n"
                        "When user asks for local recommendations, prioritize these ranked local matches. "
                        "Do not claim there are no local options if ranked matches are present."
                    ),
                }
            )

    messages.extend(normalized_history)
    messages.append({"role": "user", "content": message.strip()})

    providers_to_try: list[str] = [provider]
    # Keep iOS/web AI available even if local Ollama config drifts in hosted env.
    if provider == "ollama" and (settings.spark_public_base_url or "").strip():
        providers_to_try.append("spark")

    model = _configured_model_for_provider(provider)
    model_override = _model_override_for_context(role_context)
    spark_base_override = _spark_base_override_for_context(role_context)
    spark_host_override = _spark_host_override_for_context(role_context)
    answer = ""
    last_error: Optional[AIServiceError] = None

    for candidate in providers_to_try:
        try:
            if candidate == "openai":
                model, answer = _request_openai_chat(messages)
            elif candidate == "spark":
                model, answer = _request_spark_chat(
                    messages,
                    base_url_override=spark_base_override,
                    model_override=model_override,
                    host_id_override=spark_host_override,
                )
            else:
                model, answer = _request_ollama_chat(messages, model_override=model_override)
            break
        except AIServiceError as exc:
            last_error = exc
            continue

    if not answer:
        return AIChatResult(
            answer=_fallback_assistant_response(
                db=db,
                current_user=current_user,
                role_context=role_context,
                unavailable_reason=str(last_error).strip() if last_error else "AI service is unavailable.",
            ),
            model=_DETERMINISTIC_MODEL_NAME,
            role_context=role_context,
        )

    if not answer:
        raise AIServiceError("AI assistant returned an empty response.")

    answer = _guard_current_perk_answer(message=message, answer=answer)
    answer = _strip_visible_markdown_bold(answer)

    if len(answer) > 6000:
        answer = answer[:6000].rstrip() + "\n\n[truncated]"

    return AIChatResult(answer=answer, model=model, role_context=role_context)


def _model_override_for_context(role_context: str) -> Optional[str]:
    if role_context not in _NEMOTRON_SPARK_CONTEXTS:
        return None
    configured = (settings.home_local_guide_model or "").strip()
    return configured or None


def _spark_host_override_for_context(role_context: str) -> Optional[str]:
    if role_context not in _NEMOTRON_SPARK_CONTEXTS:
        return None
    configured = (settings.home_local_guide_spark_host_id or "").strip().lower()
    return configured or None


def _spark_base_override_for_context(role_context: str) -> Optional[str]:
    if role_context not in _NEMOTRON_SPARK_CONTEXTS:
        return None
    configured = (settings.home_local_guide_spark_base_url or "").strip()
    return configured or None


def _request_ollama_chat(
    messages: list[dict[str, str]],
    *,
    model_override: Optional[str] = None,
) -> tuple[str, str]:
    model_name = (model_override or settings.ollama_model).strip() or settings.ollama_model
    body = {
        "model": model_name,
        "stream": False,
        "options": {
            "temperature": max(0.0, min(settings.ollama_temperature, 1.0)),
        },
        "messages": messages,
    }

    endpoint = settings.ollama_base_url.rstrip("/") + "/api/chat"
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    ollama_api_key = (settings.ollama_api_key or "").strip()
    if ollama_api_key:
        headers["X-API-Key"] = ollama_api_key
    ollama_bypass_token = (settings.ollama_bypass_token or "").strip()
    if ollama_bypass_token:
        headers["X-Gateway-Bypass-Token"] = ollama_bypass_token
    ollama_host_header = (settings.ollama_host_header or "").strip()
    if ollama_host_header:
        headers["Host"] = ollama_host_header

    req = request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers=headers,
    )

    try:
        with request.urlopen(req, timeout=settings.ollama_timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise AIServiceError(f"AI request failed ({exc.code}). {detail}".strip()) from exc
    except error.URLError as exc:
        raise AIServiceError(
            "AI service is unreachable. Confirm Ollama (or gateway) is reachable from the backend host."
        ) from exc
    except TimeoutError as exc:
        raise AIServiceError("AI request timed out. Try again in a few seconds.") from exc

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIServiceError("AI service returned invalid JSON.") from exc

    model = str(envelope.get("model") or model_name)
    answer = ""
    message_obj = envelope.get("message")
    if isinstance(message_obj, dict):
        answer = str(message_obj.get("content") or "").strip()
    if not answer:
        answer = str(envelope.get("response") or "").strip()
    return model, answer


def _request_spark_chat(
    messages: list[dict[str, str]],
    *,
    base_url_override: Optional[str] = None,
    model_override: Optional[str] = None,
    host_id_override: Optional[str] = None,
) -> tuple[str, str]:
    base = (base_url_override or settings.spark_public_base_url or "").strip()
    if not base:
        raise AIServiceError(
            "AI service is unreachable. SPARK_PUBLIC_BASE_URL is not configured on this backend."
        )

    host_id = (host_id_override or settings.spark_chat_host_id or "mini").strip().lower()
    if host_id not in {"spark", "mini"}:
        host_id = "mini"
    model_name = (model_override or settings.ollama_model).strip() or settings.ollama_model
    request_messages = _compact_messages_for_spark(messages)

    body = {
        "hostId": host_id,
        "model": model_name,
        "messages": request_messages,
        "temperature": max(0.0, min(settings.ollama_temperature, 1.0)),
        "maxTokens": 900,
    }
    endpoint = base.rstrip("/") + "/api/chat"
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=max(5, int(settings.spark_timeout_seconds))) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise AIServiceError(f"Spark gateway request failed ({exc.code}). {detail}".strip()) from exc
    except error.URLError as exc:
        raise AIServiceError("Spark gateway is unreachable from the backend host.") from exc
    except TimeoutError as exc:
        raise AIServiceError("Spark gateway request timed out. Try again in a few seconds.") from exc

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIServiceError("Spark gateway returned invalid JSON.") from exc

    model = str(envelope.get("model") or model_name)
    answer = str(envelope.get("content") or "").strip()
    if not answer:
        answer = str(envelope.get("rawContent") or "").strip()

    if not answer:
        raw_obj = envelope.get("raw")
        if isinstance(raw_obj, dict):
            choices = raw_obj.get("choices")
            if isinstance(choices, list) and choices:
                message_obj = choices[0].get("message")
                if isinstance(message_obj, dict):
                    answer = str(message_obj.get("content") or "").strip()
                    if not answer:
                        answer = str(message_obj.get("reasoning") or "").strip()

    if not answer:
        raise AIServiceError("Spark gateway returned an empty response.")

    return model, answer


def _estimate_prompt_tokens(messages: list[dict[str, str]]) -> int:
    total = 0
    for item in messages:
        total += _SPARK_MESSAGE_OVERHEAD_TOKENS
        total += max(1, len(str(item.get("role") or "")) // 4)
        total += max(1, len(str(item.get("content") or "")) // 4)
    return total


def _trim_content_to_estimated_tokens(content: str, token_budget: int) -> str:
    clean = content.strip()
    if token_budget <= 0:
        return ""
    if max(1, len(clean) // 4) <= token_budget:
        return clean
    max_chars = max(120, token_budget * 4)
    trimmed = clean[:max_chars].rstrip()
    if "\n" in trimmed and len(trimmed) > 240:
        trimmed = trimmed.rsplit("\n", 1)[0].rstrip()
    return trimmed + "\n[context truncated to fit Spark input limit]"


def _compact_messages_for_spark(
    messages: list[dict[str, str]],
    *,
    token_budget: int = _SPARK_INPUT_TOKEN_BUDGET,
) -> list[dict[str, str]]:
    compact = [
        {
            "role": str(item.get("role") or "").strip(),
            "content": str(item.get("content") or "").strip(),
        }
        for item in messages
        if str(item.get("role") or "").strip() and str(item.get("content") or "").strip()
    ]
    if _estimate_prompt_tokens(compact) <= token_budget:
        return compact

    def _last_user_index() -> Optional[int]:
        for idx in range(len(compact) - 1, -1, -1):
            if compact[idx].get("role") == "user":
                return idx
        return None

    while _estimate_prompt_tokens(compact) > token_budget:
        protected = _last_user_index()
        removable_idx = next(
            (
                idx
                for idx, item in enumerate(compact)
                if idx != protected and item.get("role") in {"user", "assistant"}
            ),
            None,
        )
        if removable_idx is None:
            break
        del compact[removable_idx]

    for per_message_budget in (900, 650, 450, 300):
        if _estimate_prompt_tokens(compact) <= token_budget:
            return compact
        latest_user = _last_user_index()
        for idx in range(len(compact) - 1, -1, -1):
            if idx == latest_user:
                continue
            item = compact[idx]
            content = item.get("content") or ""
            if max(1, len(content) // 4) > per_message_budget:
                item["content"] = _trim_content_to_estimated_tokens(content, per_message_budget)
                if _estimate_prompt_tokens(compact) <= token_budget:
                    return compact

    if _estimate_prompt_tokens(compact) > token_budget:
        latest_user = _last_user_index()
        if latest_user is not None:
            compact[latest_user]["content"] = _trim_content_to_estimated_tokens(
                compact[latest_user].get("content") or "",
                240,
            )

    return compact


def _request_openai_chat(messages: list[dict[str, str]]) -> tuple[str, str]:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise AIServiceError(
            "Hosted AI is configured, but OPENAI_API_KEY is missing on the backend."
        )

    body = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": max(0.0, min(settings.openai_temperature, 1.0)),
    }
    payload = json.dumps(body).encode("utf-8")
    endpoint = settings.openai_base_url.rstrip("/") + "/chat/completions"
    req = request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with request.urlopen(req, timeout=settings.openai_timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 401:
            raise AIServiceError("Hosted AI rejected the API key. Check OPENAI_API_KEY.") from exc
        raise AIServiceError(f"Hosted AI request failed ({exc.code}). {detail}".strip()) from exc
    except error.URLError as exc:
        raise AIServiceError("Hosted AI is unreachable. Check internet connectivity from the backend.") from exc
    except TimeoutError as exc:
        raise AIServiceError("Hosted AI request timed out. Try again in a few seconds.") from exc

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIServiceError("Hosted AI returned invalid JSON.") from exc

    model = str(envelope.get("model") or settings.openai_model)
    answer = _extract_openai_answer(envelope)
    return model, answer


def _extract_openai_answer(envelope: dict) -> str:
    choices = envelope.get("choices")
    if isinstance(choices, list) and choices:
        message_obj = choices[0].get("message")
        if isinstance(message_obj, dict):
            content = message_obj.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "text":
                        text = str(item.get("text") or "").strip()
                        if text:
                            parts.append(text)
                if parts:
                    return "\n".join(parts)
    return ""


def _normalize_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    # Preserve a deeper conversational window for natural multi-turn chats.
    for item in history[-40:]:
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue

        content = str(item.get("content") or "").strip()
        if not content:
            continue

        if len(content) > 3000:
            content = content[:3000]

        items.append({"role": role, "content": content})
    return items


def _system_prompt_for_context(role_context: str) -> str:
    shared = (
        "You are PerkNation AI assistant. Be concise, practical, and accurate. "
        "Never request passwords, one-time codes, or private keys. "
        "If LIVE ACCOUNT DATA is included, use it as source of truth. "
        "If LIVE ACCOUNT DATA or LIVE QUERY RESULT is included, summarize it naturally; do not dump raw key-value blocks unless explicitly asked. "
        "If LOCAL DISCOVERY CONTEXT is included, use those ranked local matches first and provide concrete recommendations. "
        "Do not claim there are no local options when LOCAL DISCOVERY CONTEXT contains matches. "
        "Do not claim PerkNation offers cashback, cash-back, stock rewards, stock conversion, Target offers, reward-rate tables, or cash/stock percentages unless live account context explicitly provides them. "
        "If policy/financial/legal advice is requested, provide general guidance and suggest contacting a qualified professional. "
        "You can have natural, open-ended conversations on general topics."
    )

    if role_context == "merchant":
        return (
            f"{shared} Prioritize merchant operations when asked: offers, locations, activations, transactions, and growth tactics. "
            "Use numbered steps when giving operational instructions."
        )

    if role_context == "admin":
        return (
            f"{shared} Prioritize admin operations when asked: approvals, disputes, fraud/risk, analytics, and governance. "
            "Prefer measurable recommendations and mention tradeoffs."
        )

    if role_context == "consumer":
        return (
            f"{shared} Prioritize consumer experience when asked: current offers, wallet passes, purchase history, referrals, and profile preferences. "
            "Answer general questions directly when asked, even if unrelated to PerkNation. "
            "Do not refuse or redirect general-topic requests. "
            "If asked about cashback or stock rewards, state that those programs are not active on PerkNation right now."
        )

    if role_context == "home_local_guide":
        return (
            "You are the PerkNation AI Local Guide on the public homepage. "
            "Only answer questions about the current PerkNation public promos using confirmed promo context; use separate context for directory, editorial, restaurant, and local-discovery questions. "
            "Use HOME LOCAL GUIDE CONTEXT, LIVE QUERY RESULT, PUBLIC REVIEW COVERAGE CONTEXT, PUBLIC BUSINESS DIRECTORY CONTEXT, LOCAL DISCOVERY CONTEXT, and LA RESTAURANT KNOWLEDGE CONTEXT as authoritative. "
            "Keep four concepts separate: active PerkNation promotions/offers, public business-directory listings, PerkNation editorial/review coverage, and local restaurant or discovery recommendations. "
            "For counts, use the live count in context and never infer totals from a shortlist. "
            "Do not invent promos, rewards, prices, discounts, venues, hours, dates, or ticket terms. "
            "For business directory listings, do not infer missing city, address, phone, website, hours, or services; if LOCAL DISCOVERY CONTEXT says a field is not listed, say it is not listed. "
            "Do not mention cashback, cash-back, stock rewards, stock conversion, Target offers, reward-rate tables, or cash/stock percentages. "
            "If the user asks beyond the available context, say what is known and offer to narrow by category, city, ZIP, or promotion type. "
            "Keep answers concise, practical, and oriented toward what the visitor can do next. "
            "Use plain text only; do not use Markdown bold markers or surround phrases with double asterisks."
        )

    return (
        f"{shared} Focus on public PerkNation product education and onboarding guidance. "
        "Keep responses in plain language. Do not use Markdown bold markers."
    )


def _home_local_guide_context(*, db: Optional[Session]) -> str:
    lines = [
        "HOME LOCAL GUIDE CONTEXT (authoritative public content)",
        "Scope: current PerkNation promotions, public business-directory listings, and local recommendations.",
        "Important distinction: promotions/offers are active PerkNation deals. Business-directory listings are broader local business records and are not automatically promotions.",
        "For directory listings, missing fields are unknown. Never infer a city, address, phone, website, hours, or service detail that is not present in directory context.",
    ]
    if db is not None:
        marketplace_context = _public_marketplace_context(db)
        if marketplace_context:
            lines.extend(["", marketplace_context])

    lines.extend(
        [
            "",
            "Confirmed current PerkNation public promo examples:",
            "- Hollywood Sports paintball campaign: $60 package with 11 regular entry tickets plus 1 Golden Ticket, and a $5 entry-only pass.",
            "- Bond Collective workspace promo: 20% initial discount on coworking, private offices, dedicated desks, day passes, and meeting rooms.",
            "- Crystal jewelry drop: Swarovski Annual Snowflake 10-year period, Swarovski Sorcerer Mickey, Christian Dior Necklace, and Swarovski Swan Crystal Pin Set with pricing pending confirmation.",
            "- El Portal Restaurant World Cup promo: game-day happy hour Tuesday-Friday 12PM-6PM and Saturday-Sunday 12PM-5PM during games.",
            "",
            "Restaurant guide examples currently surfaced on the homepage:",
            "- Union, Agnes, Fishwives, Perle, Bone Kettle, Osawa, Panda Inn, and Pez Coastal Kitchen are Pasadena restaurant recommendations, not discount offers unless another promo says so.",
            "",
            "Editorial/review coverage examples currently surfaced or planned for PerkNation readers:",
            "- Los Angeles fashion guide: LA Market Week, CMC sample-sale Fridays, Fashion District shopping, LA Vintage warehouse sale, and The Grove K-beauty pop-up.",
            "- Events coverage: KCON LA at Crypto.com Arena, UFC Sacramento, Ringling San Diego, and all 32 NFL team schedules organized by AFC and NFC, with Chargers, Rams, and 49ers featured.",
            "- Restaurant coverage: Dine LA 2026 city guides, Pasadena restaurant picks, and broader local dining discovery.",
            "",
            "Answering rules:",
            "- Keep offer counts separate from business-directory listing counts.",
            "- Keep editorial/review coverage separate from active PerkNation promotions.",
            "- If asked for all promotions, summarize active PerkNation offers from live data and offer to narrow by merchant, city, ZIP, or category.",
            "- If asked for business listings, answer from the public directory count or directory search context, not the offer count.",
            "- If asked for recommendations, use local discovery or restaurant context and make clear it is a shortlist, not the total directory.",
        ]
    )
    return "\n".join(lines)


_PUBLIC_REVIEW_COVERAGE_ITEMS = (
    {
        "category": "Fashion and shopping",
        "city": "Los Angeles, United States, and international",
        "title": "2026 Fashion Week calendar: LA, New York, Miami and the world",
        "timing": "August through October 2026",
        "route": "/articles/la-fashion-events-2026",
        "details": (
            "LA Market Week and public CMC sample-sale dates plus official 2026 fashion weeks in Copenhagen "
            "August 3-7, Tokyo August 31-September 5, New York September 10-15, London September 17-21, "
            "Milan September 22-28, Paris September 28-October 6, and Miami October 13-17."
        ),
    },

    {
        "category": "Concerts, markets, local performances, family programs, and small businesses",
        "city": "South Pasadena",
        "title": "South Pasadena August 2026 local events guide",
        "timing": "August 13-28, 2026",
        "route": "/articles/south-pasadena-august-2026-guide",
        "details": (
            "Seven ranked plans covering the August 16 New Romantics concert in Garfield Park, three Thursday "
            "farmers-market nights, a two-day Tournament of Roses fundraiser, weekly singer-songwriter and "
            "musical-theater open mics, two family library activities, and Perk Nation's 97 South Pasadena listings."
        ),
    },
    {
        "category": "Concerts, markets, museums, architecture, and fan events",
        "city": "Pasadena and nearby Arcadia / San Marino",
        "title": "Pasadena August 2026 concerts, markets, and culture guide",
        "timing": "August 14-30, 2026",
        "route": "/articles/pasadena-august-2026-guide",
        "details": (
            "Seven current ranked plans covering Noah Kahan at the Rose Bowl, two Pasadena POPS nights, "
            "Friday Nights at The Gamble House, Sunset Sessions, "
            "America's Got Talent tapings, goat yoga, Power Morphicon, and Perk Nation's 563 Pasadena listings."
        ),
    },
    {
        "category": "Concerts, trails, family events, markets, and outdoor culture",
        "city": "Glendale",
        "title": "Glendale August 2026 concerts, trails, and culture guide",
        "timing": "August 12-30, 2026",
        "route": "/articles/glendale-august-2026-guide",
        "details": (
            "Six current ranked plans covering the final summer concert, the free Wander the "
            "Wilderness Bus, Classic Film Under the Stars, the Nature's Teamwork campfire, "
            "Wilderness Workday, Montrose Harvest Market, and Perk Nation's 100 Glendale listings."
        ),
    },
    {
        "category": "Night markets, garden concerts, community events, and local dining",
        "city": "Arcadia",
        "title": "Arcadia August 2026 night market and concert guide",
        "timing": "August 8-29, 2026",
        "route": "/articles/arcadia-august-2026-guide",
        "details": (
            "Four ranked outings covering the August 21 Arboretum Summer Night, "
            "626 Night Market, two Pasadena POPS concerts, and Perk Nation's 40 Arcadia listings."
        ),
    },
    {
        "category": "Fairs, festivals, arts, concerts, movies, fitness, and coastal events",
        "city": "Orange County",
        "title": "Orange County August 2026 events and outings guide",
        "timing": "August 10-September 6, 2026",
        "route": "/articles/orange-county-august-2026-guide",
        "details": (
            "Nine current ranked plans covering the OC Fair, D23 Anaheim week, Laguna Beach arts season, OC Parks free "
            "concerts and movies, Huntington Beach surf and nature programs, Sea Country Festival, La Habra Corn "
            "Festival, TheFitExpo Anaheim, Orange International Street Fair planning, and "
            "Perk Nation directory links across Orange County cities."
        ),
    },
    {
        "category": "Adaptive surfing, open-water swimming, nature programs, markets, and surf culture",
        "city": "Huntington Beach and Orange County",
        "title": "Huntington Beach August 2026 coastal events guide",
        "timing": "August 8-29, 2026",
        "route": "/articles/huntington-beach-august-2026-guide",
        "details": (
            "Six ranked plans covering Life Rolls On adaptive surfing, the Huntington Beach Pier Swim, "
            "two Bolsa Chica Grunion Runs, the WSL50 surf-history exhibition, Surf City Nights, Junior Rangers, "
            "Litter Getters, and Perk Nation's 43 Huntington Beach listings."
        ),
    },
    {
        "category": "Art festivals, museums, galleries, concerts, and coastal culture",
        "city": "Laguna Beach and Orange County",
        "title": "Laguna Beach August 2026 arts and festival guide",
        "timing": "August 10-September 6, 2026",
        "route": "/articles/laguna-beach-august-2026-guide",
        "details": (
            "Eight current ranked plans covering Pageant of the Masters, Sawdust Art Festival, the Passport to the Arts, "
            "Festival of Arts, Laguna Art-A-Fair, Laguna Art Museum, Music in the Park, "
            "Music at the Promenade, trolley planning, and Perk Nation's 24 Laguna Beach listings."
        ),
    },
    {
        "category": "Concerts, coastal art, wellness, movies, markets, and local history",
        "city": "Santa Monica",
        "title": "Santa Monica August 2026 coastal events guide",
        "timing": "August 15-September 27, 2026",
        "route": "/articles/santa-monica-august-2026-guide",
        "details": (
            "Six current ranked plans covering the August 21 Sunset Swim, Cinema by the Sea, "
            "Wellness & Waves, a Pier history talk, Downtown farmers markets, and the inaugural "
            "Ocean Way Festival, with transit, street-closure, weather, and reservation guidance."
        ),
    },
    {
        "category": "Restaurants, festivals, concerts, movies, and family events",
        "city": "Long Beach",
        "title": "Long Beach August 2026 food, music, and beach guide",
        "timing": "August 10-30, 2026",
        "route": "/articles/long-beach-august-2026-guide",
        "details": (
            "Eight current ranked plans covering Stroll and Savor, Taste of Downtown, the New Blues Festival, "
            "Moonlight Movies, city summer programs, Jazz on the Bay, the Queen Mary movie night, Little Earth Cinema, and Perk Nation's "
            "208 Long Beach directory listings."
        ),
    },
    {
        "category": "Concerts, festivals, and local culture",
        "city": "Long Beach",
        "title": "Vans Warped Tour Long Beach 2026 recap",
        "timing": "July 25-26, 2026",
        "route": "/articles/vans-warped-tour-long-beach-2026",
        "details": (
            "Visual, reported recap of the Shoreline Waterfront weekend covering more than 100 artists, "
            "official festival videos, emerging-artist portraits and artist-owned social links, "
            "skate/BMX/wrestling extras, Long Beach food collaborations, fan reactions, and heat planning."
        ),
    },
    {
        "category": "Events, concerts, and festivals",
        "city": "Southern California",
        "title": "Eighteen Southern California summer plans",
        "timing": "August 10-30, 2026",
        "route": "/articles/southern-california-august-events-2026",
        "details": (
            "Ranked planning guide covering the OC Fair, Huntington Beach surf, swim, and nature programs, Laguna Beach arts season, South Pasadena concerts and markets, and Long Beach food and music, "
            "with a dedicated eight-plan Long Beach guide, Santa Monica outdoor programs, Glendale park events, "
            "Pasadena POPS and a dedicated seven-plan Pasadena August guide, West Hollywood Summer Sounds "
            "on August 16, Noah Kahan at the Rose Bowl on August 15, Just Like Heaven on August 22, and Nisei Week "
            "in Little Tokyo from August 15-23."
        ),
    },
    {
        "category": "Japanese American culture, family events, and traditional arts",
        "city": "Los Angeles",
        "title": "Nisei Week 2026 Little Tokyo guide",
        "timing": "August 15-23, 2026",
        "route": "/articles/nisei-week-little-tokyo-2026-guide",
        "details": (
            "Ranked guide to the free JANM Natsumatsuri Family Festival, JACCC's August 15-16 and 22-23 "
            "traditional-arts programs, Plaza Festival, Little Tokyo Farmers' Market, pre-festival parade and "
            "street-dance practices, transit planning, and Perk Nation's Los Angeles directory."
        ),
    },
    {
        "category": "Fan events, conventions, and Anaheim",
        "city": "Anaheim",
        "title": "D23 Anaheim 2026 practical guide",
        "timing": "August 11-16, 2026",
        "route": "/articles/d23-anaheim-2026-guide",
        "details": (
            "Seven-plan guide to D23's active Anaheim week, including August 11 ticket inventory, post-assignment standby guidance, the August 14-16 "
            "Ultimate Disney Fan Event, Muzeo's Walt Disney Archives exhibition, the Anaheim "
            "Packing District, Angel Stadium, Disneyland Resort, and Perk Nation's Anaheim directory."
        ),
    },
    {
        "category": "Concerts and fan events",
        "city": "Los Angeles",
        "title": "KCON LA 2026",
        "timing": "August 14-16, 2026",
        "route": "/events/kcon-la-2026",
        "details": "K-pop arena programming at Crypto.com Arena, useful for downtown dining, shopping, hotel, and transit guides.",
    },
    {
        "category": "Concerts",
        "city": "San Jose",
        "title": "Mount Westmore",
        "timing": "August 21, 2026",
        "route": "/events/mount-westmore-san-jose",
        "details": "West Coast hip-hop arena show at SAP Center with Snoop Dogg, Ice Cube, E-40, and Too Short.",
    },
    {
        "category": "Sports",
        "city": "Sacramento",
        "title": "UFC Fight Night: Hernandez vs. Rodrigues",
        "timing": "August 22, 2026",
        "route": "/events/ufc-sacramento-2026",
        "details": "Golden 1 Center fight-night coverage; pair with restaurants, hotels, and downtown Sacramento planning.",
    },
    {
        "category": "Sports",
        "city": "Inglewood / Los Angeles",
        "title": "All 32 NFL team schedules and season openers",
        "timing": "September 9, 2026 through Week 18",
        "route": "/events",
        "details": "AFC/NFC league guide with full 18-week schedules, Pacific kickoff times, networks, venues, and byes; Chargers, Rams, and 49ers are featured.",
    },
    {
        "category": "Restaurants",
        "city": "Los Angeles and Pasadena",
        "title": "Dine LA 2026 city guides",
        "timing": "August 14-28, 2026",
        "route": "/articles/dine-la-pasadena-2026",
        "details": "City-specific Dine LA planning, including Pasadena ranked picks and internal links into nearby directory searches.",
    },
)


def _should_include_public_review_context(message: str, role_context: str) -> bool:
    if role_context not in {"public", "home_local_guide"}:
        return False
    text = _normalize_user_text(message)
    if not text:
        return False
    return _contains_any(
        text,
        (
            "fashion",
            "style",
            "shopping",
            "sample sale",
            "market week",
            "event",
            "events",
            "concert",
            "concerts",
            "warped",
            "vans",
            "festival",
            "festivals",
            "fan event",
            "fan events",
            "d23",
            "long beach",
            "stroll & savor",
            "taste of downtown",
            "jazz on the bay",
            "new blues festival",
            "food scene",
            "food week",
            "august event",
            "august events",
            "nisei week",
            "little tokyo",
            "cultural event",
            "cultural events",
            "show",
            "shows",
            "sports",
            "game",
            "games",
            "stadium",
            "arena",
            "restaurant",
            "restaurants",
            "dining",
            "dine la",
            "review",
            "reviews",
            "guide",
            "current",
            "listed",
            "website",
        ),
    )


def _public_review_coverage_context() -> str:
    lines = [
        "PUBLIC REVIEW COVERAGE CONTEXT (authoritative public/editorial content)",
        "Important distinction: these are PerkNation editorial/review topics and planning guides, not active PerkNation promotions unless a separate live offer says so.",
        "Use these items when the visitor asks what fashion events, sports, concerts, restaurants, or reviews are current/listed on the website.",
        "coverage_items:",
    ]
    for item in _PUBLIC_REVIEW_COVERAGE_ITEMS:
        lines.append(
            "- "
            f"category={item['category']}; city={item['city']}; title={item['title']}; "
            f"timing={item['timing']}; route={item['route']}; details={item['details']}"
        )
    return "\n".join(lines)


def _public_marketplace_context(db: Session) -> str:
    now = datetime.now(timezone.utc)
    lines: list[str] = ["LIVE PERKNATION MARKETPLACE SNAPSHOT"]

    try:
        active_directory_count = int(
            db.execute(
                sql_text(
                    "SELECT COUNT(*) FROM business_directory_entries "
                    "WHERE is_active IS TRUE"
                )
            ).scalar()
            or 0
        )
        total_directory_count = int(db.execute(sql_text("SELECT COUNT(*) FROM business_directory_entries")).scalar() or 0)
        lines.append(f"business_directory_active_listings: {active_directory_count}")
        lines.append(f"business_directory_total_records: {total_directory_count}")
    except Exception:
        lines.append("business_directory_counts: unavailable")

    try:
        active_offers = db.scalars(
            select(Offer)
            .options(selectinload(Offer.merchant), selectinload(Offer.location))
            .where(
                and_(
                    Offer.approval_status == OfferStatus.approved,
                    Offer.starts_at <= now,
                    Offer.ends_at >= now,
                )
            )
            .order_by(desc(Offer.created_at), desc(Offer.id))
            .limit(30)
        ).all()
        active_offer_count = db.scalar(
            select(func.count()).select_from(Offer).where(
                and_(
                    Offer.approval_status == OfferStatus.approved,
                    Offer.starts_at <= now,
                    Offer.ends_at >= now,
                )
            )
        ) or 0
    except Exception:
        active_offers = []
        active_offer_count = 0
        lines.append("active_promotion_query: unavailable")

    lines.append(f"active_promotion_count: {int(active_offer_count)}")
    if active_offers:
        lines.append("active_promotion_examples:")
        for offer in active_offers:
            merchant = offer.merchant_name or f"Merchant #{offer.merchant_id}"
            location = f"; location={offer.location.name}" if offer.location else ""
            lines.append(
                f"- offer_id={offer.id}; merchant={merchant}; title={offer.title}{location}; "
                f"ends_at={offer.ends_at.isoformat()}"
            )
    else:
        lines.append("active_promotion_examples: none")

    return "\n".join(lines)


_DIRECTORY_SEARCH_HINTS = {
    "business",
    "businesses",
    "listing",
    "listings",
    "directory",
    "near",
    "nearby",
    "zip",
    "category",
    "categories",
    "restaurant",
    "restaurants",
    "gas",
    "fuel",
    "station",
    "stations",
    "grocery",
    "coffee",
    "retail",
    "medical",
    "dental",
    "auto",
    "bank",
    "hotel",
    "law",
    "attorney",
    "salon",
    "beauty",
    "fitness",
}


def _is_public_directory_search_query(message: str) -> bool:
    text = _normalize_user_text(message)
    if not text:
        return False
    if re.search(r"\b9\d{4}(?:-\d{4})?\b", text):
        return True
    return any(hint in text for hint in _DIRECTORY_SEARCH_HINTS)


def _build_public_directory_context(db: Session, *, message: str, limit: int = 12) -> str:
    text = _normalize_user_text(message)
    if not text:
        return ""

    zip_match = re.search(r"\b(9\d{4})(?:-\d{4})?\b", text)
    zip_code = zip_match.group(1) if zip_match else ""
    excluded_tokens = {
        "how",
        "many",
        "near",
        "nearby",
        "the",
        "are",
        "available",
        "business",
        "businesses",
        "listing",
        "listings",
        "directory",
        "local",
        "total",
        "california",
    }
    tokens = []
    for token in re.findall(r"[a-z0-9]+", text):
        if len(token) < 3 or token in excluded_tokens:
            continue
        tokens.append(token[:-1] if len(token) > 4 and token.endswith("s") else token)
    if zip_code:
        tokens = [token for token in tokens if token != zip_code]

    where_parts = ["is_active IS TRUE"]
    params: dict[str, object] = {"limit": max(1, min(int(limit), 50))}
    if zip_code:
        where_parts.append("zip_code LIKE :zip_code")
        params["zip_code"] = f"{zip_code}%"

    searchable_terms = tokens[:6]
    if searchable_terms:
        term_clauses: list[str] = []
        for idx, token in enumerate(searchable_terms):
            key = f"term_{idx}"
            params[key] = f"%{token}%"
            term_clauses.append(
                "("
                f"LOWER(COALESCE(business_name, '')) LIKE :{key} OR "
                f"LOWER(COALESCE(business_type, '')) LIKE :{key} OR "
                f"LOWER(COALESCE(description, '')) LIKE :{key} OR "
                f"LOWER(COALESCE(address, '')) LIKE :{key} OR "
                f"LOWER(COALESCE(city, '')) LIKE :{key}"
                ")"
            )
        where_parts.append("(" + " AND ".join(term_clauses) + ")")

    where_sql = " AND ".join(where_parts)
    try:
        total = int(
            db.execute(
                sql_text(f"SELECT COUNT(*) FROM business_directory_entries WHERE {where_sql}"),
                params,
            ).scalar()
            or 0
        )
        rows = db.execute(
            sql_text(
                "SELECT business_name, business_type, address, city, zip_code, phone_number, website, source_url "
                f"FROM business_directory_entries WHERE {where_sql} "
                "ORDER BY COALESCE(city, ''), COALESCE(business_name, '') LIMIT :limit"
            ),
            params,
        ).mappings().all()

        broader_total = 0
        broader_rows = []
        if total == 0 and zip_code and searchable_terms:
            broader_params = {"limit": params["limit"]}
            broader_term_clauses: list[str] = []
            for idx, token in enumerate(searchable_terms):
                key = f"term_{idx}"
                broader_params[key] = f"%{token}%"
                broader_term_clauses.append(
                    "("
                    f"LOWER(COALESCE(business_name, '')) LIKE :{key} OR "
                    f"LOWER(COALESCE(business_type, '')) LIKE :{key} OR "
                    f"LOWER(COALESCE(description, '')) LIKE :{key} OR "
                    f"LOWER(COALESCE(address, '')) LIKE :{key} OR "
                    f"LOWER(COALESCE(city, '')) LIKE :{key}"
                    ")"
                )
            broader_where_sql = "is_active IS TRUE AND (" + " AND ".join(broader_term_clauses) + ")"
            broader_total = int(
                db.execute(
                    sql_text(f"SELECT COUNT(*) FROM business_directory_entries WHERE {broader_where_sql}"),
                    broader_params,
                ).scalar()
                or 0
            )
            broader_rows = db.execute(
                sql_text(
                    "SELECT business_name, business_type, address, city, zip_code, phone_number, website, source_url "
                    f"FROM business_directory_entries WHERE {broader_where_sql} "
                    "ORDER BY COALESCE(city, ''), COALESCE(business_name, '') LIMIT :limit"
                ),
                broader_params,
            ).mappings().all()
    except Exception:
        return ""

    lines = [
        "PUBLIC BUSINESS DIRECTORY CONTEXT",
        f"query: {message.strip()}",
        f"matched_listings_total: {total}",
    ]
    if zip_code:
        lines.append(f"zip_filter: {zip_code}")
    if searchable_terms:
        lines.append("search_terms: " + ", ".join(searchable_terms))
    if rows:
        lines.append("matched_listing_examples:")
        for row in rows:
            lines.append("- " + _format_directory_row(row))
    else:
        lines.append("matched_listing_examples: none")
    if total == 0 and zip_code and searchable_terms:
        lines.append(
            "nearby_note: no exact ZIP matches were found in the directory for this category; broader statewide category matches are listed when available."
        )
        lines.append(f"broader_category_matches_total: {broader_total}")
        if broader_rows:
            lines.append("broader_category_examples:")
            for row in broader_rows:
                lines.append("- " + _format_directory_row(row))
        else:
            lines.append("broader_category_examples: none")
    return "\n".join(lines)


def _format_directory_row(row: object) -> str:
    parts = [
        str(row.get("business_name") or "").strip(),
        str(row.get("business_type") or "").strip(),
        str(row.get("address") or "").strip(),
        " ".join(
            part
            for part in [
                str(row.get("city") or "").strip(),
                str(row.get("zip_code") or "").strip(),
            ]
            if part
        ),
        str(row.get("phone_number") or "").strip(),
        str(row.get("website") or "").strip(),
    ]
    return " | ".join(part for part in parts if part)


def _guard_current_perk_answer(*, message: str, answer: str) -> str:
    normalized_answer = answer.lower()
    if _is_discount_query(message) and not _mentions_confirmed_promo(answer):
        return _confirmed_current_deals_answer(message)

    forbidden_terms = (
        "cashback",
        "cash-back",
        "cash back",
        "stock reward",
        "stock rewards",
        "stock conversion",
        "reward-rate",
        "reward rate",
        "% cash",
        "cash /",
        "target",
        "admission & rental",
        "save $60",
        "golden ticket all-inclusive",
        "early access dining perk",
    )
    has_forbidden_terms = any(term in normalized_answer for term in forbidden_terms)
    if not has_forbidden_terms:
        return answer

    return _confirmed_current_deals_answer(message)


def _confirmed_current_deals_answer(message: str) -> str:
    normalized_message = message.lower()
    if any(term in normalized_message for term in ("el portal", "world cup", "happy hour", "soccer", "game")):
        return (
            "The confirmed El Portal deal is World Cup game-day happy hour: Tuesday-Friday 12PM-6PM "
            "and Saturday-Sunday 12PM-5PM during games. The restaurant guide entries are recommendations unless a specific promo is listed."
        )
    if any(term in normalized_message for term in ("paintball", "hollywood", "ticket", "package", "park", "entry")):
        return (
            "The confirmed Hollywood Sports deals are the $60 package with 11 regular entry tickets plus 1 Golden Ticket, "
            "and the $5 entry-only pass. Each ticket's terms are shown on the campaign page before purchase."
        )
    if any(term in normalized_message for term in ("bond", "cowork", "workspace", "office", "desk", "meeting room", "day pass")):
        return (
            "The confirmed Bond Collective deal is a 20% initial discount on services including coworking, private offices, "
            "dedicated desks, day passes, and meeting rooms. Final availability and terms are confirmed through Bond Collective."
        )
    if any(term in normalized_message for term in ("jewelry", "jewellery", "crystal", "swarovski", "sorcerer", "mickey", "dior", "necklace", "swan")):
        return (
            "The confirmed jewelry discounts are Swarovski Annual Snowflake 10-year period for $1,875, "
            "Swarovski Sorcerer Mickey for $180, and Christian Dior Necklace for $420. "
            "Those three items have product pages and online checkout. "
            "The Swarovski Swan Crystal Pin Set is listed with pricing pending confirmation through PerkNation Instagram."
        )
    return (
        "The confirmed PerkNation deals right now are the Hollywood Sports $60 package, the Hollywood Sports $5 entry-only pass, "
        "the Bond Collective 20% initial services discount, the jewelry discounts on the homepage, and El Portal's World Cup game-day happy hour. "
        "Pasadena restaurant guide entries are recommendations unless a specific promo is listed."
    )


def _is_discount_query(message: str) -> bool:
    normalized_message = message.lower()
    return any(
        term in normalized_message
        for term in ("discount", "deal", "deals", "promo", "promotion", "offer", "special", "coupon", "save")
    )


def _mentions_confirmed_promo(answer: str) -> bool:
    normalized_answer = answer.lower()
    return any(
        term in normalized_answer
        for term in (
            "hollywood sports",
            "paintball",
            "$60 package",
            "$5 entry",
            "bond collective",
            "jewelry",
            "swarovski",
            "christian dior",
            "dior",
            "el portal",
            "world cup",
            "happy hour",
        )
    )


def _strip_visible_markdown_bold(answer: str) -> str:
    return answer.replace("**", "").replace("__", "")


def _build_live_snapshot(
    *,
    db: Optional[Session],
    current_user: Optional[User],
    role_context: str,
) -> str:
    if db is None or current_user is None:
        return ""

    if role_context == "consumer":
        return _consumer_snapshot(db, current_user)
    if role_context == "merchant":
        return _merchant_snapshot(db, current_user)
    if role_context == "admin":
        return _admin_snapshot(db, current_user)
    return ""


def _consumer_snapshot(db: Session, current_user: User) -> str:
    now = datetime.now(timezone.utc)

    active_offers = db.scalars(
        select(Offer)
        .options(selectinload(Offer.merchant), selectinload(Offer.location))
        .where(
            and_(
                Offer.approval_status == OfferStatus.approved,
                Offer.starts_at <= now,
                Offer.ends_at >= now,
            )
        )
        .order_by(desc(Offer.created_at))
        .limit(12)
    ).all()
    current_offers = [offer for offer in active_offers if is_current_confirmed_offer(offer)]

    activated_offer_ids = set(
        db.scalars(
            select(OfferActivation.offer_id).where(OfferActivation.user_id == current_user.id)
        ).all()
    )

    recent_transactions = db.scalars(
        select(Transaction)
        .options(selectinload(Transaction.offer).selectinload(Offer.merchant))
        .where(Transaction.user_id == current_user.id)
        .order_by(desc(Transaction.occurred_at), desc(Transaction.id))
        .limit(8)
    ).all()

    lines: list[str] = []
    lines.append(f"timestamp_utc: {now.isoformat()}")
    lines.append(f"user_name: {current_user.full_name}")
    lines.append(f"user_email: {current_user.email}")
    lines.append(f"user_role: {current_user.role.value}")
    lines.append("cashback_stock_rewards: not_active")

    if current_offers:
        lines.append("active_offers:")
        for offer in current_offers:
            merchant = offer.merchant_name or f"Merchant #{offer.merchant_id}"
            activated = "yes" if offer.id in activated_offer_ids else "no"
            lines.append(
                f"- offer_id={offer.id}; title={offer.title}; merchant={merchant}; "
                f"activated={activated}; ends_at={offer.ends_at.isoformat()}"
            )
    else:
        lines.append("active_offers: none")

    if recent_transactions:
        lines.append("recent_transactions:")
        for txn in recent_transactions:
            merchant = txn.merchant_name or f"Merchant #{txn.merchant_id or '-'}"
            lines.append(
                f"- txn_id={txn.id}; merchant={merchant}; amount={_fmt_usd(txn.amount)}; "
                f"status={txn.status.value}; occurred_at={txn.occurred_at.isoformat()}"
            )
    else:
        lines.append("recent_transactions: none")

    return "\n".join(lines)


def _merchant_snapshot(db: Session, current_user: User) -> str:
    now = datetime.now(timezone.utc)

    # Merchant context is keyed by owner_user_id in merchant_profiles.
    from app.db.models import MerchantProfile

    profile = db.scalar(select(MerchantProfile).where(MerchantProfile.owner_user_id == current_user.id))
    lines: list[str] = [
        f"timestamp_utc: {now.isoformat()}",
        f"user_name: {current_user.full_name}",
        f"user_email: {current_user.email}",
        f"user_role: {current_user.role.value}",
    ]

    if profile is None:
        lines.append("merchant_profile: missing")
        return "\n".join(lines)

    offer_ids = db.scalars(select(Offer.id).where(Offer.merchant_id == profile.id)).all()
    activations = 0
    if offer_ids:
        activations = db.scalar(select(func.count()).where(OfferActivation.offer_id.in_(offer_ids))) or 0

    txn_count = db.scalar(select(func.count()).where(Transaction.merchant_id == profile.id)) or 0
    volume = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.merchant_id == profile.id)) or Decimal("0")

    lines.append(f"merchant_dba: {profile.dba_name}")
    lines.append(f"merchant_category: {profile.category}")
    lines.append(f"merchant_status: {profile.status}")
    lines.append(f"offers_count: {len(offer_ids)}")
    lines.append(f"activations_count: {activations}")
    lines.append(f"transactions_count: {txn_count}")
    lines.append(f"attributed_volume: {_fmt_usd(volume)}")

    recent_offers = db.scalars(
        select(Offer)
        .where(Offer.merchant_id == profile.id)
        .order_by(desc(Offer.created_at), desc(Offer.id))
        .limit(8)
    ).all()
    if recent_offers:
        lines.append("recent_offers:")
        for offer in recent_offers:
            lines.append(
                f"- offer_id={offer.id}; title={offer.title}; status={offer.approval_status.value}; "
                f"ends_at={offer.ends_at.isoformat()}"
            )

    return "\n".join(lines)


def _admin_snapshot(db: Session, current_user: User) -> str:
    now = datetime.now(timezone.utc)

    pending_offers = db.scalar(select(func.count()).where(Offer.approval_status == OfferStatus.pending)) or 0
    open_tickets = db.scalar(select(func.count()).where(SupportTicket.status == TicketStatus.open)) or 0

    # Disputes enum compare using literal import-safe approach.
    from app.db.models import DisputeCase, DisputeStatus

    open_disputes_count = db.scalar(select(func.count()).where(DisputeCase.status == DisputeStatus.open)) or 0
    total_users = db.scalar(select(func.count()).where(User.id.is_not(None))) or 0

    lines: list[str] = []
    lines.append(f"timestamp_utc: {now.isoformat()}")
    lines.append(f"admin_name: {current_user.full_name}")
    lines.append(f"admin_email: {current_user.email}")
    lines.append(f"users_total: {total_users}")
    lines.append(f"offers_pending_approval: {pending_offers}")
    lines.append(f"support_tickets_open: {open_tickets}")
    lines.append(f"disputes_open: {open_disputes_count}")

    return "\n".join(lines)


def _execute_confirmed_action_if_requested(
    *,
    db: Optional[Session],
    current_user: Optional[User],
    role_context: str,
    message: str,
) -> Optional[str]:
    if db is None or current_user is None or role_context != "consumer":
        return None

    lower = message.lower()

    if "confirm redeem" in lower:
        return "Cashback reward redemption is not active on PerkNation right now."

    if "confirm settle" in lower:
        return "Cashback reward settlement is not active on PerkNation right now."

    return None


@lru_cache(maxsize=1)
def _nfl_schedule_teams() -> tuple[dict[str, object], ...]:
    try:
        payload = json.loads(_NFL_SCHEDULE_DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ()
    teams = payload.get("teams", [])
    if not isinstance(teams, list):
        return ()
    return tuple(team for team in teams if isinstance(team, dict))


def _nfl_team_aliases(team: dict[str, object]) -> tuple[str, ...]:
    name = str(team.get("name") or "").lower()
    short_name = str(team.get("shortName") or "").lower()
    aliases = {name, short_name}
    if name == "san francisco 49ers":
        aliases.update(("49ers", "niners", "san francisco"))
    elif name == "washington commanders":
        aliases.update(("washington", "commanders"))
    elif name in {"los angeles chargers", "los angeles rams"}:
        aliases.add(f"la {short_name}")
    return tuple(alias for alias in aliases if len(alias) >= 4)


def _matching_nfl_teams(text: str) -> list[dict[str, object]]:
    matches: list[tuple[int, dict[str, object]]] = []
    for team in _nfl_schedule_teams():
        positions = [
            text.find(alias)
            for alias in _nfl_team_aliases(team)
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text)
        ]
        if positions:
            matches.append((min(position for position in positions if position >= 0), team))
    matches.sort(key=lambda match: match[0])
    return [team for _, team in matches]


def _is_public_nfl_query(text: str) -> bool:
    if _matching_nfl_teams(text):
        return True
    return _contains_any(
        text,
        (
            "nfl",
            "football team",
            "football teams",
            "football game",
            "football games",
            "season opener",
            "season openers",
            "afc teams",
            "nfc teams",
            "afc schedule",
            "nfc schedule",
        ),
    )


def _nfl_game_line(game: dict[str, object]) -> str:
    site = str(game.get("site") or "")
    if site == "bye":
        return f"Week {game.get('week')}: bye."
    site_label = "vs." if site == "home" else "at"
    return (
        f"Week {game.get('week')}: {site_label} {game.get('opponent')} on {game.get('date')} "
        f"at {game.get('time')} ({game.get('network')}) — {game.get('venue')}."
    )


def _nfl_preseason_game_line(game: dict[str, object]) -> str:
    site = str(game.get("site") or "")
    site_label = "vs." if site == "home" else "at"
    return (
        f"Preseason Week {game.get('week')}: {site_label} {game.get('opponent')} on {game.get('date')} "
        f"at {game.get('time')} ({game.get('network')}) — {game.get('venue')}."
    )


def _public_nfl_schedule_live_query_response(text: str, role_context: str) -> Optional[str]:
    if role_context not in {"public", "home_local_guide"} or not _is_public_nfl_query(text):
        return None

    teams = _matching_nfl_teams(text)
    all_teams = list(_nfl_schedule_teams())
    if not all_teams:
        return "The 2026 NFL schedule guide is temporarily unavailable. Browse /events for current PerkNation event coverage."

    if not teams:
        conference = "AFC" if re.search(r"\bafc\b", text) else "NFC" if re.search(r"\bnfc\b", text) else ""
        if conference:
            names = [str(team.get("name")) for team in all_teams if team.get("conference") == conference]
            return (
                f"{conference} teams in the PerkNation 2026 NFL guide: {', '.join(names)}. "
                "Open /events and expand “Explore all 32 NFL teams” for every schedule, kickoff time, network, venue, and bye."
            )
        featured = [team for team in all_teams if team.get("featured")]
        lines = [
            "PerkNation now covers all 32 NFL teams, organized by AFC and NFC. The three featured California teams are:"
        ]
        for team in featured:
            opener = team.get("opener") if isinstance(team.get("opener"), dict) else {}
            lines.append(
                f"- {team.get('name')}: {_nfl_game_line(opener)} "
                f"Guide: /events/{team.get('slug')}"
            )
        lines.append("Open /events and expand “Explore all 32 NFL teams” to choose any club.")
        return "\n".join(lines)

    team = teams[0]
    schedule = team.get("schedule") if isinstance(team.get("schedule"), list) else []
    preseason = team.get("preseason") if isinstance(team.get("preseason"), list) else []
    if not schedule:
        return None
    opponent_team = teams[1] if len(teams) > 1 else None
    wants_preseason = _contains_any(text, ("preseason", "pre season", "exhibition"))
    if wants_preseason:
        if not preseason:
            return (
                f"The announced 2026 preseason schedule for {team.get('name')} is not available in the guide yet. "
                f"Check the official team schedule at {team.get('officialUrl')}."
            )
        if opponent_team:
            opponent_name = str(opponent_team.get("name") or "")
            game = next((item for item in preseason if item.get("opponent") == opponent_name), None)
            if game is None:
                return (
                    f"I could not find an announced 2026 preseason matchup between {team.get('name')} and "
                    f"{opponent_name}. See the full NFL guide at /nfl-2026-2027 or verify {team.get('officialUrl')}."
                )
            return (
                f"{team.get('name')} vs. {opponent_name}: {_nfl_preseason_game_line(game)} "
                f"See the team article at /events/{team.get('slug')} and the shareable 2026–27 NFL guide at "
                "/nfl-2026-2027. Confirm late broadcast or ticket changes on the official team schedule: "
                f"{team.get('officialUrl')}."
            )
        lines = [f"{team.get('name')} 2026 preseason schedule (Pacific Time):"]
        lines.extend(f"- {_nfl_preseason_game_line(item)}" for item in preseason)
        lines.append(
            f"Team article: /events/{team.get('slug')} | Shareable NFL guide: /nfl-2026-2027 | "
            f"Official schedule: {team.get('officialUrl')}"
        )
        return "\n".join(lines)

    week_match = re.search(r"\bweek\s*(\d{1,2})\b", text)
    game: Optional[dict[str, object]] = None
    if week_match:
        requested_week = int(week_match.group(1))
        game = next((item for item in schedule if int(item.get("week") or 0) == requested_week), None)
        if game is None:
            return f"The 2026 regular season has Weeks 1–18. Open /events/{team.get('slug')} for the complete {team.get('name')} schedule."
    elif opponent_team:
        opponent_name = str(opponent_team.get("name") or "")
        game = next((item for item in schedule if item.get("opponent") == opponent_name), None)
    elif _contains_any(text, ("home opener", "first home", "home game")):
        game = next((item for item in schedule if item.get("site") == "home"), None)
    elif _contains_any(text, ("full schedule", "all games", "every game", "all weeks")):
        lines = [f"{team.get('name')} 2026 regular-season schedule (Pacific Time):"]
        lines.extend(f"- {_nfl_game_line(item)}" for item in schedule)
        lines.append(
            f"Official schedule: {team.get('officialUrl')} | PerkNation guide: /events/{team.get('slug')}"
        )
        lines.append("Week 18 and other eligible games can change under NFL flexible scheduling.")
        return "\n".join(lines)
    else:
        game = schedule[0]

    if game is None:
        return (
            f"I could not find a 2026 regular-season matchup between {team.get('name')} and "
            f"{opponent_team.get('name') if opponent_team else 'that opponent'}. "
            f"Open /events/{team.get('slug')} for all announced weeks."
        )

    label = "home opener" if _contains_any(text, ("home opener", "first home")) else "2026 schedule"
    return (
        f"{team.get('name')} {label}: {_nfl_game_line(game)} "
        f"See all 18 weeks at /events/{team.get('slug')}. "
        f"Official NFL schedule: {team.get('officialUrl')}. "
        "Kickoff times are shown in Pacific Time and eligible games may flex."
    )


def _execute_live_query_if_requested(
    *,
    db: Optional[Session],
    current_user: Optional[User],
    role_context: str,
    message: str,
) -> Optional[str]:
    text = _normalize_user_text(message)
    if not text:
        return None

    public_nfl_response = _public_nfl_schedule_live_query_response(text, role_context)
    if public_nfl_response:
        return public_nfl_response

    if db is None:
        return None

    public_review_response = _public_review_live_query_response(text, role_context)
    if public_review_response:
        return public_review_response

    public_directory_response = _public_directory_live_query_response(db, text)
    if public_directory_response:
        return public_directory_response

    public_marketplace_response = _public_promotions_live_query_response(db, text)
    if public_marketplace_response:
        return public_marketplace_response

    if current_user is None:
        return None

    if _contains_any(text, ("what can you do", "help", "capabilities", "supported actions")):
        return _capabilities_for_role(role_context)

    if role_context == "consumer":
        return _consumer_live_query_response(db, current_user, text)

    if role_context == "merchant":
        return _merchant_live_query_response(db, current_user, text)

    if role_context == "admin":
        return _admin_live_query_response(db, current_user, text)

    return None


def _should_return_live_query_directly(message: str, role_context: str) -> bool:
    if role_context not in {"public", "home_local_guide"}:
        return False
    text = _normalize_user_text(message)
    if not text:
        return False
    if _is_public_review_query(text):
        return True
    if _is_public_nfl_query(text):
        return True
    return _contains_any(
        text,
        (
            "how many",
            "count",
            "total",
            "all promotions",
            "all promos",
            "all offers",
            "all deals",
            "what promotions",
            "what promos",
            "what offers",
            "what deals",
            "available promotions",
            "available promos",
            "available offers",
            "available deals",
        ),
    )


def _is_public_review_query(text: str) -> bool:
    return _contains_any(
        text,
        (
            "fashion event",
            "fashion events",
            "fashion week",
            "fashion weeks",
            "sports",
            "concert",
            "concerts",
            "warped",
            "vans",
            "festival",
            "festivals",
            "fan event",
            "fan events",
            "d23",
            "long beach",
            "pasadena event",
            "pasadena august",
            "rose bowl",
            "glendale event",
            "glendale events",
            "glendale august",
            "deukmejian",
            "brand park",
            "arcadia event",
            "arcadia events",
            "arcadia august",
            "626 night market",
            "arboretum",
            "santa monica event",
            "santa monica events",
            "santa monica august",
            "wellness & waves",
            "art on ocean",
            "ocean way festival",
            "laguna beach event",
            "laguna beach events",
            "laguna beach august",
            "laguna beach arts",
            "pageant of the masters",
            "passport to the arts",
            "laguna art museum",
            "orange county event",
            "orange county events",
            "orange county august",
            "oc fair",
            "sea country festival",
            "corn festival",
            "thefitexpo",
            "huntington beach event",
            "huntington beach events",
            "huntington beach august",
            "surf city nights",
            "life rolls on",
            "pier swim",
            "bolsa chica",
            "nisei week",
            "little tokyo",
            "cultural event",
            "cultural events",
            "restaurant review",
            "restaurant reviews",
            "restaurants listed",
            "listed for review",
            "review on perknation",
            "reviews on perknation",
            "listed on the website",
            "current listed",
            "current events",
            "website events",
        ),
    )


def _public_review_live_query_response(text: str, role_context: str) -> Optional[str]:
    text = _normalize_user_text(text)
    if role_context not in {"public", "home_local_guide"} or not _is_public_review_query(text):
        return None

    matching_items = []
    wants_fashion = _contains_any(text, ("fashion", "style", "shopping", "sample sale", "market week"))
    wants_sports = _contains_any(text, ("sports", "game", "games", "stadium", "ufc", "chargers", "rams"))
    wants_film = _contains_any(text, ("film", "films", "movie", "movies", "cinema", "burbank", "screening", "screenings", "q&a", "filmmaker"))
    wants_concerts = _contains_any(text, ("concert", "concerts", "music", "warped", "vans", "long beach", "pasadena", "south pasadena", "arcadia", "arboretum", "santa monica", "laguna beach", "huntington beach", "pageant", "sawdust", "art walk", "ocean way", "rose bowl", "kcon", "mount westmore")) or (
        not wants_film and _contains_any(text, ("festival", "festivals"))
    )
    wants_pasadena = _contains_any(text, ("pasadena", "rose bowl"))
    wants_south_pasadena = _contains_any(text, ("south pasadena", "garfield park", "mission street", "new romantics"))
    wants_burbank = _contains_any(text, ("burbank", "burbank film festival"))
    wants_glendale = _contains_any(text, ("glendale", "deukmejian", "brand park"))
    wants_arcadia = _contains_any(text, ("arcadia", "626 night market", "santa anita", "arboretum"))
    wants_orange_county = _contains_any(text, ("orange county", "oc fair", "sea country festival", "corn festival", "thefitexpo"))
    wants_santa_monica = _contains_any(text, ("santa monica", "wellness & waves", "art on ocean", "ocean way festival"))
    wants_laguna_beach = _contains_any(text, ("laguna beach", "pageant of the masters", "sawdust", "passport to the arts", "laguna art museum"))
    wants_long_beach = _contains_any(text, ("long beach", "stroll & savor", "taste of downtown", "jazz on the bay", "new blues festival"))
    wants_huntington_beach = _contains_any(text, ("huntington beach", "surf city", "life rolls on", "pier swim", "bolsa chica", "grunion"))
    wants_culture = _contains_any(text, ("nisei week", "little tokyo", "cultural event", "cultural events", "traditional arts"))
    wants_restaurants = _contains_any(text, ("restaurant", "restaurants", "dining", "dine la", "food", "food scene"))
    wants_d23 = _contains_any(text, ("d23", "anaheim fan event", "anaheim fan events", "anaheim convention"))
    wants_fan_events = _contains_any(text, ("fan event", "fan events", "convention", "conventions", "d23"))
    wants_all = not any((wants_fashion, wants_sports, wants_concerts, wants_film, wants_pasadena, wants_south_pasadena, wants_burbank, wants_glendale, wants_arcadia, wants_orange_county, wants_santa_monica, wants_laguna_beach, wants_long_beach, wants_huntington_beach, wants_culture, wants_restaurants, wants_d23, wants_fan_events))

    if wants_d23 and not wants_restaurants:
        return "\n".join(
            (
                "The current PerkNation D23 Anaheim guide covers seven priorities from August 11-16, 2026:",
                "- D23 currently lists Sunday full-day passes plus Saturday and Sunday afternoon-only passes starting at $49.",
                "- The August 7-10 reservation-assignment window has ended; standby is available for most Convention Center programming, but not Honda Center presentations.",
                "- Tonight's free Anaheim Packing District gathering runs 5-9 p.m.; Angel Stadium follows August 12, Disneyland Resort August 13, and the Ultimate Disney Fan Event August 14-16.",
                "- The guide also covers Muzeo's Walt Disney Archives exhibition and a flexible no-pass Anaheim fallback.",
                "Open /articles/d23-anaheim-2026-guide for best-for rankings, entry and bag guidance, official sources, ready-made plans, and links into 35 Anaheim directory listings.",
            )
        )

    if wants_orange_county and not wants_restaurants:
        return "\n".join(
            (
                "The current PerkNation Orange County guide ranks nine late-summer plans from August 10-September 6, 2026:",
                "- The OC Fair final stretch, D23 Anaheim week, and Laguna Beach's overlapping arts season.",
                "- Free OC Parks concerts and movies, Huntington Beach surf and nature programs, Sea Country Festival, and the La Habra Corn Festival.",
                "- TheFitExpo Anaheim and Orange International Street Fair planning.",
                "Open /articles/orange-county-august-2026-guide for best-for rankings, admission and parking notes, official sources, ready-made itineraries, and links into current Orange County city directories.",
            )
        )

    if wants_huntington_beach and not wants_restaurants:
        return "\n".join(
            (
                "The current PerkNation Huntington Beach guide ranks six coastal plans from August 8-29, 2026:",
                "- Life Rolls On adaptive surfing on August 22 and the Huntington Beach Pier Swim on August 29.",
                "- Bolsa Chica Grunion Runs, Junior Rangers, and Litter Getters.",
                "- The WSL50 surf-history exhibition and Tuesday Surf City Nights market evenings.",
                "Open /articles/huntington-beach-august-2026-guide for best-for notes, registration roles, ocean safety, late-night planning, official sources, and links into 43 Huntington Beach directory listings.",
            )
        )

    if wants_long_beach:
        return "\n".join(
            (
                "The current PerkNation Long Beach guide ranks eight late-August plans from August 10-30, 2026:",
                "- Stroll & Savor on August 19-20 and Taste of Downtown with KCRW on August 22.",
                "- The New Blues Festival on August 29-30, Jazz on the Bay, Moonlight Movies, and city summer programs.",
                "- Jaws on the Queen Mary and Little Earth Cinema, plus links into 208 Long Beach directory listings.",
                "Open /articles/long-beach-august-2026-guide for best-for rankings, ticket and parking notes, official sources, and ready-made local itineraries.",
            )
        )

    if wants_laguna_beach and not wants_restaurants:
        return "\n".join(
            (
                "The current PerkNation Laguna Beach guide ranks eight current late-summer arts plans from August 10-September 6, 2026:",
                "- Pageant of the Masters, Sawdust Art Festival, Festival of Arts, and Laguna Art-A-Fair.",
                "- The three-festival Passport to the Arts, which does not include the Pageant.",
                "- Laguna Art Museum, the final Music in the Park concert, and Music at the Promenade.",
                "Open /articles/laguna-beach-august-2026-guide for best-for notes, ticket distinctions, trolley and parking guidance, official sources, and links into 24 Laguna Beach directory listings.",
            )
        )

    if wants_santa_monica and not wants_restaurants:
        return "\n".join(
            (
                "The current PerkNation Santa Monica guide ranks six late-summer plans from August 15-September 27, 2026:",
                "- The remaining Sunset Swim on August 21.",
                "- Cinema by the Sea, free Wellness & Waves mornings, a free Pier history talk, and Downtown farmers markets.",
                "- Ocean Way Festival on September 26-27, with ticket and car-free arrival guidance to decide in August.",
                "Open /articles/santa-monica-august-2026-guide for best-for notes, reservations, coastal weather, street closures, transit, and official sources.",
            )
        )

    if wants_fashion and not any((wants_sports, wants_concerts, wants_restaurants)):
        return "\n".join(
            (
                "Upcoming dates in the PerkNation 2026 Fashion Week guide:",
                "- Los Angeles Market Week: August 2-6, with another market October 12-15 (trade credentials required).",
                "- Copenhagen Fashion Week: August 3-7.",
                "- Rakuten Fashion Week TOKYO: August 31-September 5.",
                "- New York Fashion Week: September 10-15.",
                "- London Fashion Week: September 17-21.",
                "- Milano Fashion Week: September 22-28.",
                "- Paris Fashion Week Womenswear: September 28-October 6.",
                "- Miami Fashion Week: October 13-17.",
                "Best starting points: New York for the U.S. industry overview, Milan and Paris for luxury, "
                "Copenhagen, London, and Tokyo for emerging perspectives, and Miami for international, resort, "
                "culture, and technology crossover. Read the rankings, access notes, and official-source links at "
                "/articles/la-fashion-events-2026.",
            )
        )

    if wants_south_pasadena and not wants_restaurants:
        return "\n".join(
            (
                "The current PerkNation South Pasadena guide ranks seven local plans from August 13-28, 2026:",
                "- The free New Romantics concert at Garfield Park on August 16.",
                "- Thursday farmers-market nights plus weekly singer-songwriter and musical-theater open mics.",
                "- The August 14-15 Tournament of Roses Yard Sale and August 17 and 21 family library activities.",
                "Open /articles/south-pasadena-august-2026-guide for best-for notes, current official sources, compact itineraries, and links into 97 South Pasadena directory listings.",
            )
        )

    if wants_burbank and not wants_restaurants:
        return "\n".join(
            (
                "The 2026 Burbank International Film Festival concluded on August 8, so PerkNation no longer presents it as an active event.",
                "The planning article remains available at /articles/burbank-film-festival-2026-guide as a reference to the completed screening week.",
                "For current local choices, browse /directory?city=Burbank for 968 Burbank listings and confirm new event dates with Visit Burbank or the event organizer.",
            )
        )

    if wants_pasadena and not wants_restaurants:
        return "\n".join(
            (
                "The current PerkNation Pasadena guide ranks seven August plans from August 14-30, 2026:",
                "- Noah Kahan at the Rose Bowl plus two Pasadena POPS nights.",
                "- Friday Nights at The Gamble House and Sunset Sessions.",
                "- America's Got Talent tapings, goat yoga, and Power Morphicon.",
                "Open /articles/pasadena-august-2026-guide for best-for notes, current access guidance, official sources, and links into 563 Pasadena directory listings.",
            )
        )

    if wants_glendale and not wants_restaurants:
        return "\n".join(
            (
                "The current PerkNation Glendale guide ranks six August plans from August 12-30, 2026:",
                "- The final summer concert and the free Wander the Wilderness Bus.",
                "- Classic Film Under the Stars and the Nature's Teamwork campfire.",
                "- Wilderness Workday and Montrose Harvest Market.",
                "Open /articles/glendale-august-2026-guide for best-for notes, RSVP and weather guidance, official city sources, and links into 100 Glendale directory listings.",
            )
        )

    if wants_arcadia and not wants_restaurants:
        return "\n".join(
            (
                "The current PerkNation Arcadia guide ranks four August outings from August 8-29, 2026:",
                "- 626 Night Market at Santa Anita Park from August 14-16.",
                "- Arboretum Summer Nights on August 21.",
                "- Pasadena POPS at the Arboretum on August 15 and 29.",
                "Open /articles/arcadia-august-2026-guide for best-for notes, parking, picnic, heat, and transit guidance, official sources, and links into 40 Arcadia directory listings.",
            )
        )

    for item in _PUBLIC_REVIEW_COVERAGE_ITEMS:
        category = str(item["category"]).lower()
        if (
            wants_all
            or (wants_fashion and "fashion" in category)
            or (wants_sports and "sports" in category)
            or (wants_concerts and "concert" in category)
            or (wants_film and "film" in category)
            or (wants_culture and any(token in category for token in ("culture", "traditional arts")))
            or (wants_restaurants and "restaurant" in category)
            or (wants_fan_events and "fan event" in category)
        ):
            matching_items.append(item)

    if not matching_items:
        matching_items = list(_PUBLIC_REVIEW_COVERAGE_ITEMS)

    lines = ["Here are the current PerkNation guides and events that match your question:"]
    for item in matching_items:
        lines.append(
            "- "
            f"{item['category']} in {item['city']}: {item['title']} ({item['timing']}). "
            f"Open {item['route']} for the guide. {item['details']}"
        )
    lines.append(
        "Looking for deals instead? Ask for current promotions by city or category."
    )
    return "\n".join(lines)


def _public_promotions_live_query_response(db: Session, text: str) -> Optional[str]:
    mentions_offer_context = _contains_any(
        text,
        (
            "offer",
            "offers",
            "promo",
            "promos",
            "promotion",
            "promotions",
            "deal",
            "deals",
            "discount",
            "discounts",
            "perk",
            "perks",
        ),
    )
    if not mentions_offer_context:
        return None

    asks_available = _contains_any(
        text,
        (
            "how many",
            "count",
            "total",
            "all",
            "available",
            "current",
            "active",
            "what",
            "list",
            "show",
        ),
    )
    if not asks_available:
        return None

    now = datetime.now(timezone.utc)
    active_filter = and_(
        Offer.approval_status == OfferStatus.approved,
        Offer.starts_at <= now,
        Offer.ends_at >= now,
    )
    total = int(db.scalar(select(func.count()).select_from(Offer).where(active_filter)) or 0)
    offers = db.scalars(
        select(Offer)
        .options(selectinload(Offer.merchant), selectinload(Offer.location))
        .where(active_filter)
        .order_by(desc(Offer.created_at), desc(Offer.id))
        .limit(20)
    ).all()

    lines = [f"There are {total:,} active PerkNation promotions/offers right now."]
    if offers:
        lines.append("Here are current examples:")
        for offer in offers:
            merchant = offer.merchant_name or f"Merchant #{offer.merchant_id}"
            location = f" at {offer.location.name}" if offer.location else ""
            lines.append(f"- {merchant}{location}: {offer.title}")
        if total > len(offers):
            lines.append("Ask for a city, ZIP, merchant, or category to narrow the full active offer list.")
    return "\n".join(lines)


def _public_directory_live_query_response(db: Session, text: str) -> Optional[str]:
    wants_count = _contains_any(
        text,
        (
            "how many",
            "number of",
            "count",
            "total",
            "total number",
        ),
    )
    mentions_offer_context = _contains_any(
        text,
        (
            "offer",
            "offers",
            "promo",
            "promos",
            "promotion",
            "promotions",
            "deal",
            "deals",
            "discount",
            "discounts",
        ),
    )
    mentions_directory = _contains_any(
        text,
        (
            "business directory",
            "local business directory",
            "business listing",
            "business listings",
            "local business listing",
            "local business listings",
            "local businesses",
            "businesses on",
            "businesses in the directory",
            "listings available",
            "directory",
        ),
    )
    mentions_california_total = _contains_any(text, ("california", "ca")) and _contains_any(
        text,
        (
            "in total",
            "total in",
            "total across",
            "statewide",
            "state wide",
        ),
    )
    if not (wants_count and (mentions_directory or mentions_california_total)) or mentions_offer_context:
        return None

    try:
        active_count = int(
            db.execute(
                sql_text(
                    "SELECT COUNT(*) FROM business_directory_entries "
                    "WHERE is_active IS TRUE"
                )
            ).scalar()
            or 0
        )
        total_count = int(db.execute(sql_text("SELECT COUNT(*) FROM business_directory_entries")).scalar() or 0)
    except Exception:
        return None

    inactive_count = max(total_count - active_count, 0)
    if inactive_count:
        return (
            f"There are {active_count:,} active businesses in the PerkNation local business directory "
            f"({total_count:,} total records, including {inactive_count:,} inactive)."
        )
    return f"There are {active_count:,} active businesses in the PerkNation local business directory."


def _consumer_live_query_response(db: Session, current_user: User, text: str) -> Optional[str]:
    wants_all = _contains_any(
        text,
        ("all info", "all information", "all that information", "everything", "full account", "full profile"),
    )
    wants_profile = wants_all or _contains_any(
        text,
        ("my name", "who am i", "profile", "personal data", "account details", "my email"),
    )
    wants_wallet = wants_all or _contains_any(
        text,
        (
            "wallet",
            "balance",
            "available",
            "pending",
            "pass",
            "passes",
        ),
    )
    wants_offers = wants_all or _contains_any(
        text,
        ("offer", "offers", "promo", "promotion", "deal", "deals", "nearby"),
    )
    wants_transactions = wants_all or _contains_any(
        text,
        ("transaction", "transactions", "history", "purchase", "purchases", "spent"),
    )

    if not any((wants_profile, wants_wallet, wants_offers, wants_transactions)):
        return None

    now = datetime.now(timezone.utc)
    lines: list[str] = [f"Live account data (as of {now.isoformat()}):"]

    if wants_profile:
        lines.extend(
            [
                "",
                "Profile",
                f"- Name: {current_user.full_name}",
                f"- Email: {current_user.email}",
                f"- Role: {current_user.role.value}",
            ]
        )

    if wants_wallet:
        lines.extend(
            [
                "",
                "Wallet",
                "- Cashback and stock rewards are not active on PerkNation right now.",
                "- Current passes and purchase history are shown in the account page when available.",
            ]
        )

    if wants_offers:
        active_offers = db.scalars(
            select(Offer)
            .options(selectinload(Offer.merchant), selectinload(Offer.location))
            .where(
                and_(
                    Offer.approval_status == OfferStatus.approved,
                    Offer.starts_at <= now,
                    Offer.ends_at >= now,
                )
            )
            .order_by(desc(Offer.created_at), desc(Offer.id))
            .limit(10)
        ).all()
        active_offers = [offer for offer in active_offers if is_current_confirmed_offer(offer)]
        activated_offer_ids = set(
            db.scalars(
                select(OfferActivation.offer_id).where(OfferActivation.user_id == current_user.id)
            ).all()
        )
        lines.extend(["", "Active offers"])
        if not active_offers:
            lines.append("- None right now")
        else:
            for offer in active_offers:
                merchant = offer.merchant_name or f"Merchant #{offer.merchant_id}"
                status = "activated" if offer.id in activated_offer_ids else "not activated"
                lines.append(
                    f"- [{offer.id}] {offer.title} at {merchant} ({status}, ends {offer.ends_at.isoformat()})"
                )

    if wants_transactions:
        txns = db.scalars(
            select(Transaction)
            .options(selectinload(Transaction.offer).selectinload(Offer.merchant))
            .where(Transaction.user_id == current_user.id)
            .order_by(desc(Transaction.occurred_at), desc(Transaction.id))
            .limit(5)
        ).all()
        lines.extend(["", "Recent transactions"])
        if not txns:
            lines.append("- None yet")
        else:
            for txn in txns:
                merchant = txn.merchant_name or f"Merchant #{txn.merchant_id or '-'}"
                lines.append(
                    f"- Txn {txn.id}: {merchant}, {_fmt_usd(Decimal(txn.amount))}, "
                    f"{txn.status.value}, {txn.occurred_at.isoformat()}"
                )

    return "\n".join(lines)


def _merchant_live_query_response(db: Session, current_user: User, text: str) -> Optional[str]:
    if not _contains_any(
        text,
        (
            "all info",
            "all information",
            "everything",
            "metrics",
            "kpi",
            "analytics",
            "overview",
            "offers",
            "transactions",
            "activations",
            "volume",
            "merchant profile",
        ),
    ):
        return None
    return "Live merchant data:\n" + _merchant_snapshot(db, current_user)


def _admin_live_query_response(db: Session, current_user: User, text: str) -> Optional[str]:
    if not _contains_any(
        text,
        (
            "all info",
            "all information",
            "everything",
            "overview",
            "admin",
            "metrics",
            "analytics",
            "approvals",
            "tickets",
            "disputes",
            "risk",
            "users",
        ),
    ):
        return None
    return "Live admin data:\n" + _admin_snapshot(db, current_user)


def _capabilities_for_role(role_context: str) -> str:
    if role_context == "consumer":
        return (
            "I can help with your live consumer account data, current offers, wallet passes, purchase history, "
            "profile settings, and referrals. Cashback and stock rewards are not active on PerkNation right now."
        )
    if role_context == "merchant":
        return "I can read your live merchant profile, offer metrics, activations, and attributed transaction volume."
    if role_context == "admin":
        return "I can read live admin operations metrics: users, pending approvals, open tickets, and open disputes."
    if role_context == "home_local_guide":
        return (
            "I can help with current PerkNation promotions, business-directory listings, nearby categories, "
            "fashion/events/sports/concert/restaurant review coverage, and local discovery recommendations. "
            "Confirmed promos include Hollywood Sports paintball tickets, Bond Collective workspace services, "
            "jewelry discounts, and El Portal World Cup game-day happy hour; Pasadena restaurant picks are recommendations. "
            "I keep promotions separate from broader business listings and editorial guides."
        )
    return "I can answer public product and onboarding questions."


def _fallback_assistant_response(
    *,
    db: Optional[Session],
    current_user: Optional[User],
    role_context: str,
    unavailable_reason: str,
) -> str:
    lines: list[str] = [
        "Live AI chat is temporarily unavailable, but I can still help with live PerkNation data and supported actions."
    ]

    detail = unavailable_reason.strip()
    if detail:
        lines.append(f"Status: {detail}")

    summary = _deterministic_summary_for_role(
        db=db,
        current_user=current_user,
        role_context=role_context,
    )
    if summary:
        lines.extend(["", summary])
    else:
        lines.extend(["", _capabilities_for_role(role_context)])

    return "\n".join(lines)


def _deterministic_summary_for_role(
    *,
    db: Optional[Session],
    current_user: Optional[User],
    role_context: str,
) -> Optional[str]:
    if db is None or current_user is None:
        return None

    if role_context == "consumer":
        return _consumer_live_query_response(db, current_user, "all info")

    if role_context == "merchant":
        return _merchant_live_query_response(db, current_user, "all info")

    if role_context == "admin":
        return _admin_live_query_response(db, current_user, "all info")

    return _capabilities_for_role(role_context)


def _redeem_available_cash_rewards(*, db: Session, current_user: User) -> str:
    rewards = db.scalars(
        select(RewardLedgerEntry).where(
            RewardLedgerEntry.user_id == current_user.id,
            RewardLedgerEntry.state == RewardState.available,
            RewardLedgerEntry.reward_type == RewardPreference.cash,
        )
    ).all()

    if not rewards:
        return "No available cash rewards were found, so nothing was redeemed."

    total = Decimal("0")
    for reward in rewards:
        total += Decimal(reward.reward_amount)
        reward.state = RewardState.paid

    log_action(
        db,
        actor=current_user,
        action="ai.reward.redeem",
        object_type="reward",
        object_id=",".join(str(r.id) for r in rewards),
        after_snapshot=f"count={len(rewards)};total={_fmt_usd(total)}",
    )

    db.commit()
    return f"Action complete: redeemed {len(rewards)} cash reward(s) totaling {_fmt_usd(total)}."


def _settle_pending_rewards(*, db: Session, current_user: User) -> str:
    rewards = db.scalars(
        select(RewardLedgerEntry).where(
            RewardLedgerEntry.user_id == current_user.id,
            RewardLedgerEntry.state == RewardState.pending,
        )
    ).all()

    if not rewards:
        return "No pending rewards were found, so nothing was settled."

    settled_at = datetime.now(timezone.utc)
    for reward in rewards:
        reward.state = RewardState.available
        reward.settled_at = settled_at

    log_action(
        db,
        actor=current_user,
        action="ai.reward.settle",
        object_type="reward",
        object_id=",".join(str(r.id) for r in rewards),
        after_snapshot=f"count={len(rewards)}",
    )

    db.commit()
    return f"Action complete: settled {len(rewards)} reward(s) to available."


def _sum_rewards(db: Session, user_id: int, state: RewardState, reward_type: RewardPreference) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(RewardLedgerEntry.reward_amount), 0)).where(
            RewardLedgerEntry.user_id == user_id,
            RewardLedgerEntry.state == state,
            RewardLedgerEntry.reward_type == reward_type,
        )
    )
    return _quantize_usd(Decimal(value or 0))


def _sum_stock_conversions(db: Session, user_id: int) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(StockConversion.amount_usd), 0)).where(
            StockConversion.user_id == user_id,
        )
    )
    return _quantize_usd(Decimal(value or 0))


def _quantize_usd(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _fmt_usd(value: Decimal) -> str:
    quantized = _quantize_usd(value)
    return f"${quantized:,.2f}"


def _normalize_user_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _should_include_live_context(
    *,
    message: str,
    role_context: str,
    query_result: Optional[str],
) -> bool:
    if query_result:
        return True

    text = _normalize_user_text(message)
    if not text:
        return False

    if role_context == "consumer":
        return _contains_any(
            text,
            (
                "my ",
                "account",
                "wallet",
                "balance",
                "offer",
                "offers",
                "promo",
                "promotion",
                "deal",
                "deals",
                "reward",
                "rewards",
                "transaction",
                "transactions",
                "referral",
                "profile",
                "settings",
            ),
        )

    if role_context == "merchant":
        return _contains_any(
            text,
            (
                "merchant",
                "offer",
                "offers",
                "location",
                "locations",
                "activation",
                "activations",
                "transaction",
                "transactions",
                "volume",
                "kpi",
                "analytics",
            ),
        )

    if role_context == "admin":
        return _contains_any(
            text,
            (
                "admin",
                "approval",
                "approvals",
                "dispute",
                "disputes",
                "ticket",
                "tickets",
                "risk",
                "fraud",
                "analytics",
                "users",
                "orders",
            ),
        )

    return False
