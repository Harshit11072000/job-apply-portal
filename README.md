# Job Apply Portal

An automated job application system that searches and applies to matching roles across **13 platforms** simultaneously, with AI-powered resume tailoring per job description.

## Platforms Supported

| # | Platform | Type |
|---|----------|------|
| 1 | Naukri | Indian portal |
| 2 | Instahyre | AI-matched India |
| 3 | LinkedIn | Global + Easy Apply |
| 4 | Indeed India | High volume |
| 5 | Glassdoor | MNC / salary-transparent |
| 6 | Foundit (Monster India) | Mid-senior tech |
| 7 | TimesJobs | Indian corporate |
| 8 | Shine.com | NCR / Gurgaon |
| 9 | iimjobs.com | Premium 20–50 LPA |
| 10 | Wellfound | Startups global |
| 11 | Cutshort | AI-matched India |
| 12 | Hirist.tech | Tech-only niche |
| 13 | Internshala Jobs | Growing full-time |

## Features

- **Multi-platform** — runs all 13 platforms in one command
- **AI resume tailoring** — Claude rewrites your resume to match each JD (no fabrication)
- **Smart form filling** — rule-based answers for CTC/notice + Claude for open-ended questions
- **Deduplication** — SQLite tracker prevents applying twice
- **Live dashboard** — FastAPI web UI at `localhost:8000`
- **Configurable** — YAML files for profile, search params, and per-platform settings
- **Open source** — add new platform adapters by implementing `BasePlatform`

## Setup

```bash
# 1. Clone and install
git clone https://github.com/JyotiSingh07/job-apply-portal
cd job-apply-portal
pip install -r requirements.txt
playwright install chromium

# 2. Configure credentials
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY + platform passwords

# 3. Edit your profile
nano config/profile.yaml

# 4. Test a single platform (dry run — no actual applications)
python scheduler.py --platform naukri --dry-run

# 5. Run for real
python scheduler.py --platform naukri --limit 5
python scheduler.py   # all platforms
```

## Dashboard

```bash
uvicorn portal.app:app --reload --port 8000
# Open http://localhost:8000
```

## Architecture

```
job-apply-portal/
├── config/          # profile.yaml, platforms.yaml, search_params.yaml
├── core/
│   ├── job_tracker.py      # SQLite deduplication DB
│   ├── answer_engine.py    # Claude-powered form answers
│   └── resume_tailor.py    # Per-JD resume tailoring → PDF
├── platforms/
│   ├── base_platform.py    # Abstract interface
│   ├── naukri.py           # ...and 12 more adapters
│   └── ...
├── portal/
│   └── app.py              # FastAPI dashboard
├── scheduler.py            # Main orchestrator
└── .env.example
```

## Adding a New Platform

```python
from platforms.base_platform import BasePlatform, Job
from pathlib import Path

class MyPlatform(BasePlatform):
    name = "myplatform"

    def login(self, page) -> None: ...
    def search_jobs(self, page) -> list[Job]: ...
    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool: ...
```

Then register it in `platforms/__init__.py`.

## Scheduling (macOS launchd)

Add to your existing launchd setup or run via cron:

```cron
0 * * * * cd /path/to/job-apply-portal && python scheduler.py >> logs/cron.log 2>&1
```

## License

MIT — contributions welcome.
