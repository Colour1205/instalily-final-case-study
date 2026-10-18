"""Orchestrator: runs the daily GAF scrape and works through the AI analysis jobs.

It is the only file that knows the whole flow and the only one that opens transactions. Copies can run on
many servers at once: they coordinate only through the shared PostgreSQL database.

Run from the backend folder:
    python orchestrator.py                 run forever (daily scrape + AI jobs)
    python orchestrator.py --scrape-now    scrape every ZIP now, then exit
    python orchestrator.py --analyze 5     finish 5 AI jobs, then exit
"""

import argparse
import logging
import signal
import sys
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from analysis.ai_claude import ClaudeProvider
from analysis.ai_provider import AbstractAIProvider
from analysis.db_analysis import AnalysisStore
from analysis.queue_ai_jobs import AIJobQueue
from scraping.db_scraping import ScrapeStore
from scraping.scraper_gaf import GAFScraper
from shared.config import settings
from shared.db_postgres import SCHEMA_FILE, primary_engine

log = logging.getLogger("orchestrator")


class Orchestrator:
    """Connects the scraper, the AI provider and the database stores, and owns every transaction."""

    def __init__(self, provider: AbstractAIProvider) -> None:
        """Wire up the stores, the job queue and the chosen AI provider."""
        self.provider = provider
        self.scrape_store = ScrapeStore(settings.scrape_stuck_minutes)
        self.queue = AIJobQueue(settings.ai_max_attempts, settings.ai_stuck_minutes)
        self.analysis_store = AnalysisStore()

    def scrape_all(self, force: bool = False) -> bool:
        """Scrape every ZIP code, save the contractors and queue AI jobs for new facts. True if none failed."""
        min_hours = settings.min_hours_between_scrapes
        if force:
            min_hours = 0
        all_ok = True
        for zip_code in settings.scrape_zip_codes:
            with primary_engine.begin() as connection:
                run_id = self.scrape_store.start_run(connection, zip_code, min_hours)
            if run_id is None:
                log.info("ZIP %s: skipped, scraped recently", zip_code)
                continue
            try:
                contractors = GAFScraper(zip_code).fetch()
                queued = 0
                for contractor in contractors:
                    contractor["fingerprint"] = self.provider.fingerprint(contractor)
                    # Saving a contractor and queueing its AI job succeed or fail together.
                    with primary_engine.begin() as connection:
                        self.scrape_store.save_contractor(connection, contractor)
                        if self.queue.add(connection, contractor["gaf_id"], contractor["fingerprint"]):
                            queued += 1
                with primary_engine.begin() as connection:
                    self.scrape_store.finish_run(connection, run_id, "done")
                log.info("ZIP %s: saved %d contractors, queued %d AI jobs", zip_code, len(contractors), queued)
            except KeyboardInterrupt:
                with primary_engine.begin() as connection:
                    self.scrape_store.finish_run(connection, run_id, "failed")
                raise
            except Exception:
                with primary_engine.begin() as connection:
                    self.scrape_store.finish_run(connection, run_id, "failed")
                log.exception("ZIP %s: scrape failed", zip_code)
                all_ok = False
        return all_ok

    def analyze_next(self) -> str:
        """Claim one AI job and finish it. Returns "no job", "analyzed" or "failed"."""
        with primary_engine.begin() as connection:
            job = self.queue.claim(connection)
            if job is None:
                return "no job"
            facts = self.analysis_store.get_facts(connection, job["gaf_id"])

        try:
            # The slow AI call happens outside any transaction, so it never holds database locks.
            analysis = self.provider.analyze(facts)
            # A missing or null field makes this save fail, which sends the job back to the queue.
            with primary_engine.begin() as connection:
                if not self.queue.finish(connection, job):
                    log.warning("%s: job taken over by another worker, result dropped", facts["name"])
                    return "analyzed"
                self.analysis_store.save_analysis(
                    connection, job["gaf_id"], analysis, self.provider.fingerprint(facts)
                )
                # If the facts changed while the AI was working, queue another job for the new facts.
                latest = self.analysis_store.get_facts(connection, job["gaf_id"])
                self.queue.add(connection, job["gaf_id"], self.provider.fingerprint(latest))
        except KeyboardInterrupt:
            with primary_engine.begin() as connection:
                self.queue.fail(connection, job, "Stopped")
            raise
        except Exception as error:
            with primary_engine.begin() as connection:
                self.queue.fail(connection, job, repr(error))
            log.warning("%s: attempt %d failed: %r", facts["name"], job["attempts"], error)
            return "failed"
        log.info("%s: analyzed", facts["name"])
        return "analyzed"

    def analysis_loop(self, stop: threading.Event) -> None:
        """Keep finishing AI jobs until told to stop. Pause when there is no job, and longer after a failure."""
        while not stop.is_set():
            try:
                result = self.analyze_next()
                if result == "no job":
                    stop.wait(settings.queue_poll_seconds)
                elif result == "failed":
                    # If the AI service is down, this stops the threads from burning every job's attempts.
                    stop.wait(settings.ai_failure_pause_seconds)
            except Exception:
                log.exception("AI job loop error")
                stop.wait(settings.queue_poll_seconds)


def main() -> None:
    """Read the command line, then scrape, analyze, or run forever."""
    parser = argparse.ArgumentParser(description="Runs the GAF scrape and the AI analysis jobs.")
    parser.add_argument("--scrape-now", action="store_true", help="scrape every ZIP now, then exit")
    parser.add_argument("--analyze", type=int, metavar="N", help="finish N AI jobs, then exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy_logger in ("httpx", "httpx2"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    # Treat a stop signal like Ctrl+C, so jobs and scrape runs are marked properly before exiting.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    with primary_engine.begin() as connection:
        connection.exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))

    # Strategy pattern: the AI provider is picked here; everything else only uses the parent class.
    if settings.ai_provider == "claude":
        provider = ClaudeProvider(
            settings.claude_model, settings.claude_effort, settings.claude_timeout_seconds, settings.anthropic_api_key
        )
    else:
        raise ValueError(f"Unknown AI provider: {settings.ai_provider}")
    orchestrator = Orchestrator(provider)

    if args.scrape_now or args.analyze is not None:
        all_ok = True
        if args.scrape_now:
            all_ok = orchestrator.scrape_all(force=True)
        if args.analyze is not None:
            handled = 0
            while handled < args.analyze:
                if orchestrator.analyze_next() == "no job":
                    break
                handled += 1
            log.info("Handled %d AI jobs", handled)
        if not all_ok:
            sys.exit(1)
        return

    scheduler = BackgroundScheduler(timezone=settings.scrape_timezone)
    # misfire_grace_time=None: if the computer was asleep at a scheduled time, run once when it wakes.
    scheduler.add_job(
        orchestrator.scrape_all,
        CronTrigger(hour=settings.scrape_hours, minute="*/15", timezone=settings.scrape_timezone),
        id="daily_scrape",
        misfire_grace_time=None,
    )
    stop = threading.Event()
    threads = []
    # "finally" always cleans up, even if Ctrl+C comes while the threads are still starting.
    try:
        scheduler.start()
        for _ in range(settings.analysis_threads):
            thread = threading.Thread(target=orchestrator.analysis_loop, args=(stop,))
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


if __name__ == "__main__":
    main()
