"""Orchestrator: runs the daily GAF scrape and works through the AI analysis jobs.

It is the only file that knows the whole flow and the only one that opens transactions. Copies can run on
many servers at once: they coordinate only through the shared PostgreSQL database.

Run from the backend folder:
    python orchestrator.py               run forever (daily scrape + AI jobs)
    python orchestrator.py --setup-db    create any missing tables and indexes, then exit (main.py does it first)
    python orchestrator.py --scrape      scrape every ZIP now, then exit
    python orchestrator.py --analyze     finish every waiting AI job, then exit
"""

import argparse
import logging
import signal
import sys
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from analysis.abstract_provider import AbstractProvider
from analysis.analysis_data_access import AnalysisDataAccess
from analysis.analysis_queue import AnalysisQueue
from analysis.claude_provider import ClaudeProvider
from analysis.ollama_provider import OllamaProvider
from scraping.gaf_scraper import GAFScraper
from scraping.scrape_data_access import ScrapeDataAccess
from shared.db_postgres import SCHEMA_FILE, primary_engine
from shared.score_priority import compute_scores
from shared.settings import settings

log = logging.getLogger("orchestrator")


class Orchestrator:
    """Connects the scraper, the AI provider and the data access classes, and owns every transaction."""

    def __init__(self, provider: AbstractProvider) -> None:
        """Wire up the data access classes, the analysis queue and the chosen AI provider."""
        self.provider = provider
        self.scrape_data_access = ScrapeDataAccess(settings.SCRAPE_STUCK_MINUTES)
        self.analysis_queue = AnalysisQueue(settings.AI_MAX_ATTEMPTS, settings.AI_STUCK_MINUTES)
        self.analysis_data_access = AnalysisDataAccess()

    def scrape_all(self, force: bool = False) -> bool:
        """Scrape every ZIP code that is due, save the contractors and queue AI jobs for new facts. True if none failed."""
        min_hours = settings.MIN_HOURS_BETWEEN_SCRAPES
        if force:
            min_hours = 0
        all_ok = True
        for zip_code in settings.SCRAPE_ZIP_CODES:
            if not self._helper_scrape_zip(zip_code, min_hours):
                all_ok = False
        return all_ok

    def analyze_next(self) -> str:
        """Claim one AI job and finish it. Returns "no job", "analyzed" or "failed"."""
        job, facts = self._helper_claim_job()
        if job is None:
            return "no job"

        result = "failed"
        error_text = "Stopped"
        try:
            # The slow AI call happens outside any transaction, so it never holds database locks.
            analysis = self.provider.analyze(facts)
            still_ours = self._helper_save_analysis(job, facts, analysis)
            result = "analyzed"
            if still_ours:
                log.info("%s: analyzed", facts["name"])
            else:
                log.warning("%s: job taken over by another worker, result dropped", facts["name"])
        except Exception as error:
            error_text = repr(error)
            log.warning("%s: attempt %d failed: %r", facts["name"], job["attempts"], error)
        finally:
            # Also runs on Ctrl+C, so an unfinished job never stays 'running': it is retried later (with backoff).
            if result == "failed":
                self._helper_mark_job_failed(job, error_text)
        return result

    def run(self) -> None:
        """Run forever: the daily scrape on a schedule plus the AI job threads, until Ctrl+C or a stop signal."""
        scheduler = BackgroundScheduler(timezone=settings.SCRAPE_TIMEZONE)
        # misfire_grace_time=None: if the computer was asleep at a scheduled time, run once when it wakes.
        scheduler.add_job(
            self.scrape_all,
            CronTrigger(hour=settings.SCRAPE_HOURS, minute="*/15", timezone=settings.SCRAPE_TIMEZONE),
            id="daily_scrape",
            misfire_grace_time=None,
        )
        stop = threading.Event()
        threads = []
        # "finally" always cleans up, even if Ctrl+C comes while the threads are still starting.
        try:
            scheduler.start()
            for _ in range(settings.ANALYSIS_THREADS):
                thread = threading.Thread(target=self._analysis_loop, args=(stop,))
                thread.start()
                threads.append(thread)
            log.info("Running with %d AI threads. Ctrl+C to stop.", len(threads))
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Stopping after the current jobs finish")
        finally:
            stop.set()
            if scheduler.running:
                scheduler.shutdown()
            for thread in threads:
                thread.join()

    def _analysis_loop(self, stop: threading.Event) -> None:
        """Keep finishing AI jobs until told to stop. Pause when there is no job, and longer after a failure."""
        while not stop.is_set():
            try:
                result = self.analyze_next()
                if result == "no job":
                    stop.wait(settings.QUEUE_POLL_SECONDS)
                elif result == "failed":
                    # If the AI service is down, this stops the threads from burning every job's attempts.
                    stop.wait(settings.AI_FAILURE_PAUSE_SECONDS)
            except Exception:
                log.exception("AI job loop error")
                stop.wait(settings.QUEUE_POLL_SECONDS)

    def _helper_scrape_zip(self, zip_code: str, min_hours: int) -> bool:
        """Scrape one ZIP code if it is due: save every contractor and record how the run ended. False if it failed."""
        run_id = self._helper_insert_run(zip_code, min_hours)
        if run_id is None:
            log.info("ZIP %s: skipped, scraped recently", zip_code)
            return True
        status = "failed"
        try:
            contractors = GAFScraper(zip_code).fetch()
            queued = 0
            for contractor in contractors:
                self._helper_prepare_contractor(contractor)
                if self._helper_save_contractor(contractor):
                    queued += 1
            status = "done"
            log.info("ZIP %s: saved %d contractors, queued %d AI jobs", zip_code, len(contractors), queued)
        except Exception:
            log.exception("ZIP %s: scrape failed", zip_code)
        finally:
            # Also runs on Ctrl+C, so a scrape run is never left as 'running'.
            self._helper_mark_run_finished(run_id, status)
        return status == "done"

    def _helper_prepare_contractor(self, contractor: dict) -> None:
        """Round GAF's numbers to the stored format, then add the score parts, the total and the fingerprint."""
        # Rounded first and in Python, so the saved values, the scores and the fingerprint all use the same numbers
        # (PostgreSQL rounds some halfway values differently, which would make the fingerprints disagree).
        if contractor["rating"] is not None:
            contractor["rating"] = round(contractor["rating"], 1)
        if contractor["distance_miles"] is not None:
            contractor["distance_miles"] = round(contractor["distance_miles"], 2)
        contractor.update(compute_scores(contractor))
        contractor["fingerprint"] = self.provider.compute_fingerprint(contractor)

    # Each helper below is one transaction: commit() saves it; close() returns the connection and undoes anything unsaved.

    def _helper_insert_run(self, zip_code: str, min_hours: int) -> int | None:
        """Record a new running scrape for this ZIP code; None if one is running or finished recently."""
        connection = primary_engine.connect()
        try:
            run_id = self.scrape_data_access.insert_run(connection, zip_code, min_hours)
            connection.commit()
        finally:
            connection.close()
        return run_id

    def _helper_save_contractor(self, contractor: dict) -> bool:
        """Save one contractor and queue its AI job together, on a fresh connection. True if a job was queued."""
        connection = primary_engine.connect()
        try:
            self.scrape_data_access.save_contractor(connection, contractor)
            queued = self.analysis_queue.upsert_job(connection, contractor["gaf_id"], contractor["fingerprint"])
            connection.commit()
        finally:
            connection.close()
        return queued

    def _helper_mark_run_finished(self, run_id: int, status: str) -> None:
        """Record whether a scrape run ended 'done' or 'failed'."""
        connection = primary_engine.connect()
        try:
            self.scrape_data_access.mark_run_finished(connection, run_id, status)
            connection.commit()
        finally:
            connection.close()

    def _helper_claim_job(self) -> tuple[dict | None, dict | None]:
        """Claim the next ready AI job and read its contractor's facts; (None, None) if no job is ready."""
        connection = primary_engine.connect()
        try:
            job = self.analysis_queue.claim_job(connection)
            facts = None
            if job is not None:
                facts = self.analysis_data_access.get_facts(connection, job["gaf_id"])
            connection.commit()
        finally:
            connection.close()
        return job, facts

    def _helper_save_analysis(self, job: dict, facts: dict, analysis: dict) -> bool:
        """Mark the job done and save its analysis together. False if another worker took the job over."""
        connection = primary_engine.connect()
        try:
            still_ours = self.analysis_queue.mark_job_done(connection, job)
            if still_ours:
                # A missing or null field makes this save fail, which sends the job back to the queue.
                self.analysis_data_access.save_analysis(
                    connection, job["gaf_id"], analysis, self.provider.compute_fingerprint(facts)
                )
                # If the facts changed while the AI was working, queue another job for the new facts.
                latest = self.analysis_data_access.get_facts(connection, job["gaf_id"])
                self.analysis_queue.upsert_job(connection, job["gaf_id"], self.provider.compute_fingerprint(latest))
            connection.commit()
        finally:
            connection.close()
        return still_ours

    def _helper_mark_job_failed(self, job: dict, error_text: str) -> None:
        """Record a failed attempt, so the job is retried later (or marked failed once its tries are used up)."""
        connection = primary_engine.connect()
        try:
            self.analysis_queue.mark_job_failed(connection, job, error_text)
            connection.commit()
        finally:
            connection.close()


def _helper_read_options() -> argparse.Namespace:
    """Read the command-line options: --setup-db, --scrape and --analyze (none means run forever)."""
    parser = argparse.ArgumentParser(description="Runs the GAF scrape and the AI analysis jobs.")
    parser.add_argument("--setup-db", action="store_true", help="create any missing tables and indexes, then exit")
    parser.add_argument("--scrape", action="store_true", help="scrape every ZIP now, then exit")
    parser.add_argument("--analyze", action="store_true", help="finish every waiting AI job, then exit")
    return parser.parse_args()


def _helper_setup_database() -> None:
    """Create any missing tables and indexes.

    Only this step touches table structure. It locks tables even when nothing changes, so busy workers never run it.
    """
    connection = primary_engine.connect()
    try:
        connection.exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()
    log.info("Tables are ready")


def _helper_choose_provider() -> AbstractProvider:
    """Strategy pattern: pick the AI provider from the settings; everything else only uses the parent class."""
    if settings.AI_PROVIDER == "claude":
        return ClaudeProvider(settings.AI_MODEL, settings.AI_TIMEOUT_SECONDS, settings.ANTHROPIC_API_KEY)
    if settings.AI_PROVIDER == "ollama":
        return OllamaProvider(settings.OLLAMA_URL, settings.AI_MODEL, settings.AI_TIMEOUT_SECONDS)
    raise ValueError(f"Unknown AI provider: {settings.AI_PROVIDER}")


def main() -> None:
    """Read the command line, then set up the tables, scrape, analyze, or run forever."""
    options = _helper_read_options()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy_logger in ("httpx", "httpx2"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    if options.setup_db:
        _helper_setup_database()
        return

    # Treat a stop signal like Ctrl+C, so jobs and scrape runs are marked properly before exiting.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    orchestrator = Orchestrator(_helper_choose_provider())

    # No options: run forever (daily scrape + AI jobs).
    if not options.scrape and not options.analyze:
        orchestrator.run()
        return

    # One-off mode: do the requested work once, then exit.
    all_ok = True
    if options.scrape:
        all_ok = orchestrator.scrape_all(force=True)
    if options.analyze:
        handled = 0
        # Failed jobs wait (backoff) before they are ready again, so this ends when nothing is ready.
        while orchestrator.analyze_next() != "no job":
            handled += 1
        log.info("Handled %d AI jobs", handled)
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
