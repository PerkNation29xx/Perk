from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_current_user
from app.db.models import User
from app.schemas import AIChatRequest, AIChatResponse
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
