#!/usr/bin/env python3
"""
Job Application Scheduler — orchestrates all platforms.

Usage:
  python scheduler.py                          # run all enabled platforms
  python scheduler.py --platform naukri        # run one platform
  python scheduler.py --platform naukri --dry-run   # search only, no apply
  python scheduler.py --platform indeed --limit 3   # apply to max 3 jobs
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")

from playwright.sync_api import sync_playwright

import core.job_tracker as tracker
from platforms import ALL_PLATFORMS, PLATFORM_MAP
from core.resume_tailor import tailor_resume

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"scheduler_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("scheduler")


def run_platform(platform_cls, dry_run: bool = False, limit: int = 0):
    platform = platform_cls()
    if not platform.enabled:
        log.info(f"[{platform.name}] disabled in config — skipping.")
        return

    max_applies = limit if limit > 0 else platform.max_per_run
    applied_this_run = 0

    log.info(f"[{platform.name}] starting — max {max_applies} applies.")

    with sync_playwright() as p:
        # Platforms that use Google SSO launch with the real Chrome profile
        # so Google OAuth completes silently without any password.
        use_chrome_profile = getattr(platform_cls, "use_chrome_profile", False)

        if use_chrome_profile:
            chrome_user_data = os.path.expanduser("~/Library/Application Support/Google/Chrome")
            context = p.chromium.launch_persistent_context(
                user_data_dir=chrome_user_data,
                channel="chrome",           # use real Chrome, not Chromium
                headless=False,
                slow_mo=60,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 800},
            )
            browser = None
            page = context.new_page()
        else:
            browser = p.chromium.launch(
                headless=False,
                slow_mo=60,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = context.new_page()

        def close_all():
            context.close()
            if browser:
                browser.close()

        try:
            platform.login(page)
        except Exception as e:
            log.error(f"[{platform.name}] Login failed: {e}")
            close_all()
            return

        try:
            jobs = platform.search_jobs(page)
        except Exception as e:
            log.error(f"[{platform.name}] Search failed: {e}")
            close_all()
            return

        log.info(f"[{platform.name}] Found {len(jobs)} jobs.")

        for job in jobs:
            if applied_this_run >= max_applies:
                log.info(f"[{platform.name}] Reached limit ({max_applies}).")
                break

            if tracker.is_applied(job.id, platform.name):
                log.info(f"[{platform.name}] Skip (already applied): {job.title} @ {job.company}")
                continue

            if dry_run:
                log.info(f"[{platform.name}] DRY RUN — would apply: {job.title} @ {job.company}")
                applied_this_run += 1
                continue

            # Tailor resume for this job
            resume_path = tailor_resume(
                job_description=job.description,
                platform=platform.name,
                job_id=job.id,
                job_title=job.title,
                company=job.company,
            )

            try:
                success = platform.apply_to_job(page, job, resume_path)
            except Exception as e:
                log.warning(f"[{platform.name}] Apply error for {job.title}: {e}")
                success = False

            if success:
                tracker.mark_applied(job.id, platform.name, job.title, job.company, job.url)
                applied_this_run += 1
                log.info(
                    f"[{platform.name}] [{applied_this_run}/{max_applies}] "
                    f"Applied: {job.title} @ {job.company}"
                )
                time.sleep(2)  # polite delay between applications

        context.close()
        if browser:
            browser.close()

    log.info(f"[{platform.name}] Done. Applied {applied_this_run} this run.")


def main():
    tracker.init_db()

    parser = argparse.ArgumentParser(description="Job application scheduler")
    parser.add_argument("--platform", help="Run a single platform by name (e.g. naukri)")
    parser.add_argument("--dry-run", action="store_true", help="Search only, do not apply")
    parser.add_argument("--limit", type=int, default=0, help="Max applications (overrides config)")
    args = parser.parse_args()

    if args.platform:
        cls = PLATFORM_MAP.get(args.platform)
        if not cls:
            log.error(f"Unknown platform: {args.platform}. Options: {list(PLATFORM_MAP)}")
            sys.exit(1)
        run_platform(cls, dry_run=args.dry_run, limit=args.limit)
    else:
        for cls in ALL_PLATFORMS:
            run_platform(cls, dry_run=args.dry_run, limit=args.limit)
            time.sleep(5)  # gap between platforms

    log.info("=== Scheduler run complete ===")
    log.info(f"Total applied today: {tracker.applied_today()}")
    log.info(f"Total applied all time: {tracker.total_applied()}")


if __name__ == "__main__":
    main()
