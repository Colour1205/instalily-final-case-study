"""PostgreSQL access for the leads API: read-only queries, run on the replica. SQL only."""

from sqlalchemy import Connection, text

# Each filter is skipped when it is empty (NULL or false), so one query covers every combination.
# Several certifications or product lines mean "any of these".
FILTERS = """
    (CAST(:q AS TEXT) IS NULL OR strpos(lower(c.name), lower(CAST(:q AS TEXT))) > 0)
    AND (CAST(:certifications AS TEXT[]) IS NULL OR c.certification = ANY(CAST(:certifications AS TEXT[])))
    AND (CAST(:services AS TEXT[]) IS NULL OR c.services && CAST(:services AS TEXT[]))
    AND (CAST(:presidents_club AS BOOLEAN) IS NOT TRUE OR c.president_club_stars > 0)
    AND (CAST(:min_rating AS NUMERIC) IS NULL OR c.rating >= :min_rating)
    AND (CAST(:max_distance AS NUMERIC) IS NULL OR c.distance_miles <= :max_distance)
"""

COUNT_LEADS = text(f"SELECT count(*) FROM contractors c WHERE {FILTERS}")

LIST_LEADS = text(f"""
    SELECT c.gaf_id, c.name, c.rating, c.review_count, c.certification, c.president_club_stars,
           c.commercial_certification, c.services, c.distance_miles, c.priority_score, c.logo_url,
           a.gaf_id IS NOT NULL AS has_analysis, a.summary
    FROM contractors c
    LEFT JOIN analyses a ON a.gaf_id = c.gaf_id
    WHERE {FILTERS}
    ORDER BY c.priority_score DESC, c.gaf_id
    LIMIT :limit OFFSET :offset
""")

MAP_POINTS = text(f"""
    SELECT c.gaf_id, c.name, c.latitude, c.longitude, c.priority_score
    FROM contractors c
    WHERE {FILTERS} AND c.latitude IS NOT NULL AND c.longitude IS NOT NULL
    ORDER BY c.priority_score DESC, c.gaf_id
""")

GET_LEAD = text("""
    SELECT c.gaf_id, c.name, c.rating, c.review_count, c.certification, c.president_club_stars,
           c.commercial_certification, c.services, c.distance_miles, c.priority_score, c.logo_url,
           c.phone, c.address, c.profile_url, c.fingerprint, c.updated_at,
           a.gaf_id IS NOT NULL AS has_analysis,
           a.summary, a.why_good_lead, a.pitch, a.talking_points, a.draft_email,
           a.fingerprint AS analysis_fingerprint
    FROM contractors c
    LEFT JOIN analyses a ON a.gaf_id = c.gaf_id
    WHERE c.gaf_id = :gaf_id
""")


class LeadStore:
    """Reads leads for the API. Every method runs on the connection the caller passes in."""

    def count_leads(self, connection: Connection, filters: dict) -> int:
        """How many leads match the filters (for paging)."""
        return connection.execute(COUNT_LEADS, filters).scalar_one()

    def list_leads(self, connection: Connection, filters: dict, limit: int, offset: int) -> list[dict]:
        """One page of leads matching the filters, best priority score first."""
        params = dict(filters)
        params["limit"] = limit
        params["offset"] = offset
        return self.as_dicts(connection.execute(LIST_LEADS, params).mappings().all())

    def map_points(self, connection: Connection, filters: dict) -> list[dict]:
        """Name, position and score of every lead matching the filters (all of them, for the map)."""
        return self.as_dicts(connection.execute(MAP_POINTS, filters).mappings().all())

    def get_lead(self, connection: Connection, gaf_id: str) -> dict | None:
        """One lead with its analysis, or None if the id is unknown."""
        row = connection.execute(GET_LEAD, {"gaf_id": gaf_id}).mappings().first()
        if row is None:
            return None
        return dict(row)

    def as_dicts(self, rows) -> list[dict]:
        """Turn database rows into plain dictionaries."""
        result = []
        for row in rows:
            result.append(dict(row))
        return result
