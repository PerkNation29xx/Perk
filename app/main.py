from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.session import SessionLocal, engine
from app.services.la_restaurant_knowledge import seed_la_restaurant_knowledge
from app.services.seed import seed_if_empty

# Import models so SQLAlchemy metadata includes all tables.
from app.db import models as _models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_ready = False
    app.state.db_startup_error = None
    try:
        Base.metadata.create_all(bind=engine)
        run_migrations(engine)

        if settings.seed_default_data or settings.seed_restaurant_knowledge_data:
            with SessionLocal() as db:
                if settings.seed_default_data:
                    seed_if_empty(db)
                if settings.seed_restaurant_knowledge_data:
                    seed_la_restaurant_knowledge(db)
        app.state.db_ready = True
    except Exception as exc:  # noqa: BLE001
        # Keep web/API process healthy for platform health checks even if DB is
        # temporarily unreachable during boot. API handlers touching DB will
        # still return operational errors until connectivity is restored.
        app.state.db_startup_error = str(exc)
        logger.exception("Database init failed during startup; continuing in degraded mode")

    yield


app = FastAPI(title=settings.project_name, lifespan=lifespan)
app.include_router(api_router, prefix=settings.api_v1_prefix)

_BASE_DIR = Path(__file__).resolve().parent
_HOME_PORTAL_DIR = _BASE_DIR / "web" / "home_portal"
_HOME_STATIC_DIR = _HOME_PORTAL_DIR / "static"
_HOME_ASSETS_DIR = _HOME_PORTAL_DIR / "assets"
_HOME_PORTAL_WHITE_DIR = _BASE_DIR / "web" / "home_portal_white"
_HOME_WHITE_STATIC_DIR = _HOME_PORTAL_WHITE_DIR / "static"
_HOME_WHITE_ASSETS_DIR = _HOME_PORTAL_WHITE_DIR / "assets"
_ADMIN_PORTAL_DIR = _BASE_DIR / "web" / "admin_portal"
_ADMIN_STATIC_DIR = _ADMIN_PORTAL_DIR / "static"
_USER_PORTAL_DIR = _BASE_DIR / "web" / "user_portal"
_USER_STATIC_DIR = _USER_PORTAL_DIR / "static"
_MERCHANT_PORTAL_DIR = _BASE_DIR / "web" / "merchant_portal"
_MERCHANT_STATIC_DIR = _MERCHANT_PORTAL_DIR / "static"
_HOME_HTML_FILES = {
    "index.html",
    "login.html",
    "redeem.html",
    "invite.html",
    "reset-password.html",
    "create-account.html",
    "members.html",
    "hollywood-sports.html",
    "how-it-works.html",
    "merchants.html",
    "faq.html",
    "contact-us.html",
    "privacy-policy.html",
    "terms-of-use.html",
    "disclaimer.html",
    "merchant-terms.html",
    # Legacy pages kept for backward compatibility.
    "investors.html",
    "security.html",
    "contact.html",
    "privacy.html",
    "terms.html",
}

_LEGACY_HTML_TO_CANONICAL = {
    "index": "/",
    "login": "/login",
    "redeem": "/redeem",
    "invite": "/invite",
    "reset-password": "/reset-password",
    "create-account": "/create-account",
    "members": "/members",
    "hollywood-sports": "/hollywood-sports",
    "guests": "/members",
    "merchants": "/merchants",
    "how-it-works": "/how-it-works",
    "contact-us": "/contact-us",
    "faq": "/faq",
    "privacy-policy": "/privacy-policy",
    "terms-of-use": "/terms-of-use",
    "disclaimer": "/disclaimer",
    "merchant-terms": "/merchant-terms",
}
_WHITE_LEGACY_HTML_TO_CANONICAL = {
    key: (f"/white{route}" if route != "/" else "/white/")
    for key, route in _LEGACY_HTML_TO_CANONICAL.items()
}
_LEGACY_STATIC_HTML_FILES = {"investors.html", "security.html", "contact.html", "privacy.html", "terms.html"}

# Admin web portal (served from the same process for local testing).
if _ADMIN_STATIC_DIR.exists():
    app.mount("/admin/static", StaticFiles(directory=str(_ADMIN_STATIC_DIR)), name="admin-static")
if _USER_STATIC_DIR.exists():
    app.mount("/user/static", StaticFiles(directory=str(_USER_STATIC_DIR)), name="user-static")
if _MERCHANT_STATIC_DIR.exists():
    app.mount("/merchant/static", StaticFiles(directory=str(_MERCHANT_STATIC_DIR)), name="merchant-static")
if _HOME_STATIC_DIR.exists():
    app.mount("/site/static", StaticFiles(directory=str(_HOME_STATIC_DIR)), name="home-static")
if _HOME_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(_HOME_ASSETS_DIR)), name="home-assets")
if _HOME_WHITE_STATIC_DIR.exists():
    app.mount("/white/static", StaticFiles(directory=str(_HOME_WHITE_STATIC_DIR)), name="home-white-static")
if _HOME_WHITE_ASSETS_DIR.exists():
    app.mount("/white/assets", StaticFiles(directory=str(_HOME_WHITE_ASSETS_DIR)), name="home-white-assets")


def _read_html_or_missing(path: Path, name: str) -> str:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return path.read_text(encoding="utf-8")


def _read_text_or_missing(path: Path, fallback: str = "") -> str:
    if not path.exists():
        return fallback
    return path.read_text(encoding="utf-8")


@app.get("/admin", response_class=HTMLResponse)
def admin_portal() -> str:
    return _read_html_or_missing(_ADMIN_PORTAL_DIR / "index.html", "Admin portal")


@app.get("/admin/ticket-scanner", response_class=HTMLResponse)
def admin_ticket_scanner_portal() -> str:
    return _read_html_or_missing(_ADMIN_PORTAL_DIR / "index.html", "Admin portal")


@app.get("/user", response_class=HTMLResponse)
def user_portal() -> str:
    return _read_html_or_missing(_USER_PORTAL_DIR / "index.html", "User portal")


@app.get("/merchant", response_class=HTMLResponse)
def merchant_portal() -> str:
    return _read_html_or_missing(_MERCHANT_PORTAL_DIR / "index.html", "Merchant portal")


@app.get("/", response_class=HTMLResponse)
def home_portal() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "index.html", "Home portal")


@app.get("/home", response_class=HTMLResponse)
def home_portal_alias() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=308)


@app.get("/login", response_class=HTMLResponse)
def home_portal_login() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "login.html", "Login page")


@app.get("/redeem", response_class=HTMLResponse)
def home_portal_redeem() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "redeem.html", "Redeem page")


@app.get("/invite", response_class=HTMLResponse)
def home_portal_invite() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "invite.html", "Invite page")


@app.get("/reset-password", response_class=HTMLResponse)
def home_portal_reset_password() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "reset-password.html", "Reset-password page")


@app.get("/create-account", response_class=HTMLResponse)
def home_portal_create_account() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "create-account.html", "Create-account page")


@app.get("/members", response_class=HTMLResponse)
def home_portal_members() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "members.html", "Members page")


@app.get("/hollywood-sports", response_class=HTMLResponse)
def home_portal_hollywood_sports() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "hollywood-sports.html", "Hollywood Sports landing page")


@app.get("/guests", include_in_schema=False)
def home_portal_guests_redirect() -> RedirectResponse:
    return RedirectResponse(url="/members", status_code=308)


@app.get("/merchants", response_class=HTMLResponse)
def home_portal_merchants() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "merchants.html", "Merchants page")


@app.get("/how-it-works", response_class=HTMLResponse)
def home_portal_how_it_works() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "how-it-works.html", "How-it-works page")


@app.get("/contact-us", response_class=HTMLResponse)
def home_portal_contact_us() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "contact-us.html", "Contact-us page")


@app.get("/faq", response_class=HTMLResponse)
def home_portal_faq() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "faq.html", "FAQ page")


@app.get("/privacy-policy", response_class=HTMLResponse)
def home_portal_privacy_policy() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "privacy-policy.html", "Privacy-policy page")


@app.get("/terms-of-use", response_class=HTMLResponse)
def home_portal_terms_of_use() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "terms-of-use.html", "Terms-of-use page")


@app.get("/disclaimer", response_class=HTMLResponse)
def home_portal_disclaimer() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "disclaimer.html", "Disclaimer page")


@app.get("/merchant-terms", response_class=HTMLResponse)
def home_portal_merchant_terms() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "merchant-terms.html", "Merchant terms page")


@app.get("/white", include_in_schema=False)
def home_portal_white_redirect() -> RedirectResponse:
    return RedirectResponse(url="/white/", status_code=308)


@app.get("/white/", response_class=HTMLResponse)
def home_portal_white() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "index.html", "Home portal (white)")


@app.get("/white/login", response_class=HTMLResponse)
def home_portal_white_login() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "login.html", "Login page (white)")


@app.get("/white/redeem", response_class=HTMLResponse)
def home_portal_white_redeem() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "redeem.html", "Redeem page (white)")


@app.get("/white/invite", response_class=HTMLResponse)
def home_portal_white_invite() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "invite.html", "Invite page (white)")


@app.get("/white/reset-password", response_class=HTMLResponse)
def home_portal_white_reset_password() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "reset-password.html", "Reset-password page (white)")


@app.get("/white/create-account", response_class=HTMLResponse)
def home_portal_white_create_account() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "create-account.html", "Create-account page (white)")


@app.get("/white/members", response_class=HTMLResponse)
def home_portal_white_members() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "members.html", "Members page (white)")


@app.get("/white/hollywood-sports", response_class=HTMLResponse)
def home_portal_white_hollywood_sports() -> str:
    return _read_html_or_missing(
        _HOME_PORTAL_WHITE_DIR / "hollywood-sports.html",
        "Hollywood Sports landing page (white)",
    )


@app.get("/white/guests", include_in_schema=False)
def home_portal_white_guests_redirect() -> RedirectResponse:
    return RedirectResponse(url="/white/members", status_code=308)


@app.get("/white/merchants", response_class=HTMLResponse)
def home_portal_white_merchants() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "merchants.html", "Merchants page (white)")


@app.get("/white/how-it-works", response_class=HTMLResponse)
def home_portal_white_how_it_works() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "how-it-works.html", "How-it-works page (white)")


@app.get("/white/contact-us", response_class=HTMLResponse)
def home_portal_white_contact_us() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "contact-us.html", "Contact-us page (white)")


@app.get("/white/faq", response_class=HTMLResponse)
def home_portal_white_faq() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "faq.html", "FAQ page (white)")


@app.get("/white/privacy-policy", response_class=HTMLResponse)
def home_portal_white_privacy_policy() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "privacy-policy.html", "Privacy-policy page (white)")


@app.get("/white/terms-of-use", response_class=HTMLResponse)
def home_portal_white_terms_of_use() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "terms-of-use.html", "Terms-of-use page (white)")


@app.get("/white/disclaimer", response_class=HTMLResponse)
def home_portal_white_disclaimer() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "disclaimer.html", "Disclaimer page (white)")


@app.get("/white/merchant-terms", response_class=HTMLResponse)
def home_portal_white_merchant_terms() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "merchant-terms.html", "Merchant terms page (white)")


@app.get("/white/{page_name}.html", response_class=HTMLResponse)
def home_portal_white_page(page_name: str) -> Response:
    canonical = _WHITE_LEGACY_HTML_TO_CANONICAL.get(page_name.strip().lower())
    if canonical:
        return RedirectResponse(url=canonical, status_code=308)

    filename = f"{page_name}.html"
    if filename not in _HOME_HTML_FILES:
        raise HTTPException(status_code=404, detail="Page not found")
    if filename not in _LEGACY_STATIC_HTML_FILES:
        raise HTTPException(status_code=404, detail="Legacy HTML route not available")
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / filename, "Home portal page (white)")


@app.get("/{page_name}.html", response_class=HTMLResponse)
def home_portal_page(page_name: str) -> Response:
    canonical = _LEGACY_HTML_TO_CANONICAL.get(page_name.strip().lower())
    if canonical:
        return RedirectResponse(url=canonical, status_code=308)

    filename = f"{page_name}.html"
    if filename not in _HOME_HTML_FILES:
        raise HTTPException(status_code=404, detail="Page not found")
    if filename not in _LEGACY_STATIC_HTML_FILES:
        raise HTTPException(status_code=404, detail="Legacy HTML route not available")
    return _read_html_or_missing(_HOME_PORTAL_DIR / filename, "Home portal page")


@app.get("/robots.txt", response_class=PlainTextResponse)
def home_portal_robots() -> str:
    return _read_text_or_missing(_HOME_PORTAL_DIR / "robots.txt", fallback="User-agent: *\nAllow: /\n")


@app.get("/sitemap.xml")
def home_portal_sitemap() -> Response:
    content = _read_text_or_missing(_HOME_PORTAL_DIR / "sitemap.xml", fallback="<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"/>")
    return Response(content=content, media_type="application/xml")


@app.get("/white/robots.txt", response_class=PlainTextResponse)
def home_portal_white_robots() -> str:
    return _read_text_or_missing(_HOME_PORTAL_WHITE_DIR / "robots.txt", fallback="User-agent: *\nAllow: /\n")


@app.get("/white/sitemap.xml")
def home_portal_white_sitemap() -> Response:
    content = _read_text_or_missing(_HOME_PORTAL_WHITE_DIR / "sitemap.xml", fallback="<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"/>")
    return Response(content=content, media_type="application/xml")


@app.get("/web/config")
def web_portal_config() -> dict[str, str]:
    """
    Client-side config for hosted local web portals.

    Note: SUPABASE_ANON_KEY is safe to expose to browsers (it's a publishable key),
    but you should still only serve these portals on trusted origins.
    """

    supabase_url = settings.effective_supabase_url
    supabase_anon_key = settings.effective_supabase_anon_key
    if not supabase_url or not supabase_anon_key:
        return {
            "error": "Supabase is not configured on the backend. Set SUPABASE_URL and SUPABASE_ANON_KEY.",
        }

    return {
        "project_name": settings.project_name,
        "api_v1_prefix": settings.api_v1_prefix,
        "supabase_url": supabase_url,
        "supabase_anon_key": supabase_anon_key,
        "auth_email_redirect_url": settings.supabase_email_redirect_url,
        "auth_password_reset_redirect_url": settings.supabase_password_reset_redirect_url,
    }


@app.get("/admin/config")
def admin_portal_config() -> dict[str, str]:
    # Backward-compatible route for existing admin UI.
    return web_portal_config()


@app.get("/api")
def root_api() -> dict[str, str]:
    return {
        "service": settings.project_name,
        "docs": "/docs",
        "home": "/",
        "user_portal": "/user",
        "merchant_portal": "/merchant",
        "admin_portal": "/admin",
    }
