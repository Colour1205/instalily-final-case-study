"""PostgreSQL access for analysis: read a contractor's facts and save its analysis. SQL only."""

from sqlalchemy import Connection, text

GET_FACTS = text("""
    SELECT name, rating, review_count, certification, president_club_stars,
           commercial_certification, services, address, distance_miles
    FROM contractors WHERE gaf_id = :gaf_id
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

    def save_analysis(self, connection: Connection, gaf_id: str, analysis: dict, fingerprint: str) -> None:
        """Save a contractor's analysis, replacing any older one."""
        params = dict(analysis)
        params["gaf_id"] = gaf_id
        params["fingerprint"] = fingerprint
        connection.execute(SAVE_ANALYSIS, params)
