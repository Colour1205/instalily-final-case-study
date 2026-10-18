"""Answers the leads API: Redis cache first (cache-aside), then the replica database, shaped as JSON."""

import json
from urllib.parse import quote_plus

from leads.cache_leads import LeadCache
from leads.db_access_leads import LeadStore
from shared.config import settings
from shared.db_postgres import replica_engine


# The four score parts as stored in the contractors table (the user's exact names).
SCORE_PARTS = ("review_count_adjust_rating", "gaf_rank", "specialty", "distance")
# Ranking words the API accepts, and the SQL weight each one switches on.
SORT_WEIGHTS = {"rating": "w_rating", "rank": "w_rank", "specialty": "w_specialty", "distance": "w_distance"}


class LeadService:
    """The leads API's read side: uses the cache, opens replica connections and turns rows into JSON."""

    def __init__(self) -> None:
        """Use the leads store for all SQL and the leads cache for Redis."""
        self.store = LeadStore()
        self.cache = LeadCache(settings.lead_cache_seconds)

    def list_leads(self, page: int, limit: int, filters: dict, sort: list[str]) -> dict:
        """One page of leads ranked by the chosen score parts (by the priority score when none are chosen)."""
        sort = sorted(sort)
        key = f"leads:v1:page={page}:limit={limit}:sort={','.join(sort)}:" + self.filters_key(filters)
        weights = self.sort_weights(sort)

        def read_page() -> dict:
            """Read this page from the replica (only one request per key does this at a time)."""
            connection = replica_engine.connect()
            try:
                # One snapshot for both queries, so the total always matches the page.
                connection.execution_options(isolation_level="REPEATABLE READ")
                total = self.store.count_leads(connection, filters)
                rows = self.store.list_leads(connection, filters, weights, limit, (page - 1) * limit)
            finally:
                # Read only, so nothing to commit: close() hands the connection back to the pool.
                connection.close()
            leads = []
            for row in rows:
                leads.append(self.lead_summary(row))
            return {"page": page, "limit": limit, "total": total, "leads": leads}

        return self.cache.get_or_build(key, read_page)

    def map_points(self, filters: dict) -> dict:
        """The search centre and radius, plus every matching lead's position and score, for the map."""
        zip_code = settings.scrape_zip_codes[0]
        latitude, longitude = settings.zip_coordinates[zip_code]

        def read_points() -> dict:
            """Read every matching lead's position from the replica."""
            connection = replica_engine.connect()
            try:
                rows = self.store.map_points(connection, filters)
            finally:
                connection.close()
            points = []
            for row in rows:
                points.append({
                    "gaf_id": row["gaf_id"],
                    "name": row["name"],
                    "lat": row["latitude"],
                    "lng": row["longitude"],
                    "score": self.to_float(row["priority_score"]),
                })
            return {
                "center": {"zip": zip_code, "lat": latitude, "lng": longitude},
                "radius_miles": settings.search_radius_miles,
                "points": points,
            }

        return self.cache.get_or_build("map:v1:" + self.filters_key(filters), read_points)

    def sort_weights(self, sort: list[str]) -> dict:
        """Weight 1 for each chosen score part and 0 for the others; nothing chosen means all four."""
        weights = {}
        for name in SORT_WEIGHTS:
            chosen = not sort or name in sort
            weights[SORT_WEIGHTS[name]] = int(chosen)
        return weights

    def filters_key(self, filters: dict) -> str:
        """The filters written into a cache key as JSON, so two different filter sets can never share an answer."""
        key = dict(filters)
        if key["q"]:
            key["q"] = key["q"].lower()
        key["certifications"] = sorted(key["certifications"] or [])
        key["services"] = sorted(key["services"] or [])
        return json.dumps(key, sort_keys=True)

    def get_lead(self, gaf_id: str) -> dict | None:
        """One lead with contact details, score and analysis, or None if the id is unknown."""

        def read_lead() -> dict | None:
            """Read this lead from the replica (only one request per lead does this at a time)."""
            connection = replica_engine.connect()
            try:
                row = self.store.get_lead(connection, gaf_id)
            finally:
                connection.close()
            if row is None:
                return None
            return self.lead_detail(row)

        return self.cache.get_or_build(f"lead:v1:{gaf_id}", read_lead)

    def lead_summary(self, row: dict) -> dict:
        """The fields shown in the ranked list, with the score total and its four parts."""
        score = {"total": self.to_float(row["priority_score"])}
        for name in SCORE_PARTS:
            score[name] = self.to_float(row[name])
        return {
            "gaf_id": row["gaf_id"],
            "name": row["name"],
            "rating": self.to_float(row["rating"]),
            "review_count": row["review_count"],
            "certification": row["certification"],
            "president_club_stars": row["president_club_stars"],
            "commercial_certification": row["commercial_certification"],
            "services": row["services"],
            "distance_miles": self.to_float(row["distance_miles"]),
            "logo_url": row["logo_url"],
            "summary": row["summary"],
            "score": score,
        }

    def lead_detail(self, row: dict) -> dict:
        """Everything about one lead: the list fields, contact details and the AI analysis."""
        lead = self.lead_summary(row)
        maps_url = None
        if row["address"]:
            maps_url = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(row["address"])
        lead["contact"] = {
            "phone": row["phone"],
            "address": row["address"],
            "maps_url": maps_url,
            "profile_url": row["profile_url"],
        }
        lead["analysis"] = None
        # analyses.summary is NOT NULL, so NULL here means the join found no analysis yet.
        if row["summary"] is not None:
            lead["analysis"] = {
                "summary": row["summary"],
                "why_good_lead": row["why_good_lead"],
                "pitch": row["pitch"],
                "talking_points": row["talking_points"],
                "draft_email": row["draft_email"],
                # False means the facts changed since this analysis was written; a new one is on its way.
                "is_current": row["analysis_fingerprint"] == row["fingerprint"],
            }
        return lead

    def to_float(self, value) -> float | None:
        """PostgreSQL returns NUMERIC columns as Decimal; JSON needs plain numbers."""
        if value is None:
            return None
        return float(value)
