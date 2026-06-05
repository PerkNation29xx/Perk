from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import get_db
from app.services.campaign_passes import (
    checkout_ticket_from_payload,
    ensure_paid_order_pass,
    find_checkout_ticket_by_pass_code,
    find_checkout_ticket_by_wallet_serial,
    list_wallet_pass_updates_for_device,
    register_wallet_device,
    unregister_wallet_device,
    wallet_pass_authorized,
)
from app.services.wallet_passes import (
    WalletPassConfigurationError,
    WalletPassSigningError,
    wallet_pass_service,
)


router = APIRouter(prefix="/wallet", tags=["wallet"])
logger = logging.getLogger(__name__)


def _wallet_pass_context(
    *,
    db: Session,
    code: str,
    title: str,
    payload: str,
    template: str,
) -> dict[str, str]:
    if template != "perknation":
        return {}

    lookup = find_checkout_ticket_by_pass_code(db, code)
    if lookup is None:
        return {}

    row, stored_payload, resolved_code, _, ticket = lookup
    if str(stored_payload.get("payment_status") or "").strip().lower() == "paid":
        stored_payload = ensure_paid_order_pass(db, row, notify_customer=False)
        _, ticket, _ = checkout_ticket_from_payload(stored_payload, resolved_code)

    pass_data = ticket if isinstance(ticket, dict) else stored_payload

    return {
        "serial_number": str(pass_data.get("pass_wallet_serial_number") or "").strip(),
        "status": str(pass_data.get("pass_status") or "active").strip(),
        "expires_at": str(pass_data.get("pass_expires_at") or "").strip(),
        "web_service_url": str(pass_data.get("pass_wallet_web_service_url") or "").strip(),
        "authentication_token": str(pass_data.get("pass_wallet_auth_token") or "").strip(),
    }


def _wallet_service_redirect_response(
    *,
    service_url: str,
    title: str,
    code: str,
    payload: str,
    template: str,
) -> Response:
    split = urlsplit(service_url)
    query_items = list(parse_qsl(split.query, keep_blank_values=True))
    query_items.extend(
        [
            ("title", title),
            ("code", code),
            ("payload", payload),
            ("template", template),
        ]
    )
    destination = urlunsplit(
        (
            split.scheme,
            split.netloc,
            split.path,
            urlencode(query_items),
            split.fragment,
        )
    )
    return RedirectResponse(url=destination, status_code=307)


def _issue_wallet_pass(
    *,
    title: str,
    code: str,
    payload: str,
    template: str,
    context: dict[str, str] | None = None,
) -> Response:
    context = context or {}
    service_url = (settings.wallet_pass_service_url or "").strip()
    if wallet_pass_service.configured_for_local_signing(template=template):
        try:
            pkpass = wallet_pass_service.build_pass(
                title=title,
                code=code,
                payload=payload,
                template=template,
                serial_number=context.get("serial_number") or None,
                status=context.get("status") or None,
                expires_at=context.get("expires_at") or None,
                web_service_url=context.get("web_service_url") or None,
                authentication_token=context.get("authentication_token") or None,
            )
        except WalletPassConfigurationError as exc:
            if service_url:
                return _wallet_service_redirect_response(
                    service_url=service_url,
                    title=title,
                    code=code,
                    payload=payload,
                    template=template,
                )
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except WalletPassSigningError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        filename = wallet_pass_service.filename_for_code(code, template=template)
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        }
        return Response(
            content=pkpass,
            media_type="application/vnd.apple.pkpass",
            headers=headers,
        )

    if template == "hq":
        raise HTTPException(
            status_code=503,
            detail=(
                "The HQ Apple Wallet pass is not configured for dedicated signing yet. "
                "Configure WALLET_HQ_* signing values first."
            ),
        )

    if not service_url:
        raise HTTPException(
            status_code=503,
            detail=(
                "PerkNation Apple Wallet passes are not enabled on this backend yet. "
                "Configure local pass-signing certificates or a signed .pkpass service first."
            ),
        )

    return _wallet_service_redirect_response(
        service_url=service_url,
        title=title,
        code=code,
        payload=payload,
        template=template,
    )


@router.get("/pass", include_in_schema=False)
def get_apple_wallet_pass(
    title: str = Query(..., min_length=1, max_length=120),
    code: str = Query(..., min_length=1, max_length=120),
    payload: str = Query(..., min_length=1, max_length=2048),
    template: str = Query("perknation", pattern="^(perknation|hq)$"),
    db: Session = Depends(get_db),
) -> Response:
    return _issue_wallet_pass(
        title=title,
        code=code,
        payload=payload,
        template=template,
        context=_wallet_pass_context(
            db=db,
            code=code,
            title=title,
            payload=payload,
            template=template,
        ),
    )


@router.get("/pass/hq", include_in_schema=False)
def get_hq_wallet_pass(
    title: str = Query(..., min_length=1, max_length=120),
    code: str = Query(..., min_length=1, max_length=120),
    payload: str = Query(..., min_length=1, max_length=2048),
) -> Response:
    return _issue_wallet_pass(
        title=title,
        code=code,
        payload=payload,
        template="hq",
    )


def _assert_pass_type(pass_type_identifier: str) -> None:
    configured = str(settings.wallet_pass_type_identifier or "").strip()
    if configured and pass_type_identifier != configured:
        raise HTTPException(status_code=404, detail="Pass type not found")


def _lookup_wallet_row(
    *,
    db: Session,
    pass_type_identifier: str,
    serial_number: str,
    authorization: str | None,
) -> tuple[Any, dict[str, Any], int | None, dict[str, Any]]:
    _assert_pass_type(pass_type_identifier)
    lookup = find_checkout_ticket_by_wallet_serial(db, serial_number)
    if lookup is None:
        raise HTTPException(status_code=404, detail="Pass not found")

    row, payload, ticket_index, ticket = lookup
    if not wallet_pass_authorized(payload, authorization, ticket=ticket):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return row, payload, ticket_index, ticket


@router.post("/v1/devices/{device_library_identifier}/registrations/{pass_type_identifier}/{serial_number}", include_in_schema=False)
async def register_pass_device(
    device_library_identifier: str,
    pass_type_identifier: str,
    serial_number: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Response:
    row, payload, ticket_index, ticket = _lookup_wallet_row(
        db=db,
        pass_type_identifier=pass_type_identifier,
        serial_number=serial_number,
        authorization=authorization,
    )
    body = await request.json()
    push_token = str((body or {}).get("pushToken") or "").strip()
    if not push_token:
        raise HTTPException(status_code=400, detail="pushToken is required")

    is_new = register_wallet_device(
        db,
        row,
        payload,
        device_library_identifier=device_library_identifier,
        push_token=push_token,
        ticket_index=ticket_index,
        ticket=ticket,
    )
    return Response(status_code=201 if is_new else 200)


@router.delete("/v1/devices/{device_library_identifier}/registrations/{pass_type_identifier}/{serial_number}", include_in_schema=False)
def unregister_pass_device(
    device_library_identifier: str,
    pass_type_identifier: str,
    serial_number: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Response:
    row, payload, ticket_index, ticket = _lookup_wallet_row(
        db=db,
        pass_type_identifier=pass_type_identifier,
        serial_number=serial_number,
        authorization=authorization,
    )
    unregister_wallet_device(
        db,
        row,
        payload,
        device_library_identifier=device_library_identifier,
        ticket_index=ticket_index,
        ticket=ticket,
    )
    return Response(status_code=200)


@router.get("/v1/devices/{device_library_identifier}/registrations/{pass_type_identifier}", include_in_schema=False)
def get_updated_pass_serials(
    device_library_identifier: str,
    pass_type_identifier: str,
    passesUpdatedSince: Optional[str] = Query(default=None),  # noqa: N803 - PassKit parameter name.
    db: Session = Depends(get_db),
) -> Response:
    _assert_pass_type(pass_type_identifier)
    body = list_wallet_pass_updates_for_device(
        db,
        device_library_identifier=device_library_identifier,
        passes_updated_since=passesUpdatedSince,
    )
    if not body["serialNumbers"]:
        return Response(status_code=204)
    return JSONResponse(body)


@router.get("/v1/passes/{pass_type_identifier}/{serial_number}", include_in_schema=False)
def get_updated_pass(
    pass_type_identifier: str,
    serial_number: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Response:
    row, payload, _, ticket = _lookup_wallet_row(
        db=db,
        pass_type_identifier=pass_type_identifier,
        serial_number=serial_number,
        authorization=authorization,
    )
    if str(payload.get("payment_status") or "").strip().lower() == "paid":
        payload = ensure_paid_order_pass(db, row, notify_customer=False)
        _, ticket, _ = checkout_ticket_from_payload(payload, str(ticket.get("pass_code") or serial_number))

    pass_data = ticket if isinstance(ticket, dict) else payload
    pass_code = str(pass_data.get("pass_code") or "").strip()
    pass_view_url = str(pass_data.get("pass_view_url") or "").strip()
    if not pass_code or not pass_view_url:
        raise HTTPException(status_code=404, detail="Pass payload is incomplete")

    response = _issue_wallet_pass(
        title="PerkNation Park Entry Pass",
        code=pass_code,
        payload=pass_view_url,
        template="perknation",
        context={
            "serial_number": str(pass_data.get("pass_wallet_serial_number") or serial_number).strip(),
            "status": str(pass_data.get("pass_status") or "active").strip(),
            "expires_at": str(pass_data.get("pass_expires_at") or "").strip(),
            "web_service_url": str(pass_data.get("pass_wallet_web_service_url") or "").strip(),
            "authentication_token": str(pass_data.get("pass_wallet_auth_token") or "").strip(),
        },
    )
    response.headers["Last-Modified"] = str(
        pass_data.get("pass_wallet_last_updated_at") or pass_data.get("pass_issued_at") or ""
    )
    return response


@router.post("/v1/log", include_in_schema=False)
async def wallet_device_log(request: Request) -> Response:
    try:
        body = await request.json()
        logger.info("Apple Wallet device log: %s", body)
    except Exception:
        logger.info("Apple Wallet device log received.")
    return Response(status_code=200)
