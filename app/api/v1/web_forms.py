from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import WebLeadSubmission
from app.schemas import WebFormSubmitRequest, WebFormSubmitResponse
from app.services.web_forms_backup import mirror_web_form_submission

router = APIRouter(prefix="/web/forms", tags=["web-forms"])

_FORM_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "guest": ("full_name", "address", "phone", "email", "dob"),
    "merchant": ("company", "address", "email", "phone", "contact_name"),
    "contact": ("name", "email", "inquiry"),
}

_MAX_FIELDS = 64
_MAX_FIELD_NAME = 64
_MAX_FIELD_VALUE = 4000
_MAX_PAYLOAD_JSON = 20000
_SAFE_FIELD_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_data(raw: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_key, raw_value in raw.items():
        key = str(raw_key).strip().lower()
        if not key:
            continue
        if len(key) > _MAX_FIELD_NAME or not _SAFE_FIELD_RE.match(key):
            raise HTTPException(status_code=400, detail=f"Invalid field name: {key!r}")

        value = str(raw_value).strip()
        if len(value) > _MAX_FIELD_VALUE:
            raise HTTPException(status_code=400, detail=f"Field too long: {key}")
        normalized[key] = value

    if len(normalized) > _MAX_FIELDS:
        raise HTTPException(status_code=400, detail="Too many fields submitted")

    return normalized


def _client_ip(request: Request) -> str | None:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()[:64] or None

    if request.client and request.client.host:
        return request.client.host[:64]
    return None


@router.post("/{form_type}", response_model=WebFormSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_public_web_form(
    form_type: str,
    payload: WebFormSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> WebFormSubmitResponse:
    normalized_form_type = form_type.strip().lower()
    required_fields = _FORM_REQUIREMENTS.get(normalized_form_type)
    if not required_fields:
        raise HTTPException(status_code=404, detail="Form type not supported")

    data = _normalize_data(payload.data)
    if not data:
        raise HTTPException(status_code=400, detail="Form data is required")

    missing = [field for field in required_fields if not data.get(field)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    email = (data.get("email") or "").strip().lower()
    if email and (len(email) > 255 or not _EMAIL_RE.match(email)):
        raise HTTPException(status_code=400, detail="Invalid email address")

    source_page = (payload.source_page or "").strip() or request.url.path
    if len(source_page) > 255:
        source_page = source_page[:255]

    payload_json = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(payload_json) > _MAX_PAYLOAD_JSON:
        raise HTTPException(status_code=400, detail="Form payload too large")

    row = WebLeadSubmission(
        form_type=normalized_form_type,
        source_page=source_page,
        name=(data.get("name") or data.get("full_name") or data.get("contact_name") or None),
        company=data.get("company"),
        email=email or None,
        phone=data.get("phone"),
        website=data.get("website"),
        address=data.get("address"),
        dob=data.get("dob"),
        inquiry=data.get("inquiry"),
        contact_name=data.get("contact_name"),
        payload_json=payload_json,
        ip_address=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "").strip()[:255] or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    mirrored = mirror_web_form_submission(
        {
            "form_type": row.form_type,
            "source_page": row.source_page,
            "name": row.name,
            "company": row.company,
            "email": row.email,
            "phone": row.phone,
            "website": row.website,
            "address": row.address,
            "dob": row.dob,
            "inquiry": row.inquiry,
            "contact_name": row.contact_name,
            "payload_json": row.payload_json,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "created_at": row.created_at,
        }
    )

    return WebFormSubmitResponse(
        message="Form submitted successfully",
        submission_id=row.id,
        mirrored_to_backup=mirrored,
    )
