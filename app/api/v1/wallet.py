from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse, Response

from app.core.config import settings
from app.services.wallet_passes import (
    WalletPassConfigurationError,
    WalletPassSigningError,
    wallet_pass_service,
)


router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("/pass", include_in_schema=False)
def get_apple_wallet_pass(
    title: str = Query(..., min_length=1, max_length=120),
    code: str = Query(..., min_length=1, max_length=120),
    payload: str = Query(..., min_length=1, max_length=2048),
) -> Response:
    if wallet_pass_service.configured_for_local_signing():
        try:
            pkpass = wallet_pass_service.build_pass(title=title, code=code, payload=payload)
        except WalletPassConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except WalletPassSigningError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        filename = wallet_pass_service.filename_for_code(code)
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        }
        return Response(
            content=pkpass,
            media_type="application/vnd.apple.pkpass",
            headers=headers,
        )

    service_url = (settings.wallet_pass_service_url or "").strip()
    if not service_url:
        raise HTTPException(
            status_code=503,
            detail=(
                "PerkNation Apple Wallet passes are not enabled on this backend yet. "
                "Configure local pass-signing certificates or a signed .pkpass service first."
            ),
        )

    split = urlsplit(service_url)
    query_items = list(parse_qsl(split.query, keep_blank_values=True))
    query_items.extend(
        [
            ("title", title),
            ("code", code),
            ("payload", payload),
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
