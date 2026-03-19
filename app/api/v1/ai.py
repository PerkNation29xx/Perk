from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_optional_current_user
from app.core.config import settings
from app.db.models import PrivateAssistantAuthor, PrivateAssistantMessage, User, UserRole
from app.schemas import (
    AIChatRequest,
    AIChatResponse,
    PrivateAssistantMessageCreate,
    PrivateAssistantMessageOut,
    PrivateAssistantMessageSendResponse,
)
from app.services.ai_assistant import AIServiceError, chat_with_assistant

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/chat", response_model=AIChatResponse)
def ai_chat(
    payload: AIChatRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> AIChatResponse:
    requested = (payload.context or "").strip().lower()
    if requested in {"consumer", "merchant", "admin"} and current_user is None:
        raise HTTPException(status_code=401, detail="Sign in is required for private AI context.")

    try:
        result = chat_with_assistant(
            message=payload.message,
            history=[{"role": item.role, "content": item.content} for item in payload.history],
            db=db,
            current_user=current_user,
            user_role=current_user.role if current_user else None,
            requested_context=payload.context,
        )
    except AIServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return AIChatResponse(
        answer=result.answer,
        model=result.model,
        role_context=result.role_context,
    )


def _message_allowlist() -> tuple[str, str]:
    admin_email = (settings.owner_admin_message_email or "").strip().lower()
    ios_email = (settings.owner_ios_message_email or "").strip().lower()
    return admin_email, ios_email


def _require_private_message_access(current_user: User) -> None:
    email = (current_user.email or "").strip().lower()
    admin_email, ios_email = _message_allowlist()

    if email == admin_email:
        if current_user.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Forbidden")
        return

    if email == ios_email:
        return

    raise HTTPException(status_code=403, detail="Forbidden")


def _to_private_message_out(row: PrivateAssistantMessage) -> PrivateAssistantMessageOut:
    return PrivateAssistantMessageOut(
        id=row.id,
        author=row.author.value,
        message=row.message,
        model=row.model,
        created_at=row.created_at,
    )


@router.get("/messages", response_model=list[PrivateAssistantMessageOut])
def list_private_messages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PrivateAssistantMessageOut]:
    _require_private_message_access(current_user)

    rows = db.scalars(
        select(PrivateAssistantMessage)
        .where(PrivateAssistantMessage.user_id == current_user.id)
        .order_by(PrivateAssistantMessage.created_at.asc(), PrivateAssistantMessage.id.asc())
        .limit(500)
    ).all()
    return [_to_private_message_out(row) for row in rows]


@router.post("/messages", response_model=PrivateAssistantMessageSendResponse)
def send_private_message(
    payload: PrivateAssistantMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrivateAssistantMessageSendResponse:
    _require_private_message_access(current_user)

    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message is required.")

    recent_rows = db.scalars(
        select(PrivateAssistantMessage)
        .where(PrivateAssistantMessage.user_id == current_user.id)
        .order_by(desc(PrivateAssistantMessage.created_at), desc(PrivateAssistantMessage.id))
        .limit(10)
    ).all()
    history = [
        {"role": row.author.value, "content": row.message}
        for row in reversed(recent_rows)
    ]

    user_entry = PrivateAssistantMessage(
        user_id=current_user.id,
        user_email=(current_user.email or "").strip().lower(),
        author=PrivateAssistantAuthor.user,
        message=message_text,
    )
    db.add(user_entry)
    db.flush()

    try:
        result = chat_with_assistant(
            message=message_text,
            history=history,
            db=db,
            current_user=current_user,
            user_role=current_user.role,
            requested_context="admin" if current_user.role == UserRole.admin else "consumer",
        )
        assistant_text = result.answer
        model_name = result.model
    except AIServiceError as exc:
        assistant_text = (
            "I could not reach the AI service right now. "
            "Please try again in a moment. "
            f"Details: {str(exc).strip()}"
        )
        model_name = "unavailable"

    assistant_entry = PrivateAssistantMessage(
        user_id=current_user.id,
        user_email=(current_user.email or "").strip().lower(),
        author=PrivateAssistantAuthor.assistant,
        message=assistant_text,
        model=model_name,
    )
    db.add(assistant_entry)
    db.commit()
    db.refresh(user_entry)
    db.refresh(assistant_entry)

    return PrivateAssistantMessageSendResponse(
        user_message=_to_private_message_out(user_entry),
        assistant_message=_to_private_message_out(assistant_entry),
        model=model_name,
    )
