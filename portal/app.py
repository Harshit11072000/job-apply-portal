"""
FastAPI dashboard for the job application portal.

Run: uvicorn portal.app:app --reload --port 8000
Open: http://localhost:8000
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import core.job_tracker as tracker

app = FastAPI(title="Job Apply Portal")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.on_event("startup")
def startup():
    tracker.init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    stats = tracker.get_stats(days=7)
    recent = tracker.get_recent_jobs(limit=50)
    total = tracker.total_applied()
    today = tracker.applied_today()

    # Aggregate per platform for today
    from collections import defaultdict
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    by_platform = defaultdict(int)
    for s in stats:
        if s["date"] == today_str:
            by_platform[s["platform"]] += s["applied"]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total": total,
        "today": today,
        "by_platform": dict(by_platform),
        "stats": stats,
        "recent": recent,
    })


@app.get("/api/stats")
def api_stats():
    return {
        "total": tracker.total_applied(),
        "today": tracker.applied_today(),
        "weekly": tracker.get_stats(days=7),
    }


@app.get("/api/jobs")
def api_jobs(limit: int = 50):
    return tracker.get_recent_jobs(limit=limit)
