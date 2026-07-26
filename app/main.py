from contextlib import asynccontextmanager
import html
import json
import logging
import re
from urllib.parse import quote, quote_plus, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import Optional

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.session import SessionLocal, engine
from app.services.business_directory import (
    directory_facets,
    directory_sitemap_entries,
    get_business_directory_entry,
    normalize_spaces,
    search_business_directory,
)
from app.services.la_restaurant_knowledge import seed_la_restaurant_knowledge
from app.services.seed import seed_if_empty

# Import models so SQLAlchemy metadata includes all tables.
from app.db import models as _models  # noqa: F401

logger = logging.getLogger(__name__)

_GOOGLE_ANALYTICS_ID = "G-VYL0SBGMWL"
_INDEXNOW_KEY = "7a937e1db6b8272beca3c7860157d6112a7301b5832fd8a01590e17803adb3f3"
_INDEXNOW_KEY_PATH = f"/{_INDEXNOW_KEY}.txt"
_PUBLIC_BUILD_ID = "20260726-nfl-league-guide"
_GOOGLE_ANALYTICS_SNIPPET = f"""<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={_GOOGLE_ANALYTICS_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());

  gtag('config', '{_GOOGLE_ANALYTICS_ID}');
</script>"""
_DEFAULT_SOCIAL_IMAGE_PATH = "/assets/photos/hero-dining-room.jpg"


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


def _inject_google_analytics(html: str) -> str:
    if _GOOGLE_ANALYTICS_ID in html:
        return html

    lower_html = html.lower()
    head_close_index = lower_html.find("</head>")
    if head_close_index < 0:
        return html

    return f"{html[:head_close_index]}\n{_GOOGLE_ANALYTICS_SNIPPET}\n{html[head_close_index:]}"


def _regex_group(pattern: str, text: str) -> str:
    match = re.search(pattern, text or "", flags=re.IGNORECASE | re.DOTALL)
    return html.unescape(match.group(1).strip()) if match else ""


def _canonical_href(href: str) -> str:
    raw = html.unescape(str(href or "").strip())
    if not raw:
        return _public_url("/")
    if raw.startswith(("http://", "https://")):
        return settings._canonical_public_url(raw)
    return _public_url(raw)


def _inject_social_meta(html: str) -> str:
    if 'property="og:title"' in html or "property='og:title'" in html:
        return html

    lower_html = html.lower()
    head_close_index = lower_html.find("</head>")
    if head_close_index < 0:
        return html

    title = _regex_group(r"<title[^>]*>(.*?)</title>", html) or "Perk Nation"
    description = _regex_group(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        html,
    )
    if not description:
        description = "Perk Nation connects local offers, business discovery, and community rewards."
    canonical = _regex_group(r'<link\s+rel=["\']canonical["\']\s+href=["\'](.*?)["\']', html)
    canonical_url = _canonical_href(canonical)
    image_url = _public_url(_DEFAULT_SOCIAL_IMAGE_PATH)
    snippet = f"""
<meta property="og:type" content="website" />
<meta property="og:site_name" content="Perk Nation" />
<meta property="og:title" content="{_escape(title)}" />
<meta property="og:description" content="{_escape(description)}" />
<meta property="og:url" content="{_escape(canonical_url)}" />
<meta property="og:image" content="{_escape(image_url)}" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{_escape(title)}" />
<meta name="twitter:description" content="{_escape(description)}" />
<meta name="twitter:image" content="{_escape(image_url)}" />"""
    return f"{html[:head_close_index]}\n{snippet}\n{html[head_close_index:]}"


def _is_public_html_path(path: str) -> bool:
    normalized = str(path or "/").split("?", 1)[0]
    excluded_roots = ("/admin", "/user", "/merchant", "/v1", "/docs", "/redoc")
    return not any(normalized == root or normalized.startswith(f"{root}/") for root in excluded_roots)


def _public_shell_header() -> str:
    return """<header class="header">
  <div class="container">
    <div class="nav">
      <div class="brandStack">
        <a class="brand" href="/" aria-label="Perk Nation home">
          <span class="brandMark" aria-hidden="true"><img src="/assets/mark.svg" alt="" width="24" height="24" /></span>
          <span>Perk Nation</span>
        </a>
        <button class="brandMenuBtn" data-menu-btn aria-expanded="false" aria-controls="public-category-menu">
          <span aria-hidden="true">☰</span>
          <span>Explore categories</span>
        </button>
      </div>
      <nav class="navlinks" aria-label="Primary navigation">
        <a href="/events">Events</a>
        <a href="/directory">Directory</a>
        <a href="/members">Members</a>
        <a href="/merchants">Merchants</a>
        <a href="/how-it-works">How it Works</a>
        <a href="/contact-us">Contact Us</a>
        <a href="/faq">FAQ</a>
      </nav>
      <div class="navcta"><a class="btn ghost" href="/login">Login</a></div>
    </div>
    <div class="mobileMenu" data-mobile-menu id="public-category-menu">
      <div class="mobileMenuGrid">
        <div class="mobileMenuGroup">
          <div class="mobileMenuTitle">Lifestyle</div>
          <a href="/events">Events</a>
          <a href="/events#concerts">Concerts</a>
          <a href="/events#sports">Sports</a>
          <a href="/directory?q=community">Community</a>
        </div>
        <div class="mobileMenuGroup">
          <div class="mobileMenuTitle">Food &amp; style</div>
          <a href="/articles/dine-la-pasadena-2026">Food</a>
          <a href="/#pasadena-reviews">Dining</a>
          <a href="/articles/la-fashion-events-2026">Fashion</a>
          <a href="/#crystal-jewelry">Shopping</a>
        </div>
        <div class="mobileMenuGroup">
          <div class="mobileMenuTitle">Wellness &amp; discovery</div>
          <a href="/#wellness-beauty">Wellness &amp; Beauty</a>
          <a href="/directory?q=travel">Travel</a>
          <a href="/#bond-collective">Workspace</a>
          <a href="/directory">Directory</a>
        </div>
        <div class="mobileMenuGroup">
          <div class="mobileMenuTitle">Perk Nation</div>
          <a href="/members">Members</a>
          <a href="/merchants">Merchants</a>
          <a href="/how-it-works">How it Works</a>
          <a href="/contact-us">Contact Us</a>
          <a href="/faq">FAQ</a>
          <a href="/login">Login</a>
        </div>
      </div>
    </div>
  </div>
</header>"""


def _public_ai_rail() -> str:
    return """<section class="aiDiscoverySection aiRail" id="local-ai-assistant" data-ai-rail aria-label="Perk Nation AI local guide">
  <div class="aiRailShell">
    <button class="aiRailTab" type="button" data-ai-rail-toggle aria-expanded="false" aria-controls="public-ai-rail-panel">
      <span class="aiRailSpark" aria-hidden="true">✦</span><span>Ask Perk Nation AI</span>
    </button>
    <div class="card pad aiDiscoveryCard" id="public-ai-rail-panel">
      <button class="aiRailClose" type="button" data-ai-rail-close aria-label="Hide Perk Nation AI">×</button>
      <div class="aiDiscoveryHeader">
        <div>
          <div class="badge">AI Local Guide</div>
          <h2 class="h2">Ask Perk Nation.</h2>
          <p class="muted">Ask about NFL teams, game times, events, current promotions, or nearby businesses.</p>
        </div>
        <div class="small aiDiscoveryMeta" data-home-ai-status>Ready for football, events, and local plans.</div>
      </div>
      <div class="aiDiscoveryMessages" data-home-ai-messages>
        <div class="aiBubble assistant">Ask me when any NFL team plays, who they face, or what time the game starts. I can also help with PerkNation events and local discovery.</div>
      </div>
      <form class="aiDiscoveryComposer" data-home-ai-form>
        <textarea data-home-ai-input placeholder="Example: What time do the Bills play in Week 1?" aria-label="Ask Perk Nation AI about football teams, events, and local recommendations" required></textarea>
        <div class="aiDiscoveryActions">
          <button class="btn primary" type="submit" data-home-ai-send>Ask AI</button>
          <button class="btn" type="button" data-home-ai-clear>Clear</button>
        </div>
      </form>
    </div>
  </div>
</section>"""


_PUBLIC_HEADER_RE = re.compile(
    r'<header\b[^>]*class=["\'][^"\']*\bheader\b[^"\']*["\'][^>]*>.*?</header>',
    flags=re.IGNORECASE | re.DOTALL,
)
_PUBLIC_ASSET_RE = re.compile(
    r'(?P<attribute>\b(?:href|src)\s*=\s*)(?P<quote>["\'])'
    r'(?P<path>(?:(?:\.\./)*|/)?(?:white/)?assets/(?P<asset>[^"\'>?]+\.(?:css|js)))'
    r'(?:\?[^"\']*)?(?P=quote)',
    flags=re.IGNORECASE,
)


def _inject_public_shell(document_html: str, *, path: str) -> str:
    if not _is_public_html_path(path):
        return document_html

    header = _public_shell_header()
    if _PUBLIC_HEADER_RE.search(document_html):
        document_html = _PUBLIC_HEADER_RE.sub(header, document_html, count=1)
    else:
        document_html = re.sub(
            r"(<body\b[^>]*>)",
            lambda match: f"{match.group(1)}\n{header}",
            document_html,
            count=1,
            flags=re.IGNORECASE,
        )

    def version_asset(match: re.Match[str]) -> str:
        asset = match.group("asset")
        return (
            f'{match.group("attribute")}{match.group("quote")}'
            f"/assets/{asset}?v={_PUBLIC_BUILD_ID}{match.group('quote')}"
        )

    document_html = _PUBLIC_ASSET_RE.sub(version_asset, document_html)
    if not re.search(
        r'<script\b[^>]*src=["\']/assets/app\.js\?v='
        + re.escape(_PUBLIC_BUILD_ID)
        + r'["\']',
        document_html,
        flags=re.IGNORECASE,
    ):
        app_script = f'<script src="/assets/app.js?v={_PUBLIC_BUILD_ID}" defer></script>'
        if re.search(r"</body>", document_html, flags=re.IGNORECASE):
            document_html = re.sub(
                r"</body>",
                f"{app_script}\n</body>",
                document_html,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            document_html = f"{document_html}\n{app_script}"
    if "data-home-ai-form" not in document_html:
        assistant = _public_ai_rail()
        if re.search(r"</body>", document_html, flags=re.IGNORECASE):
            document_html = re.sub(
                r"</body>",
                f"{assistant}\n</body>",
                document_html,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            document_html = f"{document_html}\n{assistant}"
    return document_html


@app.middleware("http")
async def google_analytics_html_middleware(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    charset = "utf-8"
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1] or "utf-8"
            break

    try:
        html = body.decode(charset)
    except Exception:
        return Response(content=body, status_code=response.status_code, headers=dict(response.headers))

    headers = dict(response.headers)
    headers.pop("content-length", None)
    html = _inject_public_shell(html, path=request.url.path)
    html = _inject_social_meta(html)
    html = _inject_google_analytics(html)
    return Response(
        content=html,
        status_code=response.status_code,
        headers=headers,
        media_type=None,
    )


@app.get("/web/build", include_in_schema=False)
def public_web_build() -> dict[str, str]:
    return {"label": f"Build {_PUBLIC_BUILD_ID}", "id": _PUBLIC_BUILD_ID}


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
    "jewelry-product.html",
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
_ARTICLE_HTML_FILES = {
    "dine-la-pasadena-2026": "dine-la-pasadena-2026.html",
    "la-fashion-events-2026": "la-fashion-events-2026.html",
    "vvs-cosmetics-victor-kuzmanovsky-wellness-beauty": "vvs-cosmetics-victor-kuzmanovsky-wellness-beauty.html",
    "southern-california-august-events-2026": "southern-california-august-events-2026.html",
}
_BASE_EVENT_SLUGS = {
    "kcon-la-2026",
    "mount-westmore-san-jose",
    "j-cole-los-angeles",
    "carin-leon-san-diego",
    "ufc-sacramento-2026",
    "ringling-san-diego-2026",
    "chargers-home-opener-2026",
    "49ers-home-opener-2026",
    "rams-home-opener-2026",
}
_NFL_SCHEDULES_FILE = _HOME_ASSETS_DIR / "nfl-2026-schedules.json"
try:
    _NFL_TEAMS_BY_SLUG = {
        str(team["slug"]): team
        for team in json.loads(_NFL_SCHEDULES_FILE.read_text(encoding="utf-8")).get("teams", [])
        if team.get("slug")
    }
except (OSError, ValueError, TypeError):
    _NFL_TEAMS_BY_SLUG = {}
_NFL_EVENT_SLUGS = set(_NFL_TEAMS_BY_SLUG)
_EVENT_SLUGS = _BASE_EVENT_SLUGS | _NFL_EVENT_SLUGS
_DINE_LA_CITY_GUIDES_FILE = _HOME_PORTAL_DIR / "assets" / "articles" / "dine-la-city-guides-2026.json"

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
if _HOME_STATIC_DIR.exists():
    app.mount("/white/static", StaticFiles(directory=str(_HOME_STATIC_DIR)), name="home-white-static")
if _HOME_ASSETS_DIR.exists():
    app.mount("/white/assets", StaticFiles(directory=str(_HOME_ASSETS_DIR)), name="home-white-assets")


def _read_html_or_missing(path: Path, name: str, *, theme: str = "dark") -> str:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{name} not found")
    content = path.read_text(encoding="utf-8")
    normalized_theme = theme if theme in {"light", "dark"} else "dark"
    return content.replace(
        '<html lang="en">',
        f'<html lang="en" data-theme="{normalized_theme}">',
        1,
    )


def _render_event_article(event_slug: str, *, theme: str = "dark") -> str:
    document_html = _read_html_or_missing(
        _HOME_PORTAL_DIR / "event-detail.html",
        "Event article",
        theme=theme,
    )
    team = _NFL_TEAMS_BY_SLUG.get(event_slug)
    if not team:
        return document_html

    opener = team.get("opener") if isinstance(team.get("opener"), dict) else {}
    name = str(team.get("name") or "NFL team")
    opponent = str(opener.get("opponent") or "its Week 1 opponent")
    title = f"{name} 2026 Season Opener and Full Schedule | Perk Nation"
    description = (
        f"{name} opens the 2026 season against {opponent}. See all 18 weeks, "
        "Pacific kickoff times, networks, venues, the bye, and the official NFL schedule."
    )
    canonical = f"/events/{event_slug}"
    document_html = re.sub(
        r"<title>.*?</title>",
        f"<title>{_escape(title)}</title>",
        document_html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    document_html = re.sub(
        r'<meta\s+name=["\']description["\']\s+content=["\'].*?["\']\s*/?>',
        f'<meta name="description" content="{_escape(description)}" />',
        document_html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    document_html = re.sub(
        r'<link\s+rel=["\']canonical["\']\s+href=["\'].*?["\']\s*/?>',
        f'<link rel="canonical" href="{_escape(canonical)}" />',
        document_html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    noscript = (
        "<noscript><article class=\"eventNotFound\">"
        f"<span class=\"badge\">2026 NFL schedule</span><h1 class=\"h1\">{_escape(name)} season opener and full schedule</h1>"
        f"<p>{_escape(description)}</p><a class=\"btn primary\" href=\"{_escape(team.get('officialUrl'))}\">Official NFL schedule</a>"
        "</article></noscript>"
    )
    return document_html.replace(
        '<div class="eventLoading">Loading event…</div>',
        f'<div class="eventLoading">Loading event…</div>{noscript}',
        1,
    )


def _read_text_or_missing(path: Path, fallback: str = "") -> str:
    if not path.exists():
        return fallback
    return path.read_text(encoding="utf-8")


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _public_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return settings._join_public_url(settings.public_web_base_url, normalized)


def _load_dine_la_city_guides() -> dict:
    if not _DINE_LA_CITY_GUIDES_FILE.exists():
        return {"cities": []}
    try:
        return json.loads(_DINE_LA_CITY_GUIDES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.exception("Dine LA city guide data is not valid JSON")
        return {"cities": []}


def _find_dine_la_city_guide(article_slug: str) -> Optional[tuple[dict, dict]]:
    normalized = article_slug.strip().lower()
    data = _load_dine_la_city_guides()
    for city in data.get("cities", []):
        if city.get("article_slug") == normalized:
            return data, city
    return None


def _dine_la_restaurant_rank(item: dict) -> tuple[int, str]:
    name = str(item.get("name") or "")
    price = str(item.get("price_range") or "")
    cuisine = ", ".join(item.get("cuisine") or [])
    score = 0
    if "Lunch" in price and "Dinner" in price:
        score += 18
    elif "Dinner" in price:
        score += 10
    if "$25" in price or "$35" in price:
        score += 12
    if "$65 & Above" in price:
        score += 8
    if any(term in cuisine for term in ("Sushi", "Seafood", "Steakhouse", "French", "Japanese", "Italian", "Mediterranean")):
        score += 8
    if any(term in name for term in ("Steakhouse", "Sushi", "Prime", "Grill", "Coastal", "Cheesery")):
        score += 5
    return (-score, name.lower())


def _dine_la_review_note(item: dict) -> str:
    name = str(item.get("name") or "This restaurant")
    price = str(item.get("price_range") or "")
    cuisine = ", ".join(item.get("cuisine") or []) or "dining"
    if "Lunch" in price and "Dinner" in price:
        meal_note = "The lunch-and-dinner availability gives it more flexibility than dinner-only picks."
    elif "Lunch" in price:
        meal_note = "This is strongest as a daytime reservation or lower-pressure first stop."
    else:
        meal_note = "Treat this as a dinner-first reservation and book ahead for peak nights."
    if "$65 & Above" in price:
        tier_note = "The higher menu tier makes it better for celebrations, date nights, and client dinners."
    elif "$25" in price or "$35" in price:
        tier_note = "The accessible menu tier makes it useful for value-focused restaurant-week planning."
    elif "$45" in price or "$55" in price:
        tier_note = "The mid-tier pricing works well when you want a polished meal without jumping straight to a splurge."
    else:
        tier_note = "Check the menu before booking so the final price matches the occasion."
    return f"{name} stands out for {cuisine}. {meal_note} {tier_note}"


def _render_ranked_dine_la_items(restaurants: list[dict], source_url: str, limit: int = 8) -> str:
    ranked = sorted(restaurants, key=_dine_la_restaurant_rank)[:limit]
    return "\n".join(
        (
            "          <li>"
            f"<strong>#{index} <a href=\"{_escape(item.get('url') or source_url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{_escape(item.get('name'))}</a></strong>"
            f"<span>{_escape(_dine_la_review_note(item))}</span>"
            f"<small>{_escape(', '.join(item.get('cuisine') or []) or 'Dining')} · {_escape(item.get('price_range') or 'Check menu')} · {_escape(item.get('street') or '')}</small>"
            "</li>"
        )
        for index, item in enumerate(ranked, start=1)
    )


def _render_dine_la_city_article(article_slug: str, *, white: bool = False) -> Optional[str]:
    found = _find_dine_la_city_guide(article_slug)
    if not found:
        return None
    data, city = found
    city_name = city.get("city", "")
    restaurants = city.get("restaurants", [])
    restaurant_count = int(city.get("restaurant_count") or len(restaurants))
    route = city.get("route") or f"/articles/{article_slug}"
    canonical_url = _public_url(route)
    share_route = city.get("white_route") if white else route
    share_url = _public_url(share_route or route)
    directory_route = city.get("directory_route") or f"/directory?city={quote_plus(city_name)}"
    if white and directory_route.startswith("/"):
        directory_route = f"/white{directory_route}"
    source_url = data.get("source") or "https://www.discoverlosangeles.com/dinela"
    cuisines = ", ".join(city.get("top_cuisines", [])[:5]) or "local dining"
    price_ranges = city.get("price_ranges", [])[:4]
    price_summary = "; ".join(price_ranges) if price_ranges else "check current Dine LA menus"
    directory_count = city.get("perk_directory_count")
    directory_note = (
        f"Perk Nation currently has {int(directory_count):,} directory listings for {city_name}, so this guide can connect restaurant-week searches to deeper local discovery."
        if isinstance(directory_count, int)
        else f"{city_name} has enough Dine LA restaurant-week context to support a focused local guide; use the Perk Nation directory search to connect the dining plan with nearby categories."
    )
    ranked_items = _render_ranked_dine_la_items(restaurants, source_url, limit=10)
    restaurant_items = "\n".join(
        (
          "          <li>"
            f"<strong><a href=\"{_escape(item.get('url') or source_url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{_escape(item.get('name'))}</a></strong>"
            f" · {_escape(', '.join(item.get('cuisine') or []) or 'Dining')}"
            f" · {_escape(item.get('price_range') or 'Check menu')}"
            f" · {_escape(item.get('street') or city_name)}"
            "</li>"
        )
        for item in restaurants
    )
    all_cities = [other for other in data.get("cities", []) if other.get("article_slug") != article_slug]
    related_items = "\n".join(
        f"          <li><a href=\"{_escape(other.get('white_route') if white else other.get('route'))}\">{_escape(other.get('city'))} Dine LA guide</a> · {int(other.get('restaurant_count') or 0)} listings</li>"
        for other in all_cities[:10]
    )
    return f"""<!doctype html>
<html lang="en" data-theme="{'light' if white else 'dark'}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="Dine LA { _escape(city_name) } guide with ranked restaurant picks, review notes, price tiers, cuisines, and Perk Nation local discovery links." />
  <meta name="theme-color" content="#0d0d0d" />
  <title>Dine LA { _escape(city_name) } guide: {restaurant_count} restaurants | Perk Nation</title>
  <link rel="canonical" href="{_escape(canonical_url)}" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Rethink+Sans:wght@300;400;500;600;700;800;900&amp;display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/assets/styles.css?v=20260725-dine-la-cities" />
  <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "Article",
      "headline": "Dine LA { _escape(city_name) } guide: {restaurant_count} restaurants",
      "description": "Dine LA 2026 restaurant guide for { _escape(city_name) }, with ranked picks and practical review notes for local planning.",
      "image": "https://perknation.app/assets/articles/dine-la-pasadena-2026.jpg",
      "author": {{"@type": "Organization", "name": "Perk Nation"}},
      "publisher": {{"@type": "Organization", "name": "Perk Nation"}},
      "datePublished": "2026-07-25",
      "dateModified": "{_escape(data.get('generated_on') or '2026-07-25')}",
      "mainEntityOfPage": "{_escape(canonical_url)}"
    }}
  </script>
</head>
<body>
<header class="header">
  <div class="container">
    <div class="nav">
      <a class="brand" href="/" aria-label="Perk Nation home"><span class="brandMark"><img src="/assets/mark.svg" alt="" width="24" height="24" /></span><span>Perk Nation</span></a>
      <nav class="navlinks" aria-label="Primary navigation"><a href="/directory">Directory</a><a href="/events">Events</a><a href="/members">Members</a><a href="/merchants">Merchants</a><a href="/contact-us">Contact Us</a></nav>
      <div class="navcta"><a class="btn ghost" href="/login">Login</a></div>
    </div>
  </div>
</header>
<main class="articleShell">
  <article class="container">
    <a class="articleBackLink" href="/articles/dine-la-pasadena-2026">Back to the city guide hub</a>
    <section class="articleHeroGrid">
      <div class="articleHeroCopy">
        <div class="badge">Dine LA by city</div>
        <h1>Dine LA { _escape(city_name) } guide: ranked picks from {restaurant_count} restaurants.</h1>
        <p>{_escape(city_name)} has {restaurant_count} Dine LA restaurants to choose from. Use this city guide to compare ranked picks, cuisines, price tiers, and nearby Perk Nation discovery paths before booking.</p>
        <div class="articleFactGrid">
          <div><span>Dates</span><strong>{_escape(data.get('dates') or 'August 14-28, 2026')}</strong></div>
          <div><span>Restaurants</span><strong>{restaurant_count} choices</strong></div>
          <div><span>Top cuisines</span><strong>{_escape(cuisines)}</strong></div>
          <div><span>Price tiers</span><strong>{_escape(price_summary)}</strong></div>
        </div>
        <div class="articleActions">
          <a class="btn primary" href="{_escape(source_url)}" target="_blank" rel="noopener noreferrer">Open Dine LA restaurant pages</a>
          <a class="btn" href="{_escape(directory_route)}">Search { _escape(city_name) } on Perk Nation</a>
        </div>
        <div class="sharePanel" data-share-panel data-share-title="Dine LA { _escape(city_name) } guide" data-share-text="Share the Perk Nation Dine LA guide for { _escape(city_name) }." data-share-url="{_escape(share_url)}">
          <div class="shareIntro"><span>Share this city guide</span><strong>Send the { _escape(city_name) } restaurant picks.</strong></div>
          <div class="shareActions" aria-label="Share options">
            <button type="button" data-share-action="instagram">Instagram</button>
            <button type="button" data-share-action="facebook">Facebook</button>
            <button type="button" data-share-action="tiktok">TikTok</button>
            <button type="button" data-share-action="sms">SMS</button>
            <button type="button" data-share-action="imessage">iMessage</button>
            <button type="button" data-share-action="email">Email</button>
            <button type="button" data-share-action="copy">Copy link</button>
          </div>
          <div class="shareStatus" data-share-status aria-live="polite"></div>
        </div>
      </div>
      <figure class="articleHeroMedia">
        <img src="/assets/articles/dine-la-pasadena-2026.jpg" alt="Golden-hour restaurant table with spritz drinks, seasonal plates, and a city dining view" />
        <figcaption>Use the guide below to compare restaurants, then confirm current menus and booking windows before visiting.</figcaption>
      </figure>
    </section>
    <section class="articleBodyGrid">
      <div class="articleStory">
        <h2>How to plan { _escape(city_name) }</h2>
        <p>{_escape(directory_note)}</p>
        <p>Use the rankings first, then use the full list when you already know the cuisine, neighborhood, or price tier you want. The ranking favors restaurants with broader meal availability, clearer value, strong occasion fit, and cuisine intent that people commonly search during restaurant week.</p>
        <h2>Top ranked restaurants in { _escape(city_name) }</h2>
        <ol>
{ranked_items}
        </ol>
        <h2>More { _escape(city_name) } restaurants to compare</h2>
        <ul>
{restaurant_items}
        </ul>
      </div>
      <aside class="articleSourceCard">
        <h2>How to choose</h2>
        <ul>
          <li>Pick lunch when you want value and easier reservations.</li>
          <li>Pick dinner-only restaurants for date nights and celebrations.</li>
          <li>Use higher tiers for occasion meals, not casual first tries.</li>
          <li>Open each restaurant page before booking to confirm menus.</li>
        </ul>
        <a href="{_escape(source_url)}" target="_blank" rel="noopener noreferrer">Dine LA restaurant pages</a>
        <a href="{_escape(directory_route)}">Perk Nation { _escape(city_name) } search</a>
        <h2>Other city guides</h2>
        <ul>
{related_items}
        </ul>
      </aside>
    </section>
  </article>
</main>
<footer class="footer"><div class="container"><div class="footerBottom"><span>© 2026 Perk Nation</span><span><a href="/directory">Directory</a> · <a href="/events">Events</a> · <a href="/privacy-policy">Privacy</a></span></div></div></footer>
<script src="/assets/share.js" defer></script>
</body>
</html>"""


def _theme_path(path: str, *, white: bool) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    if not white:
        return normalized
    return f"/white{normalized}" if normalized != "/" else "/white/"


def _asset_path(asset: str, *, white: bool) -> str:
    prefix = "/white/assets" if white else "/assets"
    return f"{prefix}/{asset.lstrip('/')}"


def _business_page_path(slug: str, *, white: bool) -> str:
    return _theme_path(f"/business/{slug}", white=white)


def _directory_page_path(*, white: bool, city_slug: Optional[str] = None, business_type_slug: Optional[str] = None) -> str:
    if city_slug and business_type_slug:
        return _theme_path(f"/directory/{city_slug}/{business_type_slug}", white=white)
    if city_slug:
        return _theme_path(f"/directory/{city_slug}", white=white)
    if business_type_slug:
        return _theme_path(f"/directory/type/{business_type_slug}", white=white)
    return _theme_path("/directory", white=white)


def _directory_shell(*, title: str, description: str, canonical_path: str, body: str, white: bool, json_ld: Optional[dict] = None) -> str:
    brand_href = "/white/" if white else "/"
    style_href = f"{_asset_path('styles.css', white=white)}?v={_PUBLIC_BUILD_ID}"
    script_href = f"{_asset_path('app.js', white=white)}?v={_PUBLIC_BUILD_ID}"
    json_ld_html = ""
    if json_ld:
        json_ld_payload = json.dumps(json_ld, ensure_ascii=False).replace("</", "<\\/")
        json_ld_html = (
            "\n  <script type=\"application/ld+json\">"
            + json_ld_payload
            + "</script>"
        )
    return f"""<!doctype html>
<html lang="en" data-theme="{'light' if white else 'dark'}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="{_escape(description)}" />
  <meta name="theme-color" content="{'#ffffff' if white else '#0d0d0d'}" />
  <title>{_escape(title)}</title>
  <link rel="canonical" href="{_escape(_public_url(canonical_path))}" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Rethink+Sans:wght@300;400;500;600;700;800;900&amp;display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="{_escape(style_href)}" />{json_ld_html}
</head>
<body data-directory-page="1">
<header class="header">
  <div class="container">
    <div class="nav">
      <a class="brand" href="{_escape(brand_href)}" aria-label="Perk Nation home">
        <span class="brandMark" aria-hidden="true"><img src="{_escape(_asset_path('mark.svg', white=white))}" alt="" width="24" height="24" /></span>
        <span>Perk Nation</span>
      </a>
      <nav class="navlinks" aria-label="Primary navigation">
        <a href="{_escape(_theme_path('/directory', white=white))}">Directory</a>
        <a href="{_escape(_theme_path('/members', white=white))}">Members</a>
        <a href="{_escape(_theme_path('/merchants', white=white))}">Merchants</a>
        <a href="{_escape(_theme_path('/how-it-works', white=white))}">How it Works</a>
        <a href="{_escape(_theme_path('/contact-us', white=white))}">Contact Us</a>
        <a href="{_escape(_theme_path('/faq', white=white))}">FAQ</a>
      </nav>
      <div class="navcta">
        <a class="btn ghost" href="{_escape(_theme_path('/login', white=white))}">Login</a>
      </div>
    </div>
  </div>
</header>
<main>{body}</main>
<footer class="footer">
  <div class="container">
    <div class="footerGrid">
      <div><strong>Perk Nation</strong><p class="small">Local business directory, rewards, offers, and neighborhood discovery.</p></div>
      <div><a href="{_escape(_theme_path('/directory', white=white))}">Business Directory</a><a href="{_escape(_theme_path('/contact-us', white=white))}">Contact Us</a></div>
    </div>
  </div>
</footer>
<script src="{_escape(script_href)}"></script>
</body>
</html>"""


def _facet_by_slug(items: list[dict[str, object]], slug: Optional[str]) -> Optional[dict[str, object]]:
    if not slug:
        return None
    for item in items:
        if str(item.get("slug") or "") == slug:
            return item
    return None


def _contact_href_phone(phone: Optional[str]) -> str:
    cleaned = "".join(ch for ch in str(phone or "") if ch.isdigit() or ch == "+")
    return f"tel:{cleaned}" if cleaned else ""


def _business_city_line(row) -> str:
    return ", ".join(part for part in (row.search_city or row.city, row.state, row.zip_code) if part)


def _business_location_label(row) -> str:
    address = str(row.address or "").strip()
    city_line = _business_city_line(row)
    if address and city_line:
        address_lower = address.lower()
        city = str(row.search_city or row.city or "").lower()
        zip_code = str(row.zip_code or "")
        if (city and city in address_lower) or (zip_code and zip_code in address):
            return address
    return " ".join(part for part in (address, city_line) if part).strip()


def _business_map_query(row) -> str:
    location = _business_location_label(row)
    if not location:
        return ""
    return normalize_spaces(f"{row.business_name} {location}")


def _business_google_maps_url(row) -> str:
    query = _business_map_query(row)
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}" if query else ""


def _business_google_directions_url(row) -> str:
    query = _business_map_query(row)
    return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(query)}" if query else ""


def _business_apple_maps_url(row) -> str:
    query = _business_map_query(row)
    return f"https://maps.apple.com/?daddr={quote_plus(query)}" if query else ""


def _business_geo_uri(row) -> str:
    query = _business_map_query(row)
    return f"geo:0,0?q={quote(query)}" if query else ""


def _business_map_embed_url(row) -> str:
    query = _business_map_query(row)
    return f"https://www.google.com/maps?q={quote_plus(query)}&output=embed" if query else ""


def _directory_map_links(row, *, include_search: bool = False) -> str:
    directions_url = _business_google_directions_url(row)
    if not directions_url:
        return ""
    links = [f'<a href="{_escape(directions_url)}" target="_blank" rel="noopener">Directions</a>']
    apple_url = _business_apple_maps_url(row)
    geo_uri = _business_geo_uri(row)
    search_url = _business_google_maps_url(row)
    if apple_url:
        links.append(f'<a href="{_escape(apple_url)}" target="_blank" rel="noopener">Apple Maps</a>')
    if geo_uri:
        links.append(f'<a href="{_escape(geo_uri)}">GPS</a>')
    if include_search and search_url:
        links.append(f'<a href="{_escape(search_url)}" target="_blank" rel="noopener">Map</a>')
    return "".join(links)


def _directory_search_controls(
    *,
    facets: dict[str, list[dict[str, object]]],
    q: str,
    selected_city: str,
    selected_type: str,
    white: bool,
) -> str:
    city_options = ['<option value="">All cities</option>']
    for city in facets["cities"]:
        label = str(city.get("label") or "")
        selected = " selected" if label.lower() == selected_city.lower() else ""
        city_options.append(f'<option value="{_escape(label)}"{selected}>{_escape(label)} ({int(city.get("count") or 0)})</option>')

    type_options = ['<option value="">All business types</option>']
    for business_type in facets["business_types"]:
        label = str(business_type.get("label") or "")
        icon = str(business_type.get("icon") or "•")
        selected = " selected" if label.lower() == selected_type.lower() else ""
        type_options.append(
            f'<option value="{_escape(label)}"{selected}>{_escape(icon)} {_escape(label)} ({int(business_type.get("count") or 0)})</option>'
        )

    return f"""
      <form class="directorySearchForm" method="get" action="{_escape(_directory_page_path(white=white))}" data-directory-search-form>
        <label class="srOnly" for="directory-page-query">Search businesses</label>
        <input id="directory-page-query" name="q" type="search" value="{_escape(q)}" placeholder="Search restaurants, contractors, services, shops..." data-directory-search-input />
        <label class="srOnly" for="directory-page-city">Filter by city</label>
        <select id="directory-page-city" name="city" data-directory-city-select>{"".join(city_options)}</select>
        <label class="srOnly" for="directory-page-type">Filter by business type</label>
        <select id="directory-page-type" name="business_type" data-directory-type-select>{"".join(type_options)}</select>
        <button class="btn primary" type="submit">Search</button>
      </form>
    """


_DIRECTORY_CATEGORY_HIERARCHY = (
    (
        "Food, Dining & Hospitality",
        "🍽",
        (
            ("Restaurants & Dining", ("restaurant", "cafe", "eating place", "dining", "bar", "catering", "brew", "wine")),
            ("Food, Grocery & Supply", ("food", "grocery", "bakery", "beverage", "ingredient")),
            ("Hotels, Travel & Events", ("hotel", "motel", "lodging", "travel", "tourism", "event", "banquet", "wedding")),
        ),
    ),
    (
        "Home, Construction & Property",
        "🔧",
        (
            ("Construction & Trades", ("building", "contractor", "construction", "plumbing", "electrical", "roof", "floor", "handyman", "hvac", "landscape", "repair")),
            ("Real Estate & Housing", ("real estate", "apartment", "property", "mortgage", "title", "leasing", "housing")),
            ("Home Services", ("cleaning", "pest", "moving", "storage", "interior", "furniture", "home service")),
        ),
    ),
    (
        "Health, Wellness & Personal Care",
        "✚",
        (
            ("Medical & Dental", ("medical", "health care", "healthcare", "hospital", "doctor", "dentist", "dental", "physician", "optometry", "pharmacy")),
            ("Wellness & Fitness", ("wellness", "fitness", "chiropr", "massage", "therapy", "mental health", "senior care")),
            ("Beauty & Personal Care", ("beauty", "barber", "salon", "nail", "spa", "cosmetic")),
        ),
    ),
    (
        "Shopping, Automotive & Consumer",
        "🛍",
        (
            ("Retail & Shopping", ("retail", "shopping", "store", "jewelry", "apparel", "florist")),
            ("Automotive & Transportation", ("auto", "vehicle", "transport", "shuttle", "airport", "towing", " car ")),
            ("Consumer Services", ("laundry", "pet", "recreation", "photo booth")),
        ),
    ),
    (
        "Business, Finance & Legal",
        "$",
        (
            ("Finance & Insurance", ("bank", "credit union", "financial", "account", "bookkeep", "tax", "insurance", "wealth", "lending", "merchant service")),
            ("Legal & Public Services", ("attorney", "legal", "law", "government", "municipal", "utilities", "water district")),
            ("Consulting & Professional", ("consultant", "professional", "employment", "human resources", "business service", "broker")),
        ),
    ),
    (
        "Technology, Media & Creative",
        "⌘",
        (
            ("Technology & Online", ("technology", "software", "computer", "e-commerce", "internet", "telecom", "app development")),
            ("Marketing & Media", ("marketing", "advertising", "media", "printing", "publishing", "magazine", "graphic", "photography")),
            ("Arts & Entertainment", ("entertainment", "artist", "performing", "music", "sports", "screen printing")),
        ),
    ),
    (
        "Education, Community & Nonprofit",
        "🎓",
        (
            ("Education & Training", ("education", "school", "college", "university", "training", "teacher")),
            ("Nonprofits & Associations", ("non-profit", "nonprofit", "association", "chamber", "foundation", "church")),
            ("Community Services", ("community", "youth", "social service")),
        ),
    ),
    (
        "Manufacturing & Other Services",
        "◆",
        (
            ("Manufacturing & Distribution", ("manufacturing", "mfg", "wholesale", "warehouse", "distributor", "supplier", "scientific")),
            ("Industrial & Environmental", ("industrial", "environment", "energy", "solar", "engineering")),
            ("Other Local Businesses", ()),
        ),
    ),
)


def _directory_category_groups(items: list[dict[str, object]]) -> list[dict[str, object]]:
    groups = [
        {
            "label": top_label,
            "icon": top_icon,
            "levels": [{"label": level_label, "keywords": keywords, "items": []} for level_label, keywords in levels],
        }
        for top_label, top_icon, levels in _DIRECTORY_CATEGORY_HIERARCHY
    ]
    fallback = groups[-1]["levels"][-1]["items"]
    for item in items:
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        normalized = f" {label.lower()} "
        destination = None
        for group in groups:
            for level in group["levels"]:
                keywords = level["keywords"]
                if keywords and any(keyword in normalized for keyword in keywords):
                    destination = level["items"]
                    break
            if destination is not None:
                break
        (destination if destination is not None else fallback).append(item)
    return groups


def _directory_category_menu(
    *,
    facets: dict[str, list[dict[str, object]]],
    white: bool,
    selected_city_slug: Optional[str],
    selected_type_slug: Optional[str],
) -> str:
    group_html = []
    for group in _directory_category_groups(facets["business_types"]):
        level_html = []
        group_count = 0
        for level in group["levels"]:
            items = level["items"]
            if not items:
                continue
            links = []
            level_count = 0
            level_active = False
            for item in items:
                slug = str(item.get("slug") or "")
                label = str(item.get("label") or "")
                count = int(item.get("count") or 0)
                if not slug or not label:
                    continue
                href = _directory_page_path(white=white, city_slug=selected_city_slug, business_type_slug=slug)
                if not selected_city_slug:
                    href = _directory_page_path(white=white, business_type_slug=slug)
                active = " active" if slug == selected_type_slug else ""
                level_active = level_active or bool(active)
                level_count += count
                links.append(
                    f'<a class="directorySubcategoryLink{active}" href="{_escape(href)}">'
                    f'<span>{_escape(label)}</span><em>{count}</em></a>'
                )
            group_count += level_count
            open_attr = " open" if level_active else ""
            level_html.append(
                f'<details class="directoryCategoryLevel"{open_attr}>'
                f'<summary><span>{_escape(level["label"])}</span><em>{level_count}</em></summary>'
                f'<div class="directorySubcategoryGrid">{"".join(links)}</div></details>'
            )
        if not level_html:
            continue
        group_html.append(
            '<section class="directoryCategoryGroup">'
            f'<div class="directoryCategoryGroupHeading"><span class="directoryIcon" aria-hidden="true">{_escape(group["icon"])}</span>'
            f'<strong>{_escape(group["label"])}</strong><em>{group_count}</em></div>'
            f'<div class="directoryCategoryLevels">{"".join(level_html)}</div></section>'
        )
    return (
        '<div class="directoryCategoryHierarchy" aria-label="Business category hierarchy">'
        '<div class="directoryHierarchyHeader"><strong>Browse categories</strong><span>Choose a top-level group, then expand a category.</span></div>'
        f'<div class="directoryCategoryGroupGrid">{"".join(group_html)}</div></div>'
    )


def _directory_city_links(*, facets: dict[str, list[dict[str, object]]], white: bool, selected_city_slug: Optional[str]) -> str:
    links = []
    for item in facets["cities"][:48]:
        slug = str(item.get("slug") or "")
        label = str(item.get("label") or "")
        count = int(item.get("count") or 0)
        if not slug or not label:
            continue
        active = " active" if slug == selected_city_slug else ""
        links.append(
            f'<a class="directoryCityLink{active}" href="{_escape(_directory_page_path(white=white, city_slug=slug))}">'
            f'{_escape(label)} <span>{count}</span></a>'
        )
    open_attr = " open" if selected_city_slug else ""
    return (
        f'<details class="directoryCityPanel"{open_attr}>'
        f'<summary><span>Browse cities</span><em>{len(links)} popular cities</em></summary>'
        f'<div class="directoryCityGrid" aria-label="City directory">{"".join(links)}</div></details>'
    )


def _directory_result_card(row, *, white: bool) -> str:
    business_url = _business_page_path(row.slug, white=white)
    website_html = ""
    if row.website:
        website = str(row.website)
        website_href = website if website.startswith(("http://", "https://")) else f"https://{website}"
        website_html = f'<a href="{_escape(website_href)}" target="_blank" rel="noopener nofollow">Website</a>'
    phone_href = _contact_href_phone(row.phone_number)
    phone_html = f'<a href="{_escape(phone_href)}">{_escape(row.phone_number)}</a>' if phone_href else _escape(row.phone_number)
    email_html = f'<a href="mailto:{_escape(row.email)}">{_escape(row.email)}</a>' if row.email else ""
    contact_bits = [bit for bit in (phone_html, email_html, website_html) if bit]
    meta_bits = [
        _escape(row.address),
        _escape(", ".join(part for part in (row.search_city, row.state, row.zip_code) if part)),
    ]
    meta_html = "".join(f"<span>{bit}</span>" for bit in meta_bits if bit)
    contact_html = "".join(f"<span>{bit}</span>" for bit in contact_bits)
    map_links = _directory_map_links(row)
    actions_html = f'<div class="directoryResultActions">{map_links}</div>' if map_links else ""
    description = _escape(row.description or "")
    return f"""
      <article class="directoryResultCard">
        <div class="directoryResultBody">
          <div class="directoryResultHeaderLine">
            <h2><a href="{_escape(business_url)}">{_escape(row.business_name)}</a></h2>
            <a class="directoryResultType" href="{_escape(_directory_page_path(white=white, business_type_slug=row.business_type_slug))}">
              <span class="directoryIcon" aria-hidden="true">{_escape(row.business_type_icon or "•")}</span>
              <span>{_escape(row.business_type or "Local business")}</span>
            </a>
          </div>
          <p class="directoryResultDescription">{description}</p>
          <div class="directoryResultInfoLine">
            <div class="directoryResultMeta">{meta_html}</div>
            <div class="directoryResultContact">{contact_html}</div>
            {actions_html}
          </div>
        </div>
      </article>
    """


def _directory_map_panel(rows) -> str:
    mappable_rows = [row for row in rows if _business_map_query(row)][:8]
    if not mappable_rows:
        return ""

    first = mappable_rows[0]
    item_html = []
    for row in mappable_rows:
        location = _business_location_label(row)
        links = _directory_map_links(row, include_search=True)
        item_html.append(
            f"""
              <div class="directoryMapItem">
                <div>
                  <strong>{_escape(row.business_name)}</strong>
                  <span>{_escape(location)}</span>
                </div>
                <div class="directoryMapActions">{links}</div>
              </div>
            """
        )

    return f"""
      <div class="directoryMapPanel" aria-label="Business result map">
        <div class="directoryMapFrame">
          <iframe
            title="Map for {_escape(first.business_name)}"
            src="{_escape(_business_map_embed_url(first))}"
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade"></iframe>
        </div>
        <div class="directoryMapList">
          <div>
            <div class="badge">Map-ready listings</div>
            <p class="muted">Open directions, Apple Maps, or mobile GPS for businesses with imported address data.</p>
          </div>
          {"".join(item_html)}
        </div>
      </div>
    """


def _directory_item_list_json_ld(rows, *, white: bool) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Perk Nation Business Directory",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index + 1,
                "name": row.business_name,
                "url": _public_url(_business_page_path(row.slug, white=white)),
            }
            for index, row in enumerate(rows)
        ],
    }


def _render_directory_page(
    *,
    white: bool = False,
    q: str = "",
    city: Optional[str] = None,
    business_type: Optional[str] = None,
    city_slug: Optional[str] = None,
    business_type_slug: Optional[str] = None,
) -> str:
    with SessionLocal() as db:
        facets = directory_facets(db)
        city_facet = _facet_by_slug(facets["cities"], city_slug)
        type_facet = _facet_by_slug(facets["business_types"], business_type_slug)
        selected_city = str(city or (city_facet or {}).get("label") or "")
        selected_type = str(business_type or (type_facet or {}).get("label") or "")
        rows, total = search_business_directory(
            db,
            query=q,
            city=selected_city or None,
            city_slug=city_slug,
            business_type=selected_type or None,
            business_type_slug=business_type_slug,
            limit=30,
        )

    if selected_type and selected_city:
        page_heading = f"{selected_type} Businesses in {selected_city}"
    elif selected_type:
        page_heading = f"{selected_type} Businesses"
    elif selected_city:
        page_heading = f"Businesses in {selected_city}"
    else:
        page_heading = "Local Business Directory"
    page_title = f"{page_heading} | Perk Nation"
    description = normalize_spaces(
        f"Search {total or 'local'} Perk Nation directory listings"
        + (f" for {selected_type}" if selected_type else "")
        + (f" in {selected_city}" if selected_city else "")
        + ". Find descriptions, addresses, websites, phone numbers, and contact details."
    )
    canonical_path = _directory_page_path(white=False, city_slug=city_slug, business_type_slug=business_type_slug)
    if business_type_slug and not city_slug:
        canonical_path = _directory_page_path(white=False, business_type_slug=business_type_slug)

    cards_html = "".join(_directory_result_card(row, white=white) for row in rows)
    empty_html = ""
    if not rows:
        empty_html = '<div class="directoryEmpty">No matching businesses yet. Try a different city, business type, or search term.</div>'

    body = f"""
      <section class="section directoryPageHero">
        <div class="container">
          <div class="directoryHeroLayout">
            <div>
              <div class="badge">Perk Nation local directory</div>
              <h1 class="h1 luxTitle">{_escape(page_heading)}</h1>
              <p class="p">{_escape(description)}</p>
            </div>
            <div class="directoryHeroStats">
              <div><strong>{total}</strong><span>matching listings</span></div>
              <div><strong>{len(facets['cities'])}</strong><span>cities</span></div>
              <div><strong>{len(facets['business_types'])}</strong><span>business types</span></div>
            </div>
          </div>
          {_directory_search_controls(facets=facets, q=q, selected_city=selected_city, selected_type=selected_type, white=white)}
          {_directory_category_menu(facets=facets, white=white, selected_city_slug=city_slug, selected_type_slug=business_type_slug)}
          {_directory_city_links(facets=facets, white=white, selected_city_slug=city_slug)}
        </div>
      </section>
      <section class="section directoryResultsSection">
        <div class="container">
          <div class="directoryResultsHeader">
            <h2 class="h2">Business results</h2>
            <p class="muted">Listings are sourced from the imported chamber and city directory spreadsheets, with website metadata added when available.</p>
          </div>
          {_directory_map_panel(rows)}
          <div class="directoryResultsGrid" data-directory-results>{cards_html}</div>
          {empty_html}
        </div>
      </section>
    """
    return _directory_shell(
        title=page_title,
        description=description,
        canonical_path=canonical_path,
        body=body,
        white=white,
        json_ld=_directory_item_list_json_ld(rows, white=white),
    )


def _business_json_ld(row) -> dict:
    address = {
        "@type": "PostalAddress",
        "streetAddress": row.address,
        "addressLocality": row.search_city or row.city,
        "addressRegion": row.state,
        "postalCode": row.zip_code,
        "addressCountry": "US",
    }
    payload = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": row.business_name,
        "description": row.seo_description or row.description,
        "url": row.website or _public_url(_business_page_path(row.slug, white=False)),
        "telephone": row.phone_number,
        "email": row.email,
        "address": {key: value for key, value in address.items() if value},
        "additionalType": row.business_type,
    }
    if row.image_url:
        payload["image"] = row.image_url
    map_url = _business_google_maps_url(row)
    if map_url:
        payload["hasMap"] = map_url
    return {key: value for key, value in payload.items() if value}


def _render_business_page(*, slug: str, white: bool = False) -> str:
    with SessionLocal() as db:
        row = get_business_directory_entry(db, slug)
        if row is None:
            raise HTTPException(status_code=404, detail="Business not found")
        related, _total = search_business_directory(
            db,
            city_slug=row.search_city_slug,
            business_type_slug=row.business_type_slug,
            limit=8,
        )

    related_links = []
    for related_row in related:
        if related_row.slug == row.slug:
            continue
        related_links.append(
            f'<a href="{_escape(_business_page_path(related_row.slug, white=white))}">'
            f'<span class="directoryIcon" aria-hidden="true">{_escape(related_row.business_type_icon or "•")}</span>'
            f'{_escape(related_row.business_name)}</a>'
        )
        if len(related_links) >= 6:
            break

    media_html = ""
    if row.video_url:
        media_html = f'<video class="directoryDetailMedia" src="{_escape(row.video_url)}" controls preload="metadata"></video>'
    elif row.image_url:
        media_html = f'<img class="directoryDetailMedia" src="{_escape(row.image_url)}" alt="{_escape(row.business_name)}" loading="lazy" />'

    website_html = ""
    if row.website:
        website_href = row.website if row.website.startswith(("http://", "https://")) else f"https://{row.website}"
        website_html = f'<a class="btn primary" href="{_escape(website_href)}" target="_blank" rel="noopener nofollow">Visit website</a>'
    map_links = _directory_map_links(row, include_search=True)
    map_actions_html = f'<div class="directoryMapActions">{map_links}</div>' if map_links else ""
    directions_button = ""
    directions_url = _business_google_directions_url(row)
    if directions_url:
        directions_button = f'<a class="btn" href="{_escape(directions_url)}" target="_blank" rel="noopener">Get directions</a>'
    map_html = ""
    map_embed_url = _business_map_embed_url(row)
    if map_embed_url:
        map_html = f"""
          <div class="directoryDetailMap">
            <iframe
              title="Map for {_escape(row.business_name)}"
              src="{_escape(map_embed_url)}"
              loading="lazy"
              referrerpolicy="no-referrer-when-downgrade"></iframe>
            {map_actions_html}
          </div>
        """
    else:
        map_html = '<div class="directoryMapUnavailable">No imported address or city was available for map directions.</div>'

    phone_href = _contact_href_phone(row.phone_number)
    phone_html = f'<a href="{_escape(phone_href)}">{_escape(row.phone_number)}</a>' if phone_href else _escape(row.phone_number)
    detail_rows = [
        ("Business type", row.business_type),
        ("Address", row.address),
        ("City", ", ".join(part for part in (row.search_city, row.state, row.zip_code) if part)),
        ("Phone", phone_html),
        ("Email", f'<a href="mailto:{_escape(row.email)}">{_escape(row.email)}</a>' if row.email else ""),
        ("Contact", row.contact_person),
        ("Source", row.data_source),
    ]
    detail_html = "".join(
        f"<div><dt>{_escape(label)}</dt><dd>{value if label in {'Phone', 'Email'} else _escape(value)}</dd></div>"
        for label, value in detail_rows
        if value
    )
    body = f"""
      <section class="section directoryDetailSection">
        <div class="container">
          <a class="jewelryBackLink" href="{_escape(_directory_page_path(white=white))}">Back to directory</a>
          <div class="directoryDetailGrid">
            <div class="directoryDetailMain">
              <div class="badge">{_escape(row.business_type or 'Local business')}</div>
              <h1 class="h1 luxTitle">{_escape(row.business_name)}</h1>
              <p class="p">{_escape(row.description or '')}</p>
              <div class="directoryDetailActions">
                {website_html}
                {directions_button}
                <a class="btn" href="{_escape(_directory_page_path(white=white, city_slug=row.search_city_slug))}">More in {_escape(row.search_city or 'this city')}</a>
              </div>
              <dl class="directoryDetailFacts">{detail_html}</dl>
            </div>
            <aside class="directoryDetailAside">
              {media_html}
              {map_html}
              <div class="directorySourceBox">
                <strong>Directory source</strong>
                <p>Imported from {_escape(row.source_file)} / {_escape(row.source_sheet)} row {_escape(row.source_row)}.</p>
              </div>
              <div class="directoryRelated">
                <strong>Related listings</strong>
                {"".join(related_links) if related_links else '<span class="muted">More listings will appear as the directory grows.</span>'}
              </div>
            </aside>
          </div>
        </div>
      </section>
    """
    title = row.seo_title or f"{row.business_name} | Perk Nation Directory"
    description = row.seo_description or normalize_spaces(row.description or "")
    return _directory_shell(
        title=title,
        description=description,
        canonical_path=_business_page_path(row.slug, white=False),
        body=body,
        white=white,
        json_ld=_business_json_ld(row),
    )


def _directory_sitemap_xml(*, white: bool = False) -> str:
    urls = {_theme_path("/directory", white=white)}
    try:
        with SessionLocal() as db:
            facets = directory_facets(db)
            for city in facets["cities"]:
                slug = str(city.get("slug") or "")
                if slug:
                    urls.add(_directory_page_path(white=white, city_slug=slug))
            for business_type in facets["business_types"]:
                slug = str(business_type.get("slug") or "")
                if slug:
                    urls.add(_directory_page_path(white=white, business_type_slug=slug))
            for slug in directory_sitemap_entries(db):
                urls.add(_business_page_path(slug, white=white))
    except Exception:
        logger.exception("Unable to build business directory sitemap")

    body = "\n".join(f"  <url><loc>{_escape(_public_url(url))}</loc></url>" for url in sorted(urls))
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'


_SITEMAP_SKIP_PATHS = {
    "/admin",
    "/api",
    "/guests",
    "/home",
    "/invite",
    "/login",
    "/merchant",
    "/redeem",
    "/reset-password",
    "/user",
    "/web/config",
}


def _canonical_sitemap_url(raw_loc: str, *, white: bool) -> str:
    raw = html.unescape(str(raw_loc or "").strip())
    if not raw:
        return ""

    if raw.startswith(("http://", "https://")):
        canonical = settings._canonical_public_url(raw)
        path = urlsplit(canonical).path or "/"
    else:
        path = raw

    if not path.startswith("/"):
        path = f"/{path}"

    if path == "/index.html":
        path = "/"
    elif path.endswith(".html"):
        path = path[:-5]

    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    if path in _SITEMAP_SKIP_PATHS:
        return ""
    if path.startswith("/white/") or path == "/white":
        if not white:
            return ""
    elif white:
        path = _theme_path(path, white=True)

    return _public_url(path)


def _sitemap_urls_from_xml(content: str, *, white: bool) -> set[str]:
    urls: set[str] = set()
    for match in re.finditer(r"<loc>\s*(.*?)\s*</loc>", content or "", flags=re.IGNORECASE | re.DOTALL):
        url = _canonical_sitemap_url(match.group(1), white=white)
        if url:
            urls.add(url)
    return urls


def _sitemap_xml_from_urls(urls: set[str]) -> str:
    body = "\n".join(f"  <url><loc>{_escape(url)}</loc></url>" for url in sorted(urls))
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'


def _append_directory_sitemap(content: str, *, white: bool = False) -> str:
    urls = _sitemap_urls_from_xml(content, white=white)
    directory_xml = _directory_sitemap_xml(white=white)
    urls.update(_sitemap_urls_from_xml(directory_xml, white=white))
    return _sitemap_xml_from_urls(urls)


def _robots_txt(*, white: bool = False) -> str:
    sitemap_path = "/white/sitemap.xml" if white else "/sitemap.xml"
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /api",
        "Disallow: /invite",
        "Disallow: /login",
        "Disallow: /merchant",
        "Disallow: /redeem",
        "Disallow: /reset-password",
        "Disallow: /user",
        "Disallow: /web/config",
    ]
    if not white:
        lines.append("Disallow: /white/")
        lines.append("Sitemap: https://perknation.app/business-directory-sitemap.xml")
    lines.append(f"Sitemap: {_public_url(sitemap_path)}")
    return "\n".join(lines) + "\n"


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


@app.get("/directory", response_class=HTMLResponse)
def home_portal_directory(
    q: str = "",
    city: Optional[str] = None,
    business_type: Optional[str] = None,
) -> str:
    return _render_directory_page(white=False, q=q, city=city, business_type=business_type)


@app.get("/directory/type/{business_type_slug}", response_class=HTMLResponse)
def home_portal_directory_type(business_type_slug: str, q: str = "") -> str:
    return _render_directory_page(white=False, q=q, business_type_slug=business_type_slug)


@app.get("/directory/{city_slug}/{business_type_slug}", response_class=HTMLResponse)
def home_portal_directory_city_type(city_slug: str, business_type_slug: str, q: str = "") -> str:
    return _render_directory_page(white=False, q=q, city_slug=city_slug, business_type_slug=business_type_slug)


@app.get("/directory/{city_slug}", response_class=HTMLResponse)
def home_portal_directory_city(city_slug: str, q: str = "") -> str:
    return _render_directory_page(white=False, q=q, city_slug=city_slug)


@app.get("/business/{business_slug}", response_class=HTMLResponse)
def home_portal_business_directory_detail(business_slug: str) -> str:
    return _render_business_page(slug=business_slug, white=False)


@app.get("/jewelry", include_in_schema=False)
def home_portal_jewelry_redirect() -> RedirectResponse:
    return RedirectResponse(url="/#crystal-jewelry", status_code=308)


@app.get("/jewelry/{product_slug}", response_class=HTMLResponse)
def home_portal_jewelry_product(product_slug: str) -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "jewelry-product.html", "Jewelry product page")


@app.get("/hollywood-sports", response_class=HTMLResponse)
def home_portal_hollywood_sports() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "hollywood-sports.html", "Hollywood Sports landing page")


@app.get("/events", response_class=HTMLResponse)
def home_portal_events() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "events.html", "Events page")


@app.get("/events/{event_slug}", response_class=HTMLResponse)
def home_portal_event_article(event_slug: str) -> str:
    if event_slug not in _EVENT_SLUGS:
        raise HTTPException(status_code=404, detail="Event article not found")
    return _render_event_article(event_slug)


@app.get("/articles/{article_slug}", response_class=HTMLResponse)
def home_portal_article(article_slug: str) -> str:
    filename = _ARTICLE_HTML_FILES.get(article_slug.strip().lower())
    if filename:
        return _read_html_or_missing(_HOME_PORTAL_DIR / "articles" / filename, "Article")
    rendered_article = _render_dine_la_city_article(article_slug)
    if rendered_article:
        return rendered_article
    raise HTTPException(status_code=404, detail="Article not found")


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
    return _read_html_or_missing(_HOME_PORTAL_DIR / "index.html", "Home portal", theme="light")


@app.get("/white/login", response_class=HTMLResponse)
def home_portal_white_login() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "login.html", "Login page", theme="light")


@app.get("/white/redeem", response_class=HTMLResponse)
def home_portal_white_redeem() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "redeem.html", "Redeem page", theme="light")


@app.get("/white/invite", response_class=HTMLResponse)
def home_portal_white_invite() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "invite.html", "Invite page", theme="light")


@app.get("/white/reset-password", response_class=HTMLResponse)
def home_portal_white_reset_password() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "reset-password.html", "Reset-password page", theme="light")


@app.get("/white/create-account", response_class=HTMLResponse)
def home_portal_white_create_account() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "create-account.html", "Create-account page", theme="light")


@app.get("/white/members", response_class=HTMLResponse)
def home_portal_white_members() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "members.html", "Members page", theme="light")


@app.get("/white/directory", response_class=HTMLResponse)
def home_portal_white_directory(
    q: str = "",
    city: Optional[str] = None,
    business_type: Optional[str] = None,
) -> str:
    return _render_directory_page(white=True, q=q, city=city, business_type=business_type)


@app.get("/white/directory/type/{business_type_slug}", response_class=HTMLResponse)
def home_portal_white_directory_type(business_type_slug: str, q: str = "") -> str:
    return _render_directory_page(white=True, q=q, business_type_slug=business_type_slug)


@app.get("/white/directory/{city_slug}/{business_type_slug}", response_class=HTMLResponse)
def home_portal_white_directory_city_type(city_slug: str, business_type_slug: str, q: str = "") -> str:
    return _render_directory_page(white=True, q=q, city_slug=city_slug, business_type_slug=business_type_slug)


@app.get("/white/directory/{city_slug}", response_class=HTMLResponse)
def home_portal_white_directory_city(city_slug: str, q: str = "") -> str:
    return _render_directory_page(white=True, q=q, city_slug=city_slug)


@app.get("/white/business/{business_slug}", response_class=HTMLResponse)
def home_portal_white_business_directory_detail(business_slug: str) -> str:
    return _render_business_page(slug=business_slug, white=True)


@app.get("/white/jewelry", include_in_schema=False)
def home_portal_white_jewelry_redirect() -> RedirectResponse:
    return RedirectResponse(url="/white/#crystal-jewelry", status_code=308)


@app.get("/white/jewelry/{product_slug}", response_class=HTMLResponse)
def home_portal_white_jewelry_product(product_slug: str) -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "jewelry-product.html", "Jewelry product page", theme="light")


@app.get("/white/hollywood-sports", response_class=HTMLResponse)
def home_portal_white_hollywood_sports() -> str:
    return _read_html_or_missing(
        _HOME_PORTAL_DIR / "hollywood-sports.html",
        "Hollywood Sports landing page",
        theme="light",
    )


@app.get("/white/events", response_class=HTMLResponse)
def home_portal_white_events() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "events.html", "Events page", theme="light")


@app.get("/white/events/{event_slug}", response_class=HTMLResponse)
def home_portal_white_event_article(event_slug: str) -> str:
    if event_slug not in _EVENT_SLUGS:
        raise HTTPException(status_code=404, detail="Event article not found")
    return _render_event_article(event_slug, theme="light")


@app.get("/white/articles/{article_slug}", response_class=HTMLResponse)
def home_portal_white_article(article_slug: str) -> str:
    filename = _ARTICLE_HTML_FILES.get(article_slug.strip().lower())
    if filename:
        return _read_html_or_missing(_HOME_PORTAL_DIR / "articles" / filename, "Article", theme="light")
    rendered_article = _render_dine_la_city_article(article_slug, white=True)
    if rendered_article:
        return rendered_article
    raise HTTPException(status_code=404, detail="Article not found")


@app.get("/white/guests", include_in_schema=False)
def home_portal_white_guests_redirect() -> RedirectResponse:
    return RedirectResponse(url="/white/members", status_code=308)


@app.get("/white/merchants", response_class=HTMLResponse)
def home_portal_white_merchants() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "merchants.html", "Merchants page", theme="light")


@app.get("/white/how-it-works", response_class=HTMLResponse)
def home_portal_white_how_it_works() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "how-it-works.html", "How-it-works page", theme="light")


@app.get("/white/contact-us", response_class=HTMLResponse)
def home_portal_white_contact_us() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "contact-us.html", "Contact-us page", theme="light")


@app.get("/white/faq", response_class=HTMLResponse)
def home_portal_white_faq() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "faq.html", "FAQ page", theme="light")


@app.get("/white/privacy-policy", response_class=HTMLResponse)
def home_portal_white_privacy_policy() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "privacy-policy.html", "Privacy-policy page", theme="light")


@app.get("/white/terms-of-use", response_class=HTMLResponse)
def home_portal_white_terms_of_use() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "terms-of-use.html", "Terms-of-use page", theme="light")


@app.get("/white/disclaimer", response_class=HTMLResponse)
def home_portal_white_disclaimer() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "disclaimer.html", "Disclaimer page", theme="light")


@app.get("/white/merchant-terms", response_class=HTMLResponse)
def home_portal_white_merchant_terms() -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "merchant-terms.html", "Merchant terms page", theme="light")


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
    return _read_html_or_missing(_HOME_PORTAL_DIR / filename, "Home portal page", theme="light")


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
    return _robots_txt()


@app.get("/sitemap.xml")
def home_portal_sitemap() -> Response:
    content = _read_text_or_missing(_HOME_PORTAL_DIR / "sitemap.xml", fallback="<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"/>")
    return Response(content=_append_directory_sitemap(content), media_type="application/xml")


@app.get("/business-directory-sitemap.xml")
def home_portal_business_directory_sitemap() -> Response:
    return Response(content=_directory_sitemap_xml(), media_type="application/xml")


@app.get(_INDEXNOW_KEY_PATH, response_class=PlainTextResponse, include_in_schema=False)
def home_portal_indexnow_key() -> str:
    return _INDEXNOW_KEY


@app.get("/white/robots.txt", response_class=PlainTextResponse)
def home_portal_white_robots() -> str:
    return _robots_txt(white=True)


@app.get("/white/sitemap.xml")
def home_portal_white_sitemap() -> Response:
    content = _read_text_or_missing(_HOME_PORTAL_WHITE_DIR / "sitemap.xml", fallback="<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"/>")
    return Response(content=_append_directory_sitemap(content, white=True), media_type="application/xml")


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
