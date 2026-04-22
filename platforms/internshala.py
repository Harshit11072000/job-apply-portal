"""
Internshala Jobs platform adapter — growing full-time tech listings.
Credentials: INTERNSHALA_EMAIL / INTERNSHALA_PASSWORD env vars.
"""

import hashlib
import logging
import os
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from platforms.base_platform import BasePlatform, Job

log = logging.getLogger(__name__)

BASE_URL = "https://internshala.com"


class IntershalaPlatform(BasePlatform):
    name = "internshala"

    def login(self, page) -> None:
        email = os.environ.get("INTERNSHALA_EMAIL", self.profile["email"])
        password = os.environ.get("INTERNSHALA_PASSWORD", "")
        if not password:
            raise RuntimeError("Set INTERNSHALA_PASSWORD env var.")

        page.goto(f"{BASE_URL}/login/user", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        page.fill('#email, input[name="email"]', email, timeout=10000)
        page.fill('#password, input[name="password"]', password, timeout=10000)
        page.click('#login_submit, button[type="submit"]', timeout=10000)
        try:
            page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        except PlaywrightTimeoutError:
            pass
        log.info(f"Internshala: login attempted. URL: {page.url}")

    def search_jobs(self, page) -> list[Job]:
        jobs: list[Job] = []
        keywords = self.search_config.get("keywords", ["Backend Engineer"])
        cities = self.profile.get("target_cities", ["Bangalore"])
        for city in cities[:2]:
            for kw in keywords[:2]:
                jobs.extend(self._search_one(page, kw, city))
                if len(jobs) >= self.max_per_run:
                    return jobs[:self.max_per_run]
        return jobs

    def _search_one(self, page, keyword: str, city: str) -> list[Job]:
        url = f"{BASE_URL}/jobs/keywords-{quote(keyword.lower().replace(' ', '-'))}/location-{quote(city.lower())}"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            return []

        jobs = []
        cards = page.query_selector_all('.individual_internship, [class*="job_card"]')
        for card in cards:
            try:
                title_el = card.query_selector('.profile a, h3 a, [class*="title"] a')
                company_el = card.query_selector('.company_name a, [class*="company"]')
                link_el = card.query_selector('a[href*="/jobs/detail/"]')
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
        log.info(f"Internshala: '{keyword}' in {city} → {len(jobs)} jobs.")
        return jobs

    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool:
        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            return False

        for sel in ['#apply-button', 'button:has-text("Apply Now")', 'a:has-text("Apply")']:
            try:
                btn = page.wait_for_selector(sel, timeout=5000)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(2000)
                    log.info(f"Internshala: applied: {job.title} @ {job.company}")
                    return True
            except PlaywrightTimeoutError:
                continue
        return False
