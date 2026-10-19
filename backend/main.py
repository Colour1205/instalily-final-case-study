"""Sets up the tables, then starts the API and the orchestrator as two separate processes on this machine.

In production they would run separately (several API servers, several orchestrators). Run from anywhere:
    python backend/main.py
"""

import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

from shared.settings import settings

BACKEND_FOLDER = Path(__file__).parent
WINDOWS = sys.platform == "win32"
log = logging.getLogger("main")


def _helper_start(command: list[str]) -> subprocess.Popen:
    """Start one child process in a way that lets main.py stop it gracefully later."""
    if WINDOWS:
        # Its own process group, so it can be sent Ctrl+Break (Windows has no SIGTERM).
        return subprocess.Popen(command, cwd=BACKEND_FOLDER, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(command, cwd=BACKEND_FOLDER)


def main() -> None:
    """Start both processes; stop both gracefully when one of them ends or Ctrl+C (or a stop signal) arrives."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Treat a stop signal or Ctrl+Break like Ctrl+C, so the two processes are always stopped gracefully first.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    # Create any missing tables once, before anything uses them (stops here if that fails).
    subprocess.run([sys.executable, "orchestrator.py", "--setup-db"], cwd=BACKEND_FOLDER, check=True)
    api = _helper_start(
        [sys.executable, "-m", "uvicorn", "api:app", "--host", settings.API_HOST, "--port", str(settings.API_PORT)]
    )
    orchestrator = _helper_start([sys.executable, "orchestrator.py"])
    log.info("API on http://%s:%d/docs, orchestrator running. Ctrl+C to stop.", settings.API_HOST, settings.API_PORT)

    try:
        while api.poll() is None and orchestrator.poll() is None:
            time.sleep(1)
        log.warning("One process stopped, stopping the other")
    except KeyboardInterrupt:
        log.info("Stopping both processes gracefully")

    # Stop gracefully first, so the orchestrator can mark its jobs and scrape runs properly; kill after 90 s.
    for process in (api, orchestrator):
        if process.poll() is None:
            if WINDOWS:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.terminate()
    for process in (api, orchestrator):
        try:
            process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
