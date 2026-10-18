"""The web API that reps' pages call. It keeps no state of its own, so many copies can run behind a load balancer.

Run from the backend folder:  python -m uvicorn api:app --port 8000   (or start everything with main.py)
Open the app at http://localhost:8000 and the API docs at http://localhost:8000/docs
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from leads import routes_leads
from shared.config import settings

FRONTEND_FOLDER = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="GAF Lead Platform API", version="1")
app.include_router(routes_leads.router)
# Lets the frontend on GitHub Pages read the API (read-only: GET requests only).
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"])

# Mounted last so /v1 and /docs are matched first; everything else is the LiLi web page.
app.mount("/", StaticFiles(directory=FRONTEND_FOLDER, html=True), name="frontend")
