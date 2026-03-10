from __future__ import annotations

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.models import WebLeadSubmission
from app.db.session import SessionLocal


def _sessionmaker_for(url: str) -> sessionmaker[Session]:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
    Base.metadata.create_all(bind=engine, tables=[WebLeadSubmission.__table__])
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def main() -> None:
    backup_url = (settings.forms_backup_database_url or "").strip()
    if not settings.forms_backup_enabled:
        print("FORMS_BACKUP_ENABLED=false; skipping backup sync.")
        return
    if not backup_url:
        print("FORMS_BACKUP_DATABASE_URL is empty; skipping backup sync.")
        return

    backup_sessionmaker = _sessionmaker_for(backup_url)

    with SessionLocal() as primary_db:
        rows = primary_db.scalars(select(WebLeadSubmission).order_by(WebLeadSubmission.created_at.asc())).all()

    with backup_sessionmaker() as backup_db:
        backup_db.execute(delete(WebLeadSubmission))
        backup_db.commit()

        for row in rows:
            backup_db.add(
                WebLeadSubmission(
                    form_type=row.form_type,
                    source_page=row.source_page,
                    name=row.name,
                    company=row.company,
                    email=row.email,
                    phone=row.phone,
                    website=row.website,
                    address=row.address,
                    dob=row.dob,
                    inquiry=row.inquiry,
                    contact_name=row.contact_name,
                    payload_json=row.payload_json,
                    ip_address=row.ip_address,
                    user_agent=row.user_agent,
                    created_at=row.created_at,
                )
            )
        backup_db.commit()

    print(f"Synced {len(rows)} web form submissions to backup DB: {backup_url}")


if __name__ == "__main__":
    main()
