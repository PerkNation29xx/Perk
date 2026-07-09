from contextlib import asynccontextmanager
import html
import json
import logging
from urllib.parse import quote, quote_plus

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
_GOOGLE_ANALYTICS_SNIPPET = f"""<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={_GOOGLE_ANALYTICS_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());

  gtag('config', '{_GOOGLE_ANALYTICS_ID}');
</script>"""


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
    return Response(
        content=_inject_google_analytics(html),
        status_code=response.status_code,
        headers=headers,
        media_type=None,
    )

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


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _public_url(path: str) -> str:
    base_url = settings.public_web_base_url.rstrip("/") or "https://perknation.app"
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{base_url}{normalized}"


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
    style_href = f"{_asset_path('styles.css', white=white)}?v=directory20260709-map"
    script_href = f"{_asset_path('app.js', white=white)}?v=directory20260709-map"
    json_ld_html = ""
    if json_ld:
        json_ld_payload = json.dumps(json_ld, ensure_ascii=False).replace("</", "<\\/")
        json_ld_html = (
            "\n  <script type=\"application/ld+json\">"
            + json_ld_payload
            + "</script>"
        )
    return f"""<!doctype html>
<html lang="en">
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


def _directory_category_menu(
    *,
    facets: dict[str, list[dict[str, object]]],
    white: bool,
    selected_city_slug: Optional[str],
    selected_type_slug: Optional[str],
) -> str:
    links = []
    for item in facets["business_types"][:36]:
        slug = str(item.get("slug") or "")
        label = str(item.get("label") or "")
        icon = str(item.get("icon") or "•")
        count = int(item.get("count") or 0)
        if not slug or not label:
            continue
        href = _directory_page_path(white=white, city_slug=selected_city_slug, business_type_slug=slug)
        if not selected_city_slug:
            href = _directory_page_path(white=white, business_type_slug=slug)
        active = " active" if slug == selected_type_slug else ""
        links.append(
            f'<a class="directoryCategoryChip{active}" href="{_escape(href)}">'
            f'<span class="directoryIcon" aria-hidden="true">{_escape(icon)}</span>'
            f'<span>{_escape(label)}</span><em>{count}</em></a>'
        )
    return f'<div class="directoryCategoryRail" aria-label="Business type directory">{"".join(links)}</div>'


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
    return f'<div class="directoryCityRail" aria-label="City directory">{"".join(links)}</div>'


def _directory_result_card(row, *, white: bool) -> str:
    business_url = _business_page_path(row.slug, white=white)
    image_html = ""
    if row.image_url:
        image_html = f'<img class="directoryResultImage" src="{_escape(row.image_url)}" alt="{_escape(row.business_name)}" loading="lazy" />'
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
        {image_html}
        <div class="directoryResultBody">
          <div class="directoryResultType">
            <span class="directoryIcon" aria-hidden="true">{_escape(row.business_type_icon or "•")}</span>
            <a href="{_escape(_directory_page_path(white=white, business_type_slug=row.business_type_slug))}">{_escape(row.business_type or "Local business")}</a>
          </div>
          <h2><a href="{_escape(business_url)}">{_escape(row.business_name)}</a></h2>
          <p>{description}</p>
          <div class="directoryResultMeta">{meta_html}</div>
          <div class="directoryResultContact">{contact_html}</div>
          {actions_html}
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


def _append_directory_sitemap(content: str, *, white: bool = False) -> str:
    directory_xml = _directory_sitemap_xml(white=white)
    dynamic_urls = "\n".join(line for line in directory_xml.splitlines() if line.strip().startswith("<url>"))
    if not dynamic_urls or "</urlset>" not in content:
        return content
    return content.replace("</urlset>", f"{dynamic_urls}\n</urlset>")


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


@app.get("/jewelry/{product_slug}", response_class=HTMLResponse)
def home_portal_jewelry_product(product_slug: str) -> str:
    return _read_html_or_missing(_HOME_PORTAL_DIR / "jewelry-product.html", "Jewelry product page")


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


@app.get("/white/jewelry/{product_slug}", response_class=HTMLResponse)
def home_portal_white_jewelry_product(product_slug: str) -> str:
    return _read_html_or_missing(_HOME_PORTAL_WHITE_DIR / "jewelry-product.html", "Jewelry product page (white)")


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
    robots = _read_text_or_missing(_HOME_PORTAL_DIR / "robots.txt", fallback="User-agent: *\nAllow: /\n")
    if "business-directory-sitemap.xml" not in robots:
        robots = robots.rstrip() + "\nSitemap: https://perknation.app/business-directory-sitemap.xml\n"
    return robots


@app.get("/sitemap.xml")
def home_portal_sitemap() -> Response:
    content = _read_text_or_missing(_HOME_PORTAL_DIR / "sitemap.xml", fallback="<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"/>")
    return Response(content=_append_directory_sitemap(content), media_type="application/xml")


@app.get("/business-directory-sitemap.xml")
def home_portal_business_directory_sitemap() -> Response:
    return Response(content=_directory_sitemap_xml(), media_type="application/xml")


@app.get("/white/robots.txt", response_class=PlainTextResponse)
def home_portal_white_robots() -> str:
    return _read_text_or_missing(_HOME_PORTAL_WHITE_DIR / "robots.txt", fallback="User-agent: *\nAllow: /\n")


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
