from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas import (
    BusinessDirectoryEntryOut,
    BusinessDirectoryFacetOut,
    BusinessDirectoryFacetsResponse,
    BusinessDirectorySearchResponse,
)
from app.services.business_directory import (
    directory_facets,
    get_business_directory_entry,
    search_business_directory,
)

router = APIRouter(prefix="/business-directory", tags=["business-directory"])


def _facets_response(db: Session) -> BusinessDirectoryFacetsResponse:
    facets = directory_facets(db)
    return BusinessDirectoryFacetsResponse(
        cities=[BusinessDirectoryFacetOut(**item) for item in facets["cities"]],
        business_types=[BusinessDirectoryFacetOut(**item) for item in facets["business_types"]],
    )


@router.get("/facets", response_model=BusinessDirectoryFacetsResponse)
def get_business_directory_facets(db: Session = Depends(get_db)) -> BusinessDirectoryFacetsResponse:
    return _facets_response(db)


@router.get("/search", response_model=BusinessDirectorySearchResponse)
def search_business_directory_entries(
    q: str = Query(default="", max_length=200),
    city: Optional[str] = Query(default=None, max_length=100),
    city_slug: Optional[str] = Query(default=None, max_length=120),
    business_type: Optional[str] = Query(default=None, max_length=180),
    business_type_slug: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> BusinessDirectorySearchResponse:
    query = (q or "").strip()
    rows, total = search_business_directory(
        db,
        query=query,
        city=city,
        city_slug=city_slug,
        business_type=business_type,
        business_type_slug=business_type_slug,
        limit=limit,
        offset=offset,
    )
    return BusinessDirectorySearchResponse(
        query=query,
        count=total,
        limit=limit,
        offset=offset,
        results=[BusinessDirectoryEntryOut.model_validate(row) for row in rows],
        facets=_facets_response(db),
    )


@router.get("/{business_slug}", response_model=BusinessDirectoryEntryOut)
def get_business_directory_business(
    business_slug: str,
    db: Session = Depends(get_db),
) -> BusinessDirectoryEntryOut:
    row = get_business_directory_entry(db, business_slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Business not found")
    return BusinessDirectoryEntryOut.model_validate(row)

