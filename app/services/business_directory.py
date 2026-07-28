from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import json
import re
import ssl
import threading
import time
from collections import OrderedDict
from typing import Any, Optional
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import BusinessDirectoryEntry


_BAD_CITY_VALUES = {"", "ca", "california", "n/a", "na", "none", "null", "-"}
_SPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_CACHE_MAX_ENTRIES = 2048
_CACHE_TTL_SECONDS = 600
_SITEMAP_CACHE_TTL_SECONDS = 3600
_cache_lock = threading.RLock()
_cache: "OrderedDict[tuple[Any, ...], tuple[float, Any]]" = OrderedDict()

_BUSINESS_TYPE_ICON_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("pizza",), "🍕"),
    (("beauty", "salon", "spa", "barber", "cosmetic"), "✂"),
    (("restaurant", "dining", "cafe", "coffee", "bakery", "grill", "food"), "🍽"),
    (("paint", "painting"), "🖌"),
    (("law", "legal", "attorney"), "⚖"),
    (("doctor", "medical", "health", "clinic", "dental", "dentist", "therapy"), "✚"),
    (("real estate", "realtor", "property", "mortgage"), "🏠"),
    (("bank", "financial", "account", "insurance", "tax", "bookkeep"), "$"),
    (("school", "education", "college", "tutor", "training"), "🎓"),
    (("hotel", "lodging", "travel", "tour"), "🛎"),
    (("auto", "car", "vehicle", "parking", "transport"), "🚗"),
    (("construction", "contractor", "plumbing", "electric", "roof", "architect"), "🔧"),
    (("retail", "shop", "store", "boutique", "jewelry", "gift"), "🛍"),
    (("fitness", "gym", "sport", "martial", "yoga"), "★"),
    (("nonprofit", "community", "association", "church", "foundation"), "◎"),
    (("media", "marketing", "advertising", "design", "print", "photo", "video"), "◆"),
    (("technology", "software", "computer", "internet", "telecom"), "⌘"),
    (("government", "city", "public", "municipal"), "●"),
)


@dataclass(frozen=True)
class WebsiteMetadata:
    title: str = ""
    description: str = ""
    image_url: str = ""
    video_url: str = ""
    final_url: str = ""


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self._in_title = False
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() == "title":
            self._in_title = True
            return
        if tag.lower() != "meta":
            return

        attr_map = {str(key).lower(): str(value or "").strip() for key, value in attrs}
        key = attr_map.get("property") or attr_map.get("name") or attr_map.get("itemprop")
        content = attr_map.get("content", "")
        if key and content:
            self.meta[key.lower()] = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            cleaned = normalize_spaces(data)
            if cleaned:
                self.title_parts.append(cleaned)


def _cache_get(key: tuple[Any, ...]) -> Any:
    now = time.monotonic()
    with _cache_lock:
        item = _cache.pop(key, None)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= now:
            return None
        _cache[key] = (expires_at, value)
        return value


def _cache_set(key: tuple[Any, ...], value: Any, *, ttl_seconds: int = _CACHE_TTL_SECONDS) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic() + ttl_seconds, value)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def clear_business_directory_caches() -> None:
    with _cache_lock:
        _cache.clear()


def _clone_facets(facets: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {key: [dict(item) for item in items] for key, items in facets.items()}


def normalize_spaces(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "").replace("\xa0", " ")).strip()


def normalize_city(value: Any) -> str:
    text = normalize_spaces(value)
    if not text or text.lower() in _BAD_CITY_VALUES:
        return ""
    return " ".join(part if part.isupper() and len(part) <= 3 else part.capitalize() for part in text.split())


def slugify(value: Any, *, fallback: str = "entry") -> str:
    text = normalize_spaces(value).lower()
    text = _SLUG_RE.sub("-", text).strip("-")
    return text or fallback


def icon_for_business_type(business_type: Any) -> str:
    text = normalize_spaces(business_type).lower()
    for keywords, icon in _BUSINESS_TYPE_ICON_KEYWORDS:
        if any(_business_type_keyword_matches(text, keyword) for keyword in keywords):
            return icon
    return "•"


def _business_type_keyword_matches(text: str, keyword: str) -> bool:
    if keyword in {"spa", "sport", "gym"}:
        return re.search(rf"(^|[^a-z0-9]){re.escape(keyword)}([^a-z0-9]|$)", text) is not None
    return keyword in text


def pick_search_city(*, requested_city: Any = None, city: Any = None, address: Any = None) -> str:
    requested = normalize_city(requested_city)
    raw_city = normalize_city(city)
    if raw_city:
        return raw_city
    if requested:
        return requested
    return ""


def build_directory_description(record: dict[str, Any], metadata: Optional[WebsiteMetadata] = None) -> str:
    metadata_description = normalize_spaces(metadata.description if metadata else "")
    if metadata_description:
        return metadata_description[:700]

    name = normalize_spaces(record.get("business_name"))
    business_type = normalize_spaces(record.get("business_type"))
    city = pick_search_city(
        requested_city=record.get("requested_city"),
        city=record.get("city"),
        address=record.get("address"),
    )
    address = normalize_spaces(record.get("address"))

    parts = [name]
    if business_type:
        parts.append(f"is listed as {article_for(business_type)} {business_type}")
    else:
        parts.append("is listed in the Perk Nation local business directory")
    if city:
        parts.append(f"serving {city}")
    if address:
        parts.append(f"at {address}")

    sentence = " ".join(parts).strip()
    if not sentence.endswith("."):
        sentence += "."
    return f"{sentence} Contact the business directly for current services, hours, availability, and booking details."


def article_for(value: str) -> str:
    first = normalize_spaces(value)[:1].lower()
    return "an" if first in {"a", "e", "i", "o", "u"} else "a"


def fetch_website_metadata(url: str, *, timeout_seconds: float = 4.0) -> WebsiteMetadata:
    normalized_url = normalize_spaces(url)
    if not normalized_url:
        return WebsiteMetadata()
    if not normalized_url.startswith(("http://", "https://")):
        normalized_url = f"https://{normalized_url}"

    request = Request(
        normalized_url,
        headers={
            "User-Agent": "PerkNationDirectoryBot/1.0 (+https://perknation.app/directory)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    ssl_context = _default_ssl_context()
    with urlopen(request, timeout=timeout_seconds, context=ssl_context) as response:  # noqa: S310 - operator-supplied URLs.
        final_url = str(response.geturl() or normalized_url)
        content_type = str(response.headers.get("content-type") or "").lower()
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return WebsiteMetadata(final_url=final_url)
        raw = response.read(300_000)

    parser = _MetadataParser()
    parser.feed(raw.decode("utf-8", errors="ignore"))
    meta = parser.meta
    title = normalize_spaces(meta.get("og:title") or meta.get("twitter:title") or " ".join(parser.title_parts))
    description = normalize_spaces(
        meta.get("og:description")
        or meta.get("twitter:description")
        or meta.get("description")
    )
    image = normalize_spaces(meta.get("og:image") or meta.get("twitter:image") or meta.get("image"))
    video = normalize_spaces(meta.get("og:video") or meta.get("og:video:url") or meta.get("twitter:player"))
    return WebsiteMetadata(
        title=title[:260],
        description=description[:700],
        image_url=urljoin(final_url, image) if image else "",
        video_url=urljoin(final_url, video) if video else "",
        final_url=final_url,
    )


def _default_ssl_context() -> Optional[ssl.SSLContext]:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def upsert_business_directory_entry(
    db: Session,
    *,
    source_file: str,
    source_sheet: str,
    source_row: int,
    raw_record: dict[str, Any],
    metadata: Optional[WebsiteMetadata] = None,
    dedupe_natural: bool = False,
) -> tuple[BusinessDirectoryEntry, bool]:
    business_name = normalize_spaces(raw_record.get("business_name"))
    if not business_name:
        raise ValueError("business_name is required")

    business_type = normalize_spaces(raw_record.get("business_type")) or None
    requested_city = normalize_spaces(raw_record.get("requested_city")) or None
    raw_city = normalize_spaces(raw_record.get("city")) or None
    search_city = pick_search_city(
        requested_city=requested_city,
        city=raw_city,
        address=raw_record.get("address"),
    ) or None
    business_type_slug = slugify(business_type, fallback="business") if business_type else None
    city_slug = slugify(search_city, fallback="city") if search_city else None
    base_slug = slugify(" ".join(part for part in (business_name, search_city, business_type) if part), fallback="business")

    row = db.scalar(
        select(BusinessDirectoryEntry).where(
            BusinessDirectoryEntry.source_file == source_file,
            BusinessDirectoryEntry.source_sheet == source_sheet,
            BusinessDirectoryEntry.source_row == source_row,
        )
    )
    if dedupe_natural:
        row_name_matches = row is not None and normalize_spaces(row.business_name).lower() == normalize_spaces(business_name).lower()
        if row is None or not row_name_matches:
            natural_row = find_natural_business_directory_duplicate(
                db,
                business_name=business_name,
                raw_record=raw_record,
            )
            if natural_row is not None:
                row = natural_row

    created = row is None
    if row is None:
        row = BusinessDirectoryEntry(
            source_file=source_file,
            source_sheet=source_sheet,
            source_row=source_row,
            slug="",
            business_name=business_name,
            business_name_normalized=normalize_spaces(business_name).lower(),
        )
        db.add(row)
        db.flush()

    row.business_name = business_name
    row.business_name_normalized = normalize_spaces(business_name).lower()
    row.business_type = business_type
    row.business_type_slug = business_type_slug
    row.business_type_icon = icon_for_business_type(business_type)
    row.requested_city = requested_city
    row.search_city = search_city
    row.search_city_slug = city_slug
    row.city = raw_city
    row.state = normalize_spaces(raw_record.get("state")) or None
    row.zip_code = normalize_spaces(raw_record.get("zip_code")) or None
    row.address = normalize_spaces(raw_record.get("address")) or None
    row.phone_number = normalize_spaces(raw_record.get("phone_number")) or None
    row.fax = normalize_spaces(raw_record.get("fax")) or None
    row.contact_person = normalize_spaces(raw_record.get("contact_person")) or None
    row.email = normalize_spaces(raw_record.get("email")) or None
    row.website = normalize_spaces(raw_record.get("website")) or None
    row.source_month_page = normalize_spaces(raw_record.get("source_month_page")) or None
    row.pdf_page = normalize_spaces(raw_record.get("pdf_page")) or None
    row.printed_page = normalize_spaces(raw_record.get("printed_page")) or None
    row.data_source = normalize_spaces(raw_record.get("data_source")) or None
    row.source_url = normalize_spaces(raw_record.get("source_url")) or None
    row.city_match = normalize_spaces(raw_record.get("city_match")) or None
    row.coverage_notes = normalize_spaces(raw_record.get("coverage_notes")) or None
    row.notes = normalize_spaces(raw_record.get("notes")) or None
    row.description = build_directory_description(raw_record, metadata=metadata)
    row.seo_title = build_seo_title(business_name=business_name, business_type=business_type, city=search_city)
    row.seo_description = build_seo_description(row.description)
    row.image_url = normalize_spaces(metadata.image_url if metadata else "") or None
    row.video_url = normalize_spaces(metadata.video_url if metadata else "") or None
    row.enrichment_source_url = normalize_spaces(metadata.final_url if metadata else "") or None
    row.raw_json = json.dumps(raw_record, ensure_ascii=False, sort_keys=True)
    row.is_active = True
    row.slug = ensure_unique_business_slug(db, base_slug=base_slug, existing_id=row.id)
    clear_business_directory_caches()
    return row, created


def find_natural_business_directory_duplicate(
    db: Session,
    *,
    business_name: str,
    raw_record: dict[str, Any],
) -> Optional[BusinessDirectoryEntry]:
    name_norm = normalize_spaces(business_name).lower()
    if not name_norm:
        return None

    city_norm = normalize_city(raw_record.get("city") or raw_record.get("requested_city")).lower()
    address_key = _address_key(raw_record.get("address"))
    phone_digits = _digits_only(raw_record.get("phone_number"))
    website_key = _website_key(raw_record.get("website"))
    type_norm = normalize_spaces(raw_record.get("business_type")).lower()

    candidates = list(
        db.scalars(
            select(BusinessDirectoryEntry)
            .where(
                BusinessDirectoryEntry.is_active.is_(True),
                func.lower(BusinessDirectoryEntry.business_name) == name_norm,
            )
            .limit(80)
        )
    )
    if not candidates:
        return None

    scored: list[tuple[int, BusinessDirectoryEntry]] = []
    for candidate in candidates:
        score = 0
        candidate_city = normalize_city(candidate.city or candidate.search_city or candidate.requested_city).lower()
        candidate_address = _address_key(candidate.address)
        candidate_phone = _digits_only(candidate.phone_number)
        candidate_website = _website_key(candidate.website)
        candidate_type = normalize_spaces(candidate.business_type).lower()

        if phone_digits and candidate_phone and phone_digits == candidate_phone:
            score += 12
        if address_key and candidate_address and address_key == candidate_address:
            score += 10
        if website_key and candidate_website and website_key == candidate_website:
            score += 8
        if city_norm and candidate_city and city_norm == candidate_city:
            score += 6
        if type_norm and candidate_type and type_norm == candidate_type:
            score += 3

        if score >= 8 or (score >= 6 and (phone_digits or address_key or website_key or type_norm)):
            scored.append((score, candidate))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _digits_only(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _address_key(value: Any) -> str:
    text = normalize_spaces(value).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _website_key(value: Any) -> str:
    text = normalize_spaces(value).lower()
    if not text:
        return ""
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    return text.rstrip("/")


def build_seo_title(*, business_name: str, business_type: Optional[str], city: Optional[str]) -> str:
    pieces = [business_name]
    if business_type:
        pieces.append(str(business_type))
    if city:
        pieces.append(str(city))
    pieces.append("Perk Nation Directory")
    return " | ".join(normalize_spaces(piece) for piece in pieces if normalize_spaces(piece))[:260]


def build_seo_description(description: Optional[str]) -> str:
    cleaned = normalize_spaces(description)
    if len(cleaned) <= 300:
        return cleaned
    return cleaned[:297].rstrip(" ,.;") + "..."


def ensure_unique_business_slug(db: Session, *, base_slug: str, existing_id: Optional[int] = None) -> str:
    base = base_slug[:200].strip("-") or "business"
    candidate = base
    suffix = 2
    while True:
        row_id = db.scalar(select(BusinessDirectoryEntry.id).where(BusinessDirectoryEntry.slug == candidate))
        if row_id is None or (existing_id is not None and int(row_id) == int(existing_id)):
            return candidate
        tail = f"-{suffix}"
        candidate = f"{base[: 220 - len(tail)]}{tail}"
        suffix += 1


def search_business_directory(
    db: Session,
    *,
    query: str = "",
    city: Optional[str] = None,
    city_slug: Optional[str] = None,
    business_type: Optional[str] = None,
    business_type_slug: Optional[str] = None,
    limit: int = 24,
    offset: int = 0,
) -> tuple[list[BusinessDirectoryEntry], int]:
    filters = build_business_directory_filters(
        query=query,
        city=city,
        city_slug=city_slug,
        business_type=business_type,
        business_type_slug=business_type_slug,
    )
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    cache_key = (
        "search",
        normalize_spaces(query).lower(),
        normalize_city(city).lower(),
        slugify(city_slug, fallback="city") if city_slug else "",
        normalize_spaces(business_type).lower(),
        slugify(business_type_slug, fallback="business") if business_type_slug else "",
        limit,
        offset,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        cached_rows, cached_count = cached
        return list(cached_rows), int(cached_count)

    count = int(db.scalar(select(func.count()).select_from(BusinessDirectoryEntry).where(*filters)) or 0)
    rows = list(
        db.scalars(
            select(BusinessDirectoryEntry)
            .where(*filters)
            .order_by(
                desc(BusinessDirectoryEntry.search_city == "Pasadena"),
                BusinessDirectoryEntry.search_city.asc(),
                BusinessDirectoryEntry.business_name.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )
    _cache_set(cache_key, (tuple(rows), count))
    return rows, count


def build_business_directory_filters(
    *,
    query: str = "",
    city: Optional[str] = None,
    city_slug: Optional[str] = None,
    business_type: Optional[str] = None,
    business_type_slug: Optional[str] = None,
) -> list[Any]:
    filters: list[Any] = [BusinessDirectoryEntry.is_active.is_(True)]

    query_text = normalize_spaces(query).lower()
    if query_text:
        like_value = f"%{query_text}%"
        filters.append(
            or_(
                func.lower(BusinessDirectoryEntry.business_name).like(like_value),
                func.lower(BusinessDirectoryEntry.business_type).like(like_value),
                func.lower(BusinessDirectoryEntry.description).like(like_value),
                func.lower(BusinessDirectoryEntry.address).like(like_value),
                func.lower(BusinessDirectoryEntry.contact_person).like(like_value),
            )
        )

    city_label = normalize_city(city)
    if city_label:
        filters.append(func.lower(BusinessDirectoryEntry.search_city) == city_label.lower())
    elif city_slug:
        filters.append(BusinessDirectoryEntry.search_city_slug == slugify(city_slug, fallback="city"))

    type_label = normalize_spaces(business_type)
    if type_label:
        filters.append(func.lower(BusinessDirectoryEntry.business_type) == type_label.lower())
    elif business_type_slug:
        filters.append(BusinessDirectoryEntry.business_type_slug == slugify(business_type_slug, fallback="business"))

    return filters


def directory_facets(db: Session, *, limit_types: int = 120, limit_cities: int = 200) -> dict[str, list[dict[str, Any]]]:
    limit_types = max(1, min(int(limit_types), 500))
    limit_cities = max(1, min(int(limit_cities), 500))
    cache_key = ("facets", limit_types, limit_cities)
    cached = _cache_get(cache_key)
    if cached is not None:
        return _clone_facets(cached)

    city_rows = db.execute(
        select(BusinessDirectoryEntry.search_city, BusinessDirectoryEntry.search_city_slug, func.count())
        .where(
            BusinessDirectoryEntry.is_active.is_(True),
            BusinessDirectoryEntry.search_city.is_not(None),
            BusinessDirectoryEntry.search_city != "",
        )
        .group_by(BusinessDirectoryEntry.search_city, BusinessDirectoryEntry.search_city_slug)
        .order_by(desc(func.count()), BusinessDirectoryEntry.search_city.asc())
        .limit(limit_cities)
    ).all()
    type_rows = db.execute(
        select(
            BusinessDirectoryEntry.business_type,
            BusinessDirectoryEntry.business_type_slug,
            BusinessDirectoryEntry.business_type_icon,
            func.count(),
        )
        .where(
            BusinessDirectoryEntry.is_active.is_(True),
            BusinessDirectoryEntry.business_type.is_not(None),
            BusinessDirectoryEntry.business_type != "",
        )
        .group_by(
            BusinessDirectoryEntry.business_type,
            BusinessDirectoryEntry.business_type_slug,
            BusinessDirectoryEntry.business_type_icon,
        )
        .order_by(desc(func.count()), BusinessDirectoryEntry.business_type.asc())
        .limit(limit_types)
    ).all()

    facets = {
        "cities": [
            {"label": label, "slug": slug, "count": int(count)}
            for label, slug, count in city_rows
            if label and slug
        ],
        "business_types": [
            {"label": label, "slug": slug, "icon": icon or "•", "count": int(count)}
            for label, slug, icon, count in type_rows
            if label and slug
        ],
    }
    _cache_set(cache_key, _clone_facets(facets))
    return facets


def get_business_directory_entry(db: Session, slug: str) -> Optional[BusinessDirectoryEntry]:
    normalized_slug = slugify(slug, fallback="")
    cache_key = ("entry", normalized_slug)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    row = db.scalar(
        select(BusinessDirectoryEntry).where(
            BusinessDirectoryEntry.slug == normalized_slug,
            BusinessDirectoryEntry.is_active.is_(True),
        )
    )
    if row is not None:
        _cache_set(cache_key, row)
    return row


def directory_sitemap_entries(db: Session, *, limit: int = 5000) -> list[str]:
    limit = max(1, min(int(limit), 10_000))
    cache_key = ("sitemap", limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        return list(cached)
    rows = db.scalars(
        select(BusinessDirectoryEntry.slug)
        .where(BusinessDirectoryEntry.is_active.is_(True))
        .order_by(BusinessDirectoryEntry.slug.asc())
        .limit(limit)
    )
    slugs = [str(slug) for slug in rows if slug]
    _cache_set(cache_key, tuple(slugs), ttl_seconds=_SITEMAP_CACHE_TTL_SECONDS)
    return slugs
