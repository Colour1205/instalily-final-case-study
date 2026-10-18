"""Starts the API and the orchestrator as two separate processes on this machine.

In production they would run separately (several API servers, several orchestrators). Run from anywhere:
    python backend/main.py
"""

import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

from shared.config import settings

BACKEND_FOLDER = Path(__file__).parent
WINDOWS = sys.platform == "win32"
log = logging.getLogger("main")


def start(command: list[str]) -> subprocess.Popen:
    """Start one child process in a way that lets main.py ask it to stop politely later."""
    if WINDOWS:
        # Its own process group, so it can be sent Ctrl+Break (Windows has no SIGTERM).
        return subprocess.Popen(command, cwd=BACKEND_FOLDER, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(command, cwd=BACKEND_FOLDER)


def main() -> None:
    """Start both processes; stop both cleanly when one of them ends or Ctrl+C is pressed."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    api = start(
        [sys.executable, "-m", "uvicorn", "api:app", "--host", settings.api_host, "--port", str(settings.api_port)]
    )
    orchestrator = start([sys.executable, "orchestrator.py"])
    log.info("API on http://%s:%d/docs, orchestrator running. Ctrl+C to stop.", settings.api_host, settings.api_port)

    try:
        while api.poll() is None and orchestrator.poll() is None:
            time.sleep(1)
        log.warning("One process stopped, stopping the other")
    except KeyboardInterrupt:
        log.info("Stopping both processes after their current work")

    # Ask politely first, so the orchestrator can mark its jobs and scrape runs properly.
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
