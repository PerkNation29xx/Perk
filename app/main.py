from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.session import SessionLocal, engine
from app.services.seed import seed_if_empty

# Import models so SQLAlchemy metadata includes all tables.
from app.db import models as _models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    if settings.seed_default_data:
        with SessionLocal() as db:
            seed_if_empty(db)

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
    "create-account.html",
    "how-it-works.html",
    "merchants.html",
    "guests.html",
    "faq.html",
    "contact-us.html",
    "privacy-policy.html",
    "terms-of-use.html",
    "disclaimer.html",
    # Legacy pages kept for backward compatibility.
    "investors.html",
    "security.html",
    "contact.html",
    "privacy.html",
    "terms.html",
}

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
        return f"<h1>{name} not found</h1>"
    return path.read_text(encoding="utf-8")


def _read_text_or_missing(path: Path, fallback: str = "") -> str:
    if not path.exists():
        return fallback
    return path.read_text(encoding="utf-8")


@app.get("/admin", response_class=HTMLResponse)
def admin_portal() -> str:
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
def home_portal_alias() -> str:
    return home_portal()


@app.get("/login", response_class=HTMLResponse)
def home_portal_login() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "login.html", "Login page")


@app.get("/create-account", response_class=HTMLResponse)
def home_portal_create_account() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "create-account.html", "Create-account page")


@app.get("/white", include_in_schema=False)
def home_portal_white_redirect() -> RedirectResponse:
    return RedirectResponse(url="/white/", status_code=307)


@app.get("/white/", response_class=HTMLResponse)
def home_portal_white() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "index.html", "Home portal (white)")


@app.get("/white/login", response_class=HTMLResponse)
def home_portal_white_login() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "login.html", "Login page (white)")


@app.get("/white/create-account", response_class=HTMLResponse)
def home_portal_white_create_account() -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "create-account.html", "Create-account page (white)")


@app.get("/white/{page_name}.html", response_class=HTMLResponse)
def home_portal_white_page(page_name: str) -> str:
    filename = f"{page_name}.html"
    if filename not in _HOME_HTML_FILES:
        raise HTTPException(status_code=404, detail="Page not found")
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / filename, "Home portal page (white)")


@app.get("/{page_name}.html", response_class=HTMLResponse)
def home_portal_page(page_name: str) -> str:
    filename = f"{page_name}.html"
    if filename not in _HOME_HTML_FILES:
        raise HTTPException(status_code=404, detail="Page not found")
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

    if not settings.supabase_url or not settings.supabase_anon_key:
        return {
            "error": "Supabase is not configured on the backend. Set SUPABASE_URL and SUPABASE_ANON_KEY.",
        }

    return {
        "project_name": settings.project_name,
        "api_v1_prefix": settings.api_v1_prefix,
        "supabase_url": settings.supabase_url,
        "supabase_anon_key": settings.supabase_anon_key,
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
