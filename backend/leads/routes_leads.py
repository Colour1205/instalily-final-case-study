"""The leads API's web addresses (version 1). Each returns plain JSON."""

from fastapi import APIRouter, Depends, HTTPException, Query

from leads.service_leads import LeadService

router = APIRouter(prefix="/v1")
lead_service = LeadService()


def non_empty(values: list[str] | None) -> list[str] | None:
    """Drop blank values from a repeated query parameter; None if nothing is left."""
    if not values:
        return None
    kept = []
    for value in values:
        if value.strip():
            kept.append(value)
    if not kept:
        return None
    return kept


# Query(...) sets each value's default and allowed range; FastAPI rejects anything outside it.
def lead_filters(
    q: str | None = Query(None, min_length=1),
    certification: list[str] | None = Query(None),
    service: list[str] | None = Query(None),
    presidents_club: bool = False,
    min_rating: float | None = Query(None, ge=0, le=5),
    max_distance: float | None = Query(None, gt=0),
) -> dict:
    """The optional filters shared by the list and the map. Repeat certification or service to pick several."""
    return {
        "q": q,
        "certifications": non_empty(certification),
        "services": non_empty(service),
        "presidents_club": presidents_club,
        "min_rating": min_rating,
        "max_distance": max_distance,
    }


# Depends(lead_filters) makes FastAPI read the filters above for each route that uses them.
@router.get("/leads")
def list_leads(
    page: int = Query(1, ge=1, le=10000),
    limit: int = Query(20, ge=1, le=100),
    filters: dict = Depends(lead_filters),
) -> dict:
    """One page of leads ranked by priority score. All filters are optional."""
    return lead_service.list_leads(page, limit, filters)


@router.get("/map")
def map_points(filters: dict = Depends(lead_filters)) -> dict:
    """The search area and every matching lead's position, for the map."""
    return lead_service.map_points(filters)


@router.get("/leads/{gaf_id}")
def get_lead(gaf_id: str) -> dict:
    """One lead with contact details, the score breakdown and the AI analysis."""
    lead = lead_service.get_lead(gaf_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead
