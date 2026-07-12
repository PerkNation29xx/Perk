from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
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
    include_public_directory_context = (
        db is not None
        and role_context in {"public", "home_local_guide"}
        and _is_public_directory_search_query(message)
    )
    include_local_discovery_context = (
        db is not None
        and should_attempt_local_discovery_context(message)
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

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

    body = {
        "hostId": host_id,
        "model": model_name,
        "messages": messages,
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
            "Use HOME LOCAL GUIDE CONTEXT, LIVE QUERY RESULT, PUBLIC BUSINESS DIRECTORY CONTEXT, LOCAL DISCOVERY CONTEXT, and LA RESTAURANT KNOWLEDGE CONTEXT as authoritative. "
            "Keep three concepts separate: active PerkNation promotions/offers, public business-directory listings, and local restaurant or discovery recommendations. "
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
            "Restaurant guide examples currently surfaced on the homepage:",
            "- Union, Agnes, Fishwives, Perle, Bone Kettle, Osawa, Panda Inn, and Pez Coastal Kitchen are Pasadena restaurant recommendations, not discount offers unless another promo says so.",
            "",
            "Answering rules:",
            "- Keep offer counts separate from business-directory listing counts.",
            "- If asked for all promotions, summarize active PerkNation offers from live data and offer to narrow by merchant, city, ZIP, or category.",
            "- If asked for business listings, answer from the public directory count or directory search context, not the offer count.",
            "- If asked for recommendations, use local discovery or restaurant context and make clear it is a shortlist, not the total directory.",
        ]
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


def _execute_live_query_if_requested(
    *,
    db: Optional[Session],
    current_user: Optional[User],
    role_context: str,
    message: str,
) -> Optional[str]:
    if db is None:
        return None

    text = _normalize_user_text(message)
    if not text:
        return None

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
            "and local restaurant or discovery recommendations. I keep promotions separate from broader business listings."
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
