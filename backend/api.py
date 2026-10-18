"""The web API that reps' pages call. It keeps no state of its own, so many copies can run behind a load balancer.

Run from the backend folder:  python -m uvicorn api:app --port 8000   (or start everything with main.py)
Open the app at http://localhost:8000 and the API docs at http://localhost:8000/docs
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from leads import routes_leads

FRONTEND_FOLDER = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="GAF Lead Platform API", version="1")
app.include_router(routes_leads.router)


@app.middleware("http")
async def check_for_new_files(request, call_next):
    """Make browsers ask for newer page files on each visit (a quick "not modified" reply if unchanged)."""
    response = await call_next(request)
    if not request.url.path.startswith("/v1"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# Mounted last so /v1 and /docs are matched first; everything else is the LiLi web page.
app.mount("/", StaticFiles(directory=FRONTEND_FOLDER, html=True), name="frontend")
