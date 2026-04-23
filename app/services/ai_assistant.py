from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Optional
from urllib import error, request

from sqlalchemy import and_, desc, func, select
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


class AIServiceError(RuntimeError):
    pass


@dataclass
class AIChatResult:
    answer: str
    model: str
    role_context: str


_ALLOWED_CONTEXTS = {"consumer", "merchant", "admin", "public"}
_DETERMINISTIC_MODEL_NAME = "perk-deterministic"


def resolve_context(user_role: Optional[UserRole], requested_context: Optional[str]) -> str:
    requested = (requested_context or "").strip().lower()
    if requested not in _ALLOWED_CONTEXTS:
        requested = ""

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
        return settings.ollama_model
    return settings.ollama_model


def chat_with_assistant(
    *,
    message: str,
    history: Optional[list[dict[str, str]]],
    db: Optional[Session] = None,
    current_user: Optional[User] = None,
    user_role: Optional[UserRole] = None,
    requested_context: Optional[str] = None,
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

    # Deterministic read/query hooks for live account data.
    query_result = _execute_live_query_if_requested(
        db=db,
        current_user=current_user,
        role_context=role_context,
        message=message,
    )
    if query_result:
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

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

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

    messages.extend(normalized_history)
    messages.append({"role": "user", "content": message.strip()})

    providers_to_try: list[str] = [provider]
    # Keep iOS/web AI available even if local Ollama config drifts in hosted env.
    if provider == "ollama" and (settings.spark_public_base_url or "").strip():
        providers_to_try.append("spark")

    model = _configured_model_for_provider(provider)
    answer = ""
    last_error: Optional[AIServiceError] = None

    for candidate in providers_to_try:
        try:
            if candidate == "openai":
                model, answer = _request_openai_chat(messages)
            elif candidate == "spark":
                model, answer = _request_spark_chat(messages)
            else:
                model, answer = _request_ollama_chat(messages)
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

    if len(answer) > 6000:
        answer = answer[:6000].rstrip() + "\n\n[truncated]"

    return AIChatResult(answer=answer, model=model, role_context=role_context)


def _request_ollama_chat(messages: list[dict[str, str]]) -> tuple[str, str]:
    body = {
        "model": settings.ollama_model,
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

    model = str(envelope.get("model") or settings.ollama_model)
    answer = ""
    message_obj = envelope.get("message")
    if isinstance(message_obj, dict):
        answer = str(message_obj.get("content") or "").strip()
    if not answer:
        answer = str(envelope.get("response") or "").strip()
    return model, answer


def _request_spark_chat(messages: list[dict[str, str]]) -> tuple[str, str]:
    base = (settings.spark_public_base_url or "").strip()
    if not base:
        raise AIServiceError(
            "AI service is unreachable. SPARK_PUBLIC_BASE_URL is not configured on this backend."
        )

    host_id = (settings.spark_chat_host_id or "mini").strip().lower()
    if host_id not in {"spark", "mini"}:
        host_id = "mini"

    body = {
        "hostId": host_id,
        "model": settings.ollama_model,
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

    model = str(envelope.get("model") or settings.ollama_model)
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
    for item in history[-12:]:
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue

        content = str(item.get("content") or "").strip()
        if not content:
            continue

        if len(content) > 1500:
            content = content[:1500]

        items.append({"role": role, "content": content})
    return items


def _system_prompt_for_context(role_context: str) -> str:
    shared = (
        "You are PerkNation AI assistant. Be concise, practical, and accurate. "
        "Never request passwords, one-time codes, or private keys. "
        "If LIVE ACCOUNT DATA is included, use it as source of truth. "
        "If policy/financial/legal advice is requested, provide general guidance and suggest contacting a qualified professional."
    )

    if role_context == "merchant":
        return (
            f"{shared} Focus on merchant operations: offers, locations, activations, transactions, and growth tactics. "
            "Use numbered steps when giving operational instructions."
        )

    if role_context == "admin":
        return (
            f"{shared} Focus on admin operations: approvals, disputes, fraud/risk, analytics, and governance. "
            "Prefer measurable recommendations and mention tradeoffs."
        )

    if role_context == "consumer":
        return (
            f"{shared} Focus on consumer experience: nearby offers, wallet, rewards, referrals, and profile preferences. "
            "If user asks to redeem/settle, require explicit phrase 'confirm redeem' or 'confirm settle'."
        )

    return (
        f"{shared} Focus on public PerkNation product education and onboarding guidance. "
        "Keep responses in plain language."
    )


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

    available_cash = _sum_rewards(db, current_user.id, RewardState.available, RewardPreference.cash)
    pending_cash = _sum_rewards(db, current_user.id, RewardState.pending, RewardPreference.cash)
    stock_balance = _sum_stock_conversions(db, current_user.id)

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
    lines.append(f"reward_preference: {current_user.reward_preference.value}")
    lines.append(f"wallet_available_cash: {_fmt_usd(available_cash)}")
    lines.append(f"wallet_pending_cash: {_fmt_usd(pending_cash)}")
    lines.append(f"stock_vault_balance: {_fmt_usd(stock_balance)}")

    if active_offers:
        lines.append("active_offers:")
        for offer in active_offers:
            merchant = offer.merchant_name or f"Merchant #{offer.merchant_id}"
            activated = "yes" if offer.id in activated_offer_ids else "no"
            lines.append(
                f"- offer_id={offer.id}; merchant={merchant}; cash_rate={offer.reward_rate_cash}; "
                f"stock_rate={offer.reward_rate_stock}; activated={activated}; ends_at={offer.ends_at.isoformat()}"
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
                f"cash_rate={offer.reward_rate_cash}; ends_at={offer.ends_at.isoformat()}"
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
        return _redeem_available_cash_rewards(db=db, current_user=current_user)

    if "confirm settle" in lower:
        return _settle_pending_rewards(db=db, current_user=current_user)

    return None


def _execute_live_query_if_requested(
    *,
    db: Optional[Session],
    current_user: Optional[User],
    role_context: str,
    message: str,
) -> Optional[str]:
    if db is None or current_user is None:
        return None

    text = _normalize_user_text(message)
    if not text:
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
            "reward balance",
            "cash rewards",
            "stock balance",
            "stock vault",
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
                f"- Reward preference: {current_user.reward_preference.value}",
            ]
        )

    if wants_wallet:
        available_cash = _sum_rewards(db, current_user.id, RewardState.available, RewardPreference.cash)
        pending_cash = _sum_rewards(db, current_user.id, RewardState.pending, RewardPreference.cash)
        stock_balance = _sum_stock_conversions(db, current_user.id)
        lines.extend(
            [
                "",
                "Wallet",
                f"- Available cash rewards: {_fmt_usd(available_cash)}",
                f"- Pending cash rewards: {_fmt_usd(pending_cash)}",
                f"- Stock vault balance: {_fmt_usd(stock_balance)}",
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
                    f"- [{offer.id}] {merchant}: {offer.reward_rate_cash} cash / {offer.reward_rate_stock} stock "
                    f"({status}, ends {offer.ends_at.isoformat()})"
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

    lines.extend(
        [
            "",
            "Available commands",
            "- Type `confirm redeem` to redeem all available cash rewards.",
            "- Type `confirm settle` to move pending rewards to available.",
        ]
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
            "I can read your live consumer account data (profile, wallet, active offers, transactions) "
            "and perform confirmed reward actions.\n\n"
            "Commands:\n"
            "- `confirm settle` -> move pending rewards to available.\n"
            "- `confirm redeem` -> redeem all available cash rewards."
        )
    if role_context == "merchant":
        return "I can read your live merchant profile, offer metrics, activations, and attributed transaction volume."
    if role_context == "admin":
        return "I can read live admin operations metrics: users, pending approvals, open tickets, and open disputes."
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
