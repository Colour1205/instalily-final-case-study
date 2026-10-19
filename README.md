# LiLi: AI lead finder for roofing sales reps

LiLi turns GAF's public contractor directory into a ranked list of sales leads for a roofing materials distributor.
It collects every residential roofing contractor within 25 miles of ZIP 10013 (New York City), scores each one, and
writes an AI sales note for each: a summary, why to call, what to pitch, talking points and a draft email.
Reps browse the leads on a website with filters, a map, short video-style "Roofing Shorts" and email drafts.

- Repository: https://github.com/Colour1205/instalily-final-case-study
- Design decisions, architecture diagram and database schema: [DESIGN.md](DESIGN.md)

## What is inside

| Part | What it does |
|---|---|
| `backend/orchestrator.py` | Scrapes GAF once a day, scores each contractor, and works through the AI analysis queue |
| `backend/api.py` | FastAPI web API (`/v1/leads`, `/v1/map`, `/v1/leads/{gaf_id}`) that also serves the website |
| `backend/main.py` | Starts the API and the orchestrator together |
| `frontend/` | The website: plain HTML, CSS and JavaScript, no build step |
| PostgreSQL | Stores contractors, analyses, the job queue and the scrape log |
| Redis | Caches API answers for 60 seconds (optional: without it, every request reads PostgreSQL) |

## Run it locally

The steps below were tested on Windows 11 with Python 3.12, PostgreSQL 18 and Memurai (Redis for Windows).
They work the same way on macOS and Linux; the only differences are shown as separate commands.

### 1. Install the prerequisites

- **Python 3.12** from https://www.python.org/downloads/
- **PostgreSQL** (version 14 or newer) from https://www.postgresql.org/download/. Remember the password you give the `postgres` user.
- **Redis** (optional but recommended): on Windows install Memurai (https://www.memurai.com/), on macOS `brew install redis`, on Linux `sudo apt install redis-server`. Leave it on the default port 6379.

### 2. Get the code and the Python packages

```bash
git clone https://github.com/Colour1205/instalily-final-case-study.git
cd instalily-final-case-study
python -m venv .venv
```

Activate the virtual environment, then install the packages:

```powershell
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

```bash
# macOS or Linux
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

### 3. Create the database

```bash
psql -U postgres -c "CREATE DATABASE leads;"
```

(On Windows, if `psql` is not found, open "SQL Shell (psql)" from the Start menu and run `CREATE DATABASE leads;`.)

### 4. Create your settings file

Copy the example settings and fill in your PostgreSQL password:

```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
```

```bash
# macOS or Linux
cp .env.example .env
```

Then open `.env` and set `POSTGRES_PASSWORD`. Every other setting has a working default.

**Choosing the AI (needed only for the AI sales notes, step 6).** The default model, `lili-analyst`, is the author's own
fine-tuned model running on a private computer, so it is not reachable from yours. Pick one of these instead by removing
the `#` in front of the matching lines in `.env`:

- **Claude** (about $0.40 for all 426 contractors): `AI_PROVIDER=claude`, `AI_MODEL=claude-haiku-5-5` and your `ANTHROPIC_API_KEY`.
- **Ollama on your own computer** (free): install Ollama from https://ollama.com, run `ollama pull qwen3:1.7b`, then set
  `AI_PROVIDER=ollama`, `AI_MODEL=qwen3:1.7b` and `OLLAMA_URL=http://localhost:11434`. Any Ollama model works; the answers
  are better with a larger or fine-tuned one.

You can also skip the AI: the website still works, and each lead shows "Analysis on its way."

### 5. Create the tables and load the contractors

```bash
python backend/orchestrator.py --setup-db
python backend/orchestrator.py --scrape
```

The scrape takes a few seconds and should end with `ZIP 10013: saved 426 contractors, queued 426 AI jobs`
(the number changes as GAF's directory changes).

### 6. Write the AI sales notes (optional)

```bash
python backend/orchestrator.py --analyze
```

This works through every waiting job and then stops. It takes a few seconds per contractor. You can skip it: the
background worker started in step 7 also writes the notes, a few at a time.

**Skip this step if you did not choose an AI in step 4.** Every job would fail, and the command would take a long time
to try all of them.

### 7. Start the app

```bash
python backend/main.py
```

If you skipped the AI, the background worker logs a warning now and then while it retries the jobs. That is expected,
and the website works normally.

Open **http://localhost:8000** for the website and **http://localhost:8000/docs** for the interactive API documentation.
Press Ctrl+C in the terminal to stop.

### Run the tests

```bash
python -m pytest -q
```

The tests use made-up data and fakes, so they need no database, Redis, network or AI.

## Orchestrator commands

| Command | What it does |
|---|---|
| `python backend/orchestrator.py` | Runs forever: the daily scrape (between 2 and 7 AM New York time) plus the AI workers |
| `python backend/orchestrator.py --setup-db` | Creates any missing tables and indexes, then exits (`main.py` runs this first) |
| `python backend/orchestrator.py --scrape` | Scrapes GAF now, then exits |
| `python backend/orchestrator.py --analyze` | Finishes every waiting AI job, then exits |

## Settings

All settings live in `backend/shared/settings.py` and can be changed in `.env` (or as environment variables) without
touching the code. The ones you are most likely to change:

| Setting | Default | Meaning |
|---|---|---|
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `localhost`, `5432`, `postgres`, empty, `leads` | The database |
| `POSTGRES_REPLICA_HOST` | empty | A read replica for the API; empty means reads go to the main database |
| `REDIS_URL` | `redis://localhost:6379/0` | The cache |
| `AI_PROVIDER`, `AI_MODEL` | `ollama`, `lili-analyst` | Which AI writes the notes (change both together) |
| `OLLAMA_URL` / `ANTHROPIC_API_KEY` | private address / empty | Where Ollama runs / the key for Claude |
| `API_HOST`, `API_PORT` | `127.0.0.1`, `8000` | Where the API listens |

## Notes

- **Data source:** contractors come from the public search service (Coveo) behind GAF's contractor finder, using the
  public search key GAF sends to every browser. gaf.com itself blocks automated visitors, and LiLi does not try to get around that.
- **Live demo:** https://colour1205.github.io/instalily-final-case-study/ serves the website from GitHub Pages. It shows
  data only while the author's computer is running the API.
- **Tested with:** Windows 11, Python 3.12.10, PostgreSQL 18.6, Memurai for Redis 8.2.
