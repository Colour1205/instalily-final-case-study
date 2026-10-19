-- The one PostgreSQL database for the lead platform. Run once per deploy by `orchestrator.py --setup-db`
-- (main.py does this), never by every worker: running it locks tables, even when nothing changes.
-- Safe to run more than once. It only creates what is missing; changing an existing table needs a migration.

-- If two setup runs start at the same moment, they take turns running this file.
SELECT pg_advisory_xact_lock(7243001);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id         BIGSERIAL   PRIMARY KEY,
    zip_code   TEXT        NOT NULL,
    status     TEXT        NOT NULL CHECK (status IN ('running', 'done', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Only one scrape per ZIP code can be running at a time.
CREATE UNIQUE INDEX IF NOT EXISTS scrape_runs_one_running_per_zip
    ON scrape_runs (zip_code) WHERE status = 'running';

CREATE TABLE IF NOT EXISTS contractors (
    gaf_id                     TEXT         PRIMARY KEY,
    name                       TEXT         NOT NULL,
    rating                     NUMERIC(2,1),
    review_count               INTEGER      NOT NULL DEFAULT 0,
    certification              TEXT,
    president_club_stars       SMALLINT     NOT NULL DEFAULT 0,
    commercial_certification   TEXT,
    services                   TEXT[]       NOT NULL DEFAULT '{}',
    phone                      TEXT,
    address                    TEXT,
    distance_miles             NUMERIC(5,2),
    latitude                   DOUBLE PRECISION,
    longitude                  DOUBLE PRECISION,
    profile_url                TEXT,
    logo_url                   TEXT,
    fingerprint                TEXT         NOT NULL,
    priority_score             NUMERIC(5,2) NOT NULL,
    -- The four 25-point parts of priority_score, so the list can be ranked by any of them.
    review_count_adjusted_rating NUMERIC(5,2) NOT NULL DEFAULT 0,
    gaf_rank                   NUMERIC(5,2) NOT NULL DEFAULT 0,
    specialty                  NUMERIC(5,2) NOT NULL DEFAULT 0,
    distance                   NUMERIC(5,2) NOT NULL DEFAULT 0,
    updated_at                 TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS contractors_certification ON contractors (certification);

-- One analysis per contractor; a new one replaces the old one.
CREATE TABLE IF NOT EXISTS analyses (
    gaf_id         TEXT   PRIMARY KEY REFERENCES contractors (gaf_id) ON DELETE CASCADE,
    summary        TEXT   NOT NULL,
    why_good_lead  TEXT   NOT NULL,
    pitch          TEXT   NOT NULL,
    talking_points TEXT[] NOT NULL,
    draft_email    TEXT   NOT NULL,
    fingerprint    TEXT   NOT NULL
);

-- One queue row per contractor, holding the state of its AI job.
CREATE TABLE IF NOT EXISTS analysis_jobs (
    gaf_id     TEXT        PRIMARY KEY REFERENCES contractors (gaf_id) ON DELETE CASCADE,
    status     TEXT        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts   INTEGER     NOT NULL DEFAULT 0,
    error      TEXT,
    -- How long to wait after updated_at before the job may be tried again.
    delay      INTERVAL    NOT NULL DEFAULT '0 seconds',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS analysis_jobs_pending ON analysis_jobs (updated_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS analysis_jobs_running ON analysis_jobs (updated_at) WHERE status = 'running';
