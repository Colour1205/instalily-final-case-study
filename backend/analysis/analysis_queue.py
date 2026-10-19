"""The analysis queue: one job row per contractor in analysis_jobs. Safe for many servers to use at once. SQL only."""

from sqlalchemy import Connection, text

# Queue the contractor unless its analysis already matches these facts or its job is already open.
UPSERT_JOB = text("""
    INSERT INTO analysis_jobs (gaf_id)
    SELECT :gaf_id
    WHERE NOT EXISTS (SELECT 1 FROM analyses WHERE gaf_id = :gaf_id AND fingerprint = :fingerprint)
    ON CONFLICT (gaf_id) DO UPDATE
        SET status = 'pending', attempts = 0, error = NULL, delay = INTERVAL '0 seconds', updated_at = now()
        WHERE analysis_jobs.status IN ('done', 'failed')
    RETURNING gaf_id
""")

# A job that stays 'running' too long belongs to a crashed worker: retry it, or fail it if out of attempts.
RELEASE_STUCK_JOBS = text("""
    UPDATE analysis_jobs
    SET status = CASE WHEN attempts >= :max_attempts THEN 'failed' ELSE 'pending' END,
        error = 'Stuck', delay = INTERVAL '0 seconds', updated_at = now()
    WHERE status = 'running' AND updated_at < now() - make_interval(mins => :minutes)
""")

# SKIP LOCKED: a job another server is claiming right now is skipped instead of waited for.
CLAIM_JOB = text("""
    UPDATE analysis_jobs SET status = 'running', attempts = attempts + 1, updated_at = now()
    WHERE gaf_id = (
        SELECT gaf_id FROM analysis_jobs
        WHERE status = 'pending' AND updated_at + delay <= now()
        ORDER BY updated_at
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING gaf_id, attempts
""")

# The attempts check means only the worker that still owns the job can finish it.
MARK_JOB_DONE = text("""
    UPDATE analysis_jobs SET status = 'done', error = NULL, updated_at = now()
    WHERE gaf_id = :gaf_id AND status = 'running' AND attempts = :attempts
    RETURNING gaf_id
""")

# Exponential backoff with random jitter: wait 2^attempts minutes, times a random 0.5 to 1.5,
# so jobs on many servers do not all retry at the same moment.
MARK_JOB_FAILED = text("""
    UPDATE analysis_jobs
    SET status = CASE WHEN attempts >= :max_attempts THEN 'failed' ELSE 'pending' END,
        delay = make_interval(secs => power(2, attempts) * 60 * (0.5 + random())),
        error = :error, updated_at = now()
    WHERE gaf_id = :gaf_id AND status = 'running' AND attempts = :attempts
""")


class AnalysisQueue:
    """Adds, hands out and finishes analysis jobs. Every method runs inside the caller's transaction."""

    def __init__(self, max_attempts: int, stuck_minutes: int) -> None:
        """Set how many tries a job gets and when a 'running' job counts as stuck."""
        self.max_attempts = max_attempts
        self.stuck_minutes = stuck_minutes

    def upsert_job(self, connection: Connection, gaf_id: str, fingerprint: str) -> bool:
        """Queue a contractor unless its analysis matches these facts or its job is already open."""
        queued = connection.execute(UPSERT_JOB, {"gaf_id": gaf_id, "fingerprint": fingerprint}).scalar()
        return queued is not None

    def claim_job(self, connection: Connection) -> dict | None:
        """Free any stuck jobs, then hand out the next ready job (or None if there is none)."""
        connection.execute(RELEASE_STUCK_JOBS, {"max_attempts": self.max_attempts, "minutes": self.stuck_minutes})
        row = connection.execute(CLAIM_JOB).first()
        if row is None:
            return None
        return {"gaf_id": row.gaf_id, "attempts": row.attempts}

    def mark_job_done(self, connection: Connection, job: dict) -> bool:
        """Mark a job as done. False if another worker has taken it over."""
        finished = connection.execute(MARK_JOB_DONE, {"gaf_id": job["gaf_id"], "attempts": job["attempts"]}).scalar()
        return finished is not None

    def mark_job_failed(self, connection: Connection, job: dict, error: str) -> None:
        """Record a failed attempt: retry after a delay, or 'failed' once all attempts are used."""
        parameters = {
            "max_attempts": self.max_attempts,
            "error": error[:1000],
            "gaf_id": job["gaf_id"],
            "attempts": job["attempts"],
        }
        connection.execute(MARK_JOB_FAILED, parameters)
