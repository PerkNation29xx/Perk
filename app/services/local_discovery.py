from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import math
from typing import Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.models import (
    Offer,
    OfferActivation,
    OfferStatus,
    RestaurantKnowledge,
    RestaurantReview,
)
from app.services.la_restaurant_knowledge import search_restaurants
from app.services.restaurant_vector_rag import RestaurantSemanticMatch, semantic_search_restaurants


_LOCAL_DISCOVERY_KEYWORDS = {
    "local",
    "nearby",
    "near me",
    "close by",
    "things to do",
    "where should i go",
    "where should i eat",
    "where to eat",
    "what should i do",
    "what to do",
    "restaurant",
    "restaurants",
    "food",
    "dining",
    "brunch",
    "dinner",
    "lunch",
    "date night",
    "activity",
    "activities",
    "fun",
    "pasadena",
    "los angeles",
    "hollywood",
    "santa monica",
    "culver city",
    "beverly hills",
    "west hollywood",
}

_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "for",
    "to",
    "with",
    "near",
    "in",
    "on",
    "at",
    "of",
    "that",
    "this",
    "what",
    "where",
    "should",
    "could",
    "would",
    "please",
    "show",
    "find",
    "give",
    "best",
    "good",
    "great",
    "top",
    "me",
    "my",
    "is",
    "are",
    "do",
    "tonight",
    "today",
    "around",
    "around me",
}


@dataclass(frozen=True)
class _DiscoveryCandidate:
    source: str
    title: str
    subtitle: str
    details: str
    score: float
    distance_miles: Optional[float]


def is_local_discovery_query(message: str) -> bool:
    text = _normalize(message)
    if not text:
        return False
    if any(keyword in text for keyword in _LOCAL_DISCOVERY_KEYWORDS):
        return True

    # Broad fallback: short discovery-like prompts should still trigger retrieval.
    return text.endswith("?") and any(token in text for token in ("eat", "go", "do", "near"))


def build_local_discovery_context(
    db: Session,
    *,
    message: str,
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
    limit: int = 12,
) -> str:
    if not is_local_discovery_query(message):
        return ""

    now_utc = datetime.now(timezone.utc)
    limit = max(4, min(int(limit), 20))
    tokens = _tokenize(message)

    offer_candidates = _offer_discovery_candidates(
        db,
        message=message,
        tokens=tokens,
        now_utc=now_utc,
        user_latitude=user_latitude,
        user_longitude=user_longitude,
        limit=max(limit, 12),
    )

    restaurant_rows = search_restaurants(
        db,
        query=message,
        limit=max(limit, 12),
    )
    try:
        semantic_matches = semantic_search_restaurants(
            db,
            query=message,
            limit=max(limit, 12),
        )
    except Exception:
        semantic_matches = []
    merged_restaurants, semantic_similarity_by_id = _merge_restaurant_candidates(
        lexical_rows=restaurant_rows,
        semantic_rows=semantic_matches,
        limit=max(limit, 16),
    )
    restaurant_candidates = _restaurant_discovery_candidates(
        merged_restaurants,
        message=message,
        tokens=tokens,
        user_latitude=user_latitude,
        user_longitude=user_longitude,
        semantic_similarity_by_id=semantic_similarity_by_id,
        limit=max(limit, 12),
    )

    merged = sorted(
        offer_candidates + restaurant_candidates,
        key=lambda item: item.score,
        reverse=True,
    )[:limit]

    if not merged:
        return ""

    lines: list[str] = [
        "LOCAL DISCOVERY CONTEXT",
        f"query: {message.strip()}",
    ]
    if user_latitude is not None and user_longitude is not None:
        lines.append(f"user_location: lat={user_latitude:.6f}, lon={user_longitude:.6f}")
    else:
        lines.append("user_location: unavailable")
    lines.append(f"ranked_matches: {len(merged)}")

    for candidate in merged:
        distance_text = ""
        if candidate.distance_miles is not None:
            distance_text = f"; distance_miles={candidate.distance_miles:.2f}"

        lines.append(
            f"- source={candidate.source}; title={candidate.title}; "
            f"subtitle={candidate.subtitle}; {candidate.details}{distance_text}"
        )

    lines.append(
        "Use these ranked local matches when answering discovery questions. "
        "Lead with the top 3 and ask one follow-up preference question "
        "(neighborhood, budget, cuisine/category, or vibe)."
    )
    return "\n".join(lines)


def _offer_discovery_candidates(
    db: Session,
    *,
    message: str,
    tokens: list[str],
    now_utc: datetime,
    user_latitude: Optional[float],
    user_longitude: Optional[float],
    limit: int,
) -> list[_DiscoveryCandidate]:
    offers = db.scalars(
        select(Offer)
        .options(selectinload(Offer.merchant), selectinload(Offer.location))
        .where(
            and_(
                Offer.approval_status == OfferStatus.approved,
                Offer.starts_at <= now_utc,
                Offer.ends_at >= now_utc,
            )
        )
        .order_by(desc(Offer.created_at), desc(Offer.id))
        .limit(300)
    ).all()
    if not offers:
        return []

    offer_ids = [offer.id for offer in offers]
    activation_rows = db.execute(
        select(OfferActivation.offer_id, func.count(OfferActivation.id))
        .where(OfferActivation.offer_id.in_(offer_ids))
        .group_by(OfferActivation.offer_id)
    ).all()
    activation_counts = {int(offer_id): int(count) for offer_id, count in activation_rows}

    merchant_ids = {offer.merchant_id for offer in offers}
    review_rows = db.execute(
        select(
            RestaurantReview.merchant_id,
            func.coalesce(func.avg(RestaurantReview.overall_hearts), 0.0),
            func.count(RestaurantReview.id),
        )
        .where(RestaurantReview.merchant_id.in_(merchant_ids))
        .group_by(RestaurantReview.merchant_id)
    ).all()
    review_stats = {
        int(merchant_id): (float(avg_hearts or 0.0), int(review_count or 0))
        for merchant_id, avg_hearts, review_count in review_rows
    }

    area_acceptance = _compute_area_acceptance(offers, activation_counts)

    items: list[_DiscoveryCandidate] = []
    normalized_message = _normalize(message)
    for offer in offers:
        merchant_name = offer.merchant_name or f"Merchant #{offer.merchant_id}"
        category = ""
        try:
            category = str(offer.merchant.category or "").strip()
        except Exception:
            category = ""

        location_name = ""
        location_address = ""
        lat = None
        lon = None
        if offer.location is not None:
            location_name = str(offer.location.name or "").strip()
            location_address = str(offer.location.address or "").strip()
            try:
                lat = float(offer.location.latitude)
                lon = float(offer.location.longitude)
            except Exception:
                lat = None
                lon = None

        text_score = 0.0
        title_norm = _normalize(offer.title)
        merchant_norm = _normalize(merchant_name)
        category_norm = _normalize(category)
        location_norm = _normalize(f"{location_name} {location_address}")
        terms_norm = _normalize(offer.terms_text)

        if merchant_norm and merchant_norm in normalized_message:
            text_score += 7.0
        if title_norm and title_norm in normalized_message:
            text_score += 8.0
        if category_norm and category_norm in normalized_message:
            text_score += 5.0

        for token in tokens:
            if token in merchant_norm:
                text_score += 4.0
            elif token in title_norm:
                text_score += 4.0
            elif token in category_norm:
                text_score += 3.0
            elif token in location_norm:
                text_score += 2.0
            elif token in terms_norm:
                text_score += 1.5

        if text_score == 0.0:
            text_score = 0.8

        direct_accepts = activation_counts.get(offer.id, 0)
        cluster_accepts = area_acceptance.get(offer.id, direct_accepts)
        popularity_score = (math.log1p(direct_accepts) * 1.1) + (math.log1p(cluster_accepts) * 0.9)

        avg_hearts, review_count = review_stats.get(offer.merchant_id, (0.0, 0))
        review_score = avg_hearts * 0.15 + min(review_count, 60) * 0.01

        distance_miles = None
        proximity_score = 0.0
        if (
            user_latitude is not None
            and user_longitude is not None
            and lat is not None
            and lon is not None
        ):
            distance_miles = _haversine_miles(user_latitude, user_longitude, lat, lon)
            proximity_score = max(0.0, 1.0 - min(distance_miles / 15.0, 1.0)) * 2.8

        score = (text_score * 1.45) + popularity_score + review_score + proximity_score

        boost_text = f"{float(offer.reward_rate_cash) * 100:.1f}% cash / {float(offer.reward_rate_stock) * 100:.1f}% stock"
        subtitle_parts = [part for part in [merchant_name, category or None, location_name or None] if part]
        subtitle = " | ".join(subtitle_parts[:3]) if subtitle_parts else merchant_name
        details = f"offer='{offer.title}'; boost='{boost_text}'; activations={direct_accepts}; area_activations={cluster_accepts}"
        items.append(
            _DiscoveryCandidate(
                source="offer",
                title=offer.title,
                subtitle=subtitle,
                details=details,
                score=score,
                distance_miles=distance_miles,
            )
        )

    items.sort(key=lambda item: item.score, reverse=True)
    return items[:limit]


def _restaurant_discovery_candidates(
    rows: list[RestaurantKnowledge],
    *,
    message: str,
    tokens: list[str],
    user_latitude: Optional[float],
    user_longitude: Optional[float],
    semantic_similarity_by_id: Optional[dict[int, float]],
    limit: int,
) -> list[_DiscoveryCandidate]:
    if not rows:
        return []

    normalized_message = _normalize(message)
    items: list[_DiscoveryCandidate] = []
    for row in rows:
        name_norm = _normalize(row.name)
        cuisine_norm = _normalize(row.cuisine)
        neighborhood_norm = _normalize(row.neighborhood or "")
        city_norm = _normalize(row.city)
        summary_norm = _normalize(row.summary)
        highlight_norm = _normalize(row.highlights or "")

        text_score = 0.0
        if name_norm and name_norm in normalized_message:
            text_score += 8.0
        if cuisine_norm and cuisine_norm in normalized_message:
            text_score += 5.0
        if neighborhood_norm and neighborhood_norm in normalized_message:
            text_score += 4.0
        if city_norm and city_norm in normalized_message:
            text_score += 3.0

        for token in tokens:
            if token in name_norm:
                text_score += 4.0
            elif token in cuisine_norm:
                text_score += 3.5
            elif token in neighborhood_norm:
                text_score += 3.0
            elif token in summary_norm or token in highlight_norm:
                text_score += 1.25

        if text_score == 0.0:
            text_score = 0.7

        distance_miles = None
        proximity_score = 0.0
        lat = _to_float(row.latitude)
        lon = _to_float(row.longitude)
        if (
            user_latitude is not None
            and user_longitude is not None
            and lat is not None
            and lon is not None
        ):
            distance_miles = _haversine_miles(user_latitude, user_longitude, lat, lon)
            proximity_score = max(0.0, 1.0 - min(distance_miles / 18.0, 1.0)) * 2.4

        semantic_similarity = 0.0
        semantic_score = 0.0
        if semantic_similarity_by_id:
            semantic_similarity = max(0.0, float(semantic_similarity_by_id.get(row.id, 0.0)))
            if semantic_similarity >= max(0.0, float(settings.rag_semantic_min_similarity)):
                semantic_score = semantic_similarity * max(0.0, float(settings.rag_semantic_weight))

        score = (text_score * 1.35) + proximity_score + semantic_score
        subtitle = " | ".join(part for part in [row.cuisine, row.neighborhood, row.city] if part)
        details = (
            f"price='{row.price_tier or 'n/a'}'; summary='{row.summary}'; "
            f"semantic_similarity={semantic_similarity:.3f}"
        )
        items.append(
            _DiscoveryCandidate(
                source="restaurant_knowledge",
                title=row.name,
                subtitle=subtitle,
                details=details,
                score=score,
                distance_miles=distance_miles,
            )
        )

    items.sort(key=lambda item: item.score, reverse=True)
    return items[:limit]


def _merge_restaurant_candidates(
    *,
    lexical_rows: list[RestaurantKnowledge],
    semantic_rows: list[RestaurantSemanticMatch],
    limit: int,
) -> tuple[list[RestaurantKnowledge], dict[int, float]]:
    merged: list[RestaurantKnowledge] = []
    seen_ids: set[int] = set()
    semantic_similarity_by_id: dict[int, float] = {}

    for match in semantic_rows:
        restaurant = match.restaurant
        rid = int(getattr(restaurant, "id", 0) or 0)
        if rid <= 0:
            continue
        similarity = float(match.similarity or 0.0)
        semantic_similarity_by_id[rid] = max(semantic_similarity_by_id.get(rid, 0.0), similarity)
        if rid in seen_ids:
            continue
        merged.append(restaurant)
        seen_ids.add(rid)

    for row in lexical_rows:
        rid = int(row.id)
        if rid in seen_ids:
            continue
        merged.append(row)
        seen_ids.add(rid)

    max_rows = max(1, min(limit, 50))
    return merged[:max_rows], semantic_similarity_by_id


def _compute_area_acceptance(offers: list[Offer], activation_counts: dict[int, int]) -> dict[int, int]:
    coords_by_offer: dict[int, tuple[float | None, float | None]] = {}
    for offer in offers:
        lat = None
        lon = None
        if offer.location is not None:
            lat = _to_float(offer.location.latitude)
            lon = _to_float(offer.location.longitude)
        coords_by_offer[offer.id] = (lat, lon)

    out: dict[int, int] = {}
    cluster_radius_miles = 2.0
    for offer in offers:
        offer_lat, offer_lon = coords_by_offer.get(offer.id, (None, None))
        count = 0
        for other in offers:
            other_accepts = activation_counts.get(other.id, 0)
            if other_accepts <= 0:
                continue
            other_lat, other_lon = coords_by_offer.get(other.id, (None, None))
            if (
                offer_lat is not None
                and offer_lon is not None
                and other_lat is not None
                and other_lon is not None
            ):
                if _haversine_miles(offer_lat, offer_lon, other_lat, other_lon) <= cluster_radius_miles:
                    count += other_accepts
            elif offer.location_id is not None and offer.location_id == other.location_id:
                count += other_accepts
        out[offer.id] = count
    return out


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_miles = 3958.7613
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2) + math.cos(p1) * math.cos(p2) * (math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(1 - a, 0.0)))
    return r_miles * c


def _tokenize(text: str) -> list[str]:
    normalized = _normalize(text)
    if not normalized:
        return []
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in normalized)
    tokens = [token for token in cleaned.split() if len(token) > 1 and token not in _STOPWORDS]
    return tokens[:24]


def _normalize(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _to_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
