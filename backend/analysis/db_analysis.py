"""PostgreSQL access for analysis: read a contractor's facts, save its web research and its analysis. SQL only."""

from sqlalchemy import Connection, text

GET_FACTS = text("""
    SELECT gaf_id, name, rating, review_count, certification, president_club_stars,
           commercial_certification, services, address, distance_miles, phone
    FROM contractors WHERE gaf_id = :gaf_id
""")

UNKNOWN_IDS = text("""
    SELECT id FROM unnest(CAST(:ids AS TEXT[])) AS id
    WHERE NOT EXISTS (SELECT 1 FROM contractors WHERE gaf_id = id)
""")

GET_RESEARCH = text("SELECT website, about, people, sources FROM research WHERE gaf_id = :gaf_id")

SAVE_RESEARCH = text("""
    INSERT INTO research (gaf_id, website, about, people, sources)
    VALUES (:gaf_id, :website, :about, :people, :sources)
    ON CONFLICT (gaf_id) DO UPDATE SET
        website = EXCLUDED.website,
        about = EXCLUDED.about,
        people = EXCLUDED.people,
        sources = EXCLUDED.sources,
        researched_at = now()
""")

SAVE_ANALYSIS = text("""
    INSERT INTO analyses (gaf_id, summary, why_good_lead, pitch, talking_points, draft_email, fingerprint)
    VALUES (:gaf_id, :summary, :why_good_lead, :pitch, :talking_points, :draft_email, :fingerprint)
    ON CONFLICT (gaf_id) DO UPDATE SET
        summary = EXCLUDED.summary,
        why_good_lead = EXCLUDED.why_good_lead,
        pitch = EXCLUDED.pitch,
        talking_points = EXCLUDED.talking_points,
        draft_email = EXCLUDED.draft_email,
        fingerprint = EXCLUDED.fingerprint
""")


class AnalysisStore:
    """Reads contractor facts and writes analyses. Every method runs inside the caller's transaction."""

    def get_facts(self, connection: Connection, gaf_id: str) -> dict:
        """Return the facts the AI needs about one contractor."""
        row = connection.execute(GET_FACTS, {"gaf_id": gaf_id}).mappings().one()
        return dict(row)

    def unknown_ids(self, connection: Connection, gaf_ids: list[str]) -> list[str]:
        """The ids in the list that are not in the contractors table."""
        return list(connection.execute(UNKNOWN_IDS, {"ids": gaf_ids}).scalars())

    def get_research(self, connection: Connection, gaf_id: str) -> dict | None:
        """Return a contractor's web research, or None if it was never researched."""
        row = connection.execute(GET_RESEARCH, {"gaf_id": gaf_id}).mappings().first()
        if row is None:
            return None
        return dict(row)

    def save_research(self, connection: Connection, gaf_id: str, research: dict) -> None:
        """Save a contractor's web research, replacing any older one."""
        params = dict(research)
        params["gaf_id"] = gaf_id
        connection.execute(SAVE_RESEARCH, params)

    def save_analysis(self, connection: Connection, gaf_id: str, analysis: dict, fingerprint: str) -> None:
        """Save a contractor's analysis, replacing any older one."""
        params = dict(analysis)
        params["gaf_id"] = gaf_id
        params["fingerprint"] = fingerprint
        connection.execute(SAVE_ANALYSIS, params)
