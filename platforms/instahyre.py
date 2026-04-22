"""
Instahyre platform adapter.
Credentials: INSTAHYRE_EMAIL / INSTAHYRE_PASSWORD env vars.
Instahyre shows curated "Interested" opportunities — we click Interested
on matching cards rather than filling lengthy forms.
"""

import hashlib
import logging
import os
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from platforms.base_platform import BasePlatform, Job

log = logging.getLogger(__name__)

BASE_URL = "https://www.instahyre.com"


class InstahyrePlatform(BasePlatform):
    name = "instahyre"

    def login(self, page) -> None:
        email = os.environ.get("INSTAHYRE_EMAIL", self.profile["email"])
        password = os.environ.get("INSTAHYRE_PASSWORD", "")
        if not password:
            raise RuntimeError("Set INSTAHYRE_PASSWORD env var.")

        page.goto(f"{BASE_URL}/login/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)

        page.fill('input[name="email"], input[type="email"]', email, timeout=10000)
        page.fill('input[name="password"], input[type="password"]', password, timeout=10000)
        page.click('button[type="submit"], input[type="submit"]', timeout=10000)

        try:
            page.wait_for_url(lambda u: "/dashboard" in u or "/opportunities" in u or "/jobs" in u, timeout=20000)
        except PlaywrightTimeoutError:
            pass

        if "/login" in page.url:
            raise RuntimeError(f"Instahyre login failed — URL: {page.url}")
        log.info("Instahyre: logged in.")

    def search_jobs(self, page) -> list[Job]:
        """Load the opportunities/matches page."""
        try:
            page.goto(f"{BASE_URL}/candidate/opportunities/", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            return []

        return self._extract_cards(page)

    def _extract_cards(self, page) -> list[Job]:
        jobs = []
        try:
            page.wait_for_selector('[class*="opportunity"], [class*="job-card"], .card', timeout=10000)
        except PlaywrightTimeoutError:
            return jobs

        cards = page.query_selector_all('[class*="opportunity-card"], [class*="job-card"], .opportunity')
        for card in cards:
            try:
                title_el = card.query_selector('[class*="title"], h3, h4')
                company_el = card.query_selector('[class*="company"], [class*="employer"]')
                link_el = card.query_selector('a[href]')

                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                href = link_el.get_attribute("href") if link_el else ""

                if not title:
                    continue
                if self.should_skip_title(title):
                    continue

                url = href if href.startswith("http") else BASE_URL + href
                job_id = hashlib.md5(url.encode()).hexdigest()[:16]
                jobs.append(Job(id=job_id, title=title, company=company, url=url, platform=self.name))
            except Exception:
                continue

        log.info(f"Instahyre: found {len(jobs)} opportunity cards.")
        return jobs

    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool:
        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            return False

        # Click "I'm Interested" or "Apply" button
        for selector in [
            'button:has-text("I\'m Interested")',
            'button:has-text("Interested")',
            'button:has-text("Apply")',
            '[class*="apply-btn"]',
            '[class*="interested"]',
        ]:
            try:
                btn = page.wait_for_selector(selector, timeout=5000)
                if btn and btn.is_visible():
                    btn.click()
                    log.info(f"Instahyre: clicked apply: {job.title} @ {job.company}")
                    page.wait_for_timeout(2000)
                    return True
            except PlaywrightTimeoutError:
                continue

        log.info(f"Instahyre: no apply button found: {job.title}")
        return False
