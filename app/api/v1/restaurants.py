from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas import RestaurantKnowledgeOut, RestaurantKnowledgeSearchResponse
from app.services.la_restaurant_knowledge import search_restaurants

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("/search", response_model=RestaurantKnowledgeSearchResponse)
def search_la_restaurants(
    q: str = Query(default="", max_length=200),
    city: Optional[str] = Query(default=None, max_length=80),
    neighborhood: Optional[str] = Query(default=None, max_length=120),
    cuisine: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
) -> RestaurantKnowledgeSearchResponse:
    query = (q or "").strip()
    query_for_search = query or "best restaurants in los angeles"

    rows = search_restaurants(
        db,
        query=query_for_search,
        city_hint=city,
        neighborhood_hint=neighborhood,
        cuisine_hint=cuisine,
        limit=limit,
    )

    return RestaurantKnowledgeSearchResponse(
        query=query,
        count=len(rows),
        results=[RestaurantKnowledgeOut.model_validate(row) for row in rows],
    )
