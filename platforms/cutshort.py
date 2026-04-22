"""
Cutshort platform adapter — AI-matched tech roles in India.
Credentials: CUTSHORT_EMAIL / CUTSHORT_PASSWORD env vars.
"""

import hashlib
import logging
import os
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from platforms.base_platform import BasePlatform, Job

log = logging.getLogger(__name__)

BASE_URL = "https://cutshort.io"


class CutshortPlatform(BasePlatform):
    name = "cutshort"

    def login(self, page) -> None:
        email = os.environ.get("CUTSHORT_EMAIL", self.profile["email"])
        password = os.environ.get("CUTSHORT_PASSWORD", "")
        if not password:
            raise RuntimeError("Set CUTSHORT_PASSWORD env var.")

        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        page.fill('input[type="email"]', email, timeout=10000)
        page.fill('input[type="password"]', password, timeout=10000)
        page.click('button[type="submit"]', timeout=10000)
        try:
            page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        except PlaywrightTimeoutError:
            pass
        log.info(f"Cutshort: login attempted. URL: {page.url}")

    def search_jobs(self, page) -> list[Job]:
        try:
            page.goto(f"{BASE_URL}/jobs", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            return []

        return self._extract_cards(page)

    def _extract_cards(self, page) -> list[Job]:
        jobs = []
        cards = page.query_selector_all('[class*="jobCard"], [class*="job-card"], .job-list-item')
        for card in cards:
            try:
                title_el = card.query_selector('[class*="title"], h3, h4')
                company_el = card.query_selector('[class*="company"]')
                link_el = card.query_selector('a[href*="/jobs/"]')
                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                href = link_el.get_attribute("href") if link_el else ""
                if not title or self.should_skip_title(title):
                    continue
                url = href if href.startswith("http") else BASE_URL + href
                job_id = hashlib.md5(url.encode()).hexdigest()[:16]
                jobs.append(Job(id=job_id, title=title, company=company, url=url, platform=self.name))
            except Exception:
                continue
        log.info(f"Cutshort: found {len(jobs)} jobs.")
        return jobs

    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool:
        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            return False

        for sel in ['button:has-text("Apply")', '[class*="apply"]']:
            try:
                btn = page.wait_for_selector(sel, timeout=6000)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(2000)
                    log.info(f"Cutshort: applied: {job.title} @ {job.company}")
                    return True
            except PlaywrightTimeoutError:
                continue
        return False
