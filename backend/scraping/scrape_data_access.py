"""PostgreSQL access for scraping: the scrape_runs log and the contractors table. SQL only."""

from sqlalchemy import Connection, text

UPSERT_CONTRACTOR = text("""
    INSERT INTO contractors (
        gaf_id, name, rating, review_count, certification, president_club_stars, commercial_certification,
        services, phone, address, distance_miles, latitude, longitude, profile_url, logo_url, fingerprint, priority_score,
        review_count_adjust_rating, gaf_rank, specialty, distance
    ) VALUES (
        :gaf_id, :name, :rating, :review_count, :certification, :president_club_stars, :commercial_certification,
        :services, :phone, :address, :distance_miles, :latitude, :longitude, :profile_url, :logo_url, :fingerprint,
        :priority_score, :review_count_adjust_rating, :gaf_rank, :specialty, :distance
    )
    ON CONFLICT (gaf_id) DO UPDATE SET
        name = EXCLUDED.name,
        rating = EXCLUDED.rating,
        review_count = EXCLUDED.review_count,
        certification = EXCLUDED.certification,
        president_club_stars = EXCLUDED.president_club_stars,
        commercial_certification = EXCLUDED.commercial_certification,
        services = EXCLUDED.services,
        phone = EXCLUDED.phone,
        address = EXCLUDED.address,
        distance_miles = EXCLUDED.distance_miles,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        profile_url = EXCLUDED.profile_url,
        logo_url = EXCLUDED.logo_url,
        fingerprint = EXCLUDED.fingerprint,
        priority_score = EXCLUDED.priority_score,
        review_count_adjust_rating = EXCLUDED.review_count_adjust_rating,
        gaf_rank = EXCLUDED.gaf_rank,
        specialty = EXCLUDED.specialty,
        distance = EXCLUDED.distance,
        updated_at = now()
""")

# Adds a 'running' row only if this ZIP has no running scrape (unique index) and no recent finished one.
INSERT_RUN = text("""
    INSERT INTO scrape_runs (zip_code, status)
    SELECT :zip, 'running'
    WHERE NOT EXISTS (
        SELECT 1 FROM scrape_runs
        WHERE zip_code = :zip AND status = 'done' AND started_at > now() - make_interval(hours => :hours)
    )
    ON CONFLICT DO NOTHING
    RETURNING id
""")


class ScrapeDataAccess:
    """Reads and writes scrape_runs and contractors. Every method runs inside the caller's transaction."""

    def __init__(self, stuck_minutes: int) -> None:
        """Set when a 'running' scrape counts as stuck (left behind by a crash)."""
        self.stuck_minutes = stuck_minutes

    def insert_run(self, connection: Connection, zip_code: str, min_hours_between_scrapes: int) -> int | None:
        """Expire this ZIP's stuck runs, then log a new running scrape and return its id (None if one is running or finished recently)."""
        # A run left as 'running' by a crash would block every future scrape, so expire it.
        connection.execute(
            text(
                "UPDATE scrape_runs SET status = 'failed' "
                "WHERE zip_code = :zip AND status = 'running' "
                "AND started_at < now() - make_interval(mins => :minutes)"
            ),
            {"zip": zip_code, "minutes": self.stuck_minutes},
        )
        return connection.execute(INSERT_RUN, {"zip": zip_code, "hours": min_hours_between_scrapes}).scalar()

    def mark_run_finished(self, connection: Connection, run_id: int, status: str) -> None:
        """Mark a still-running scrape as done or failed."""
        connection.execute(
            text("UPDATE scrape_runs SET status = :status WHERE id = :id AND status = 'running'"),
            {"status": status, "id": run_id},
        )

    def save_contractor(self, connection: Connection, contractor: dict) -> None:
        """Insert a contractor, or update it if GAF's id is already saved."""
        connection.execute(UPSERT_CONTRACTOR, contractor)
