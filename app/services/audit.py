from __future__ import annotations
from sqlalchemy.orm import Session
from typing import Optional

from app.db.models import AuditLog, User


def log_action(
    db: Session,
    *,
    actor: Optional[User],
    action: str,
    object_type: str,
    object_id: str,
    before_snapshot: Optional[str] = None,
    after_snapshot: Optional[str] = None,
) -> None:
    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else "system",
        action=action,
        object_type=object_type,
        object_id=object_id,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )
    db.add(entry)
