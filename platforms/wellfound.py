"""
Wellfound (wellfound.com, formerly AngelList Talent) platform adapter.
Great for startup roles globally.
Credentials: WELLFOUND_EMAIL / WELLFOUND_PASSWORD env vars.
"""

import hashlib
import logging
import os
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from platforms.base_platform import BasePlatform, Job
from core.answer_engine import answer_field

log = logging.getLogger(__name__)

BASE_URL = "https://wellfound.com"


class WellfoundPlatform(BasePlatform):
    name = "wellfound"

    def login(self, page) -> None:
        email = os.environ.get("WELLFOUND_EMAIL", self.profile["email"])
        password = os.environ.get("WELLFOUND_PASSWORD", "")
        if not password:
            raise RuntimeError("Set WELLFOUND_PASSWORD env var.")

        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        page.fill('input[name="email"], input[type="email"]', email, timeout=10000)
        page.fill('input[name="password"], input[type="password"]', password, timeout=10000)
        page.click('input[type="submit"], button[type="submit"]', timeout=10000)
        try:
            page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        except PlaywrightTimeoutError:
            pass
        log.info(f"Wellfound: login attempted. URL: {page.url}")

    def search_jobs(self, page) -> list[Job]:
        jobs: list[Job] = []
        keywords = self.search_config.get("keywords", ["Backend Engineer"])
        for kw in keywords[:3]:
            jobs.extend(self._search_one(page, kw))
            if len(jobs) >= self.max_per_run:
                return jobs[:self.max_per_run]
        return jobs

    def _search_one(self, page, keyword: str) -> list[Job]:
        # Wellfound has a single global search with location filter
        url = (
            f"{BASE_URL}/role/software-engineer"
            f"?keywords={quote(keyword)}"
            f"&locations[]=India"
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            return []

        jobs = []
        cards = page.query_selector_all('[data-test="StartupResult"], [class*="styles_jobListing"]')
        for card in cards:
            try:
                title_el = card.query_selector('[class*="role"], [class*="title"], h4')
                company_el = card.query_selector('[class*="company"], [class*="startup"]')
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
        log.info(f"Wellfound: '{keyword}' → {len(jobs)} jobs.")
        return jobs

    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool:
        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            return False

        try:
            btn = page.wait_for_selector('button:has-text("Apply"), [data-test="apply-button"]', timeout=8000)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(2000)

                # Fill cover note if shown
                for sel in ['textarea[name="note"], textarea[placeholder*="note"], textarea[placeholder*="cover"]']:
                    try:
                        ta = page.query_selector(sel)
                        if ta and ta.is_visible():
                            answer = answer_field(
                                "Why are you interested in this role?", "text", [],
                                job.title, job.company,
                            )
                            ta.fill(answer)
                    except Exception:
                        pass

                submit = page.query_selector('button:has-text("Submit"), button[type="submit"]')
                if submit and submit.is_visible():
                    submit.click()
                    log.info(f"Wellfound: submitted: {job.title} @ {job.company}")
                    return True
        except PlaywrightTimeoutError:
            pass

        log.info(f"Wellfound: apply flow incomplete: {job.title}")
        return False
