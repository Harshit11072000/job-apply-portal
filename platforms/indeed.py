"""
Indeed India (indeed.co.in) platform adapter.
Uses Indeed's Easy Apply flow where available.
Credentials: INDEED_EMAIL / INDEED_PASSWORD env vars.
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

BASE_URL = "https://in.indeed.com"


class IndeedPlatform(BasePlatform):
    name = "indeed"

    def login(self, page) -> None:
        email = os.environ.get("INDEED_EMAIL", self.profile["email"])
        password = os.environ.get("INDEED_PASSWORD", "")
        if not password:
            raise RuntimeError("Set INDEED_EMAIL and INDEED_PASSWORD env vars.")

        page.goto(f"{BASE_URL}/account/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Indeed may show email first, then password on next screen
        try:
            page.fill('input[name="__email"], input[type="email"]', email, timeout=8000)
            page.click('button[type="submit"]', timeout=8000)
            page.wait_for_timeout(1500)
        except PlaywrightTimeoutError:
            pass

        try:
            page.fill('input[name="__password"], input[type="password"]', password, timeout=8000)
            page.click('button[type="submit"]', timeout=8000)
        except PlaywrightTimeoutError:
            pass

        try:
            page.wait_for_url(lambda u: "account" not in u or "dashboard" in u, timeout=20000)
        except PlaywrightTimeoutError:
            pass

        log.info(f"Indeed: login attempted. URL: {page.url}")

    def search_jobs(self, page) -> list[Job]:
        jobs: list[Job] = []
        cities = self.profile.get("target_cities", ["Bangalore"])
        keywords = self.search_config.get("keywords", ["Backend Engineer"])

        for city in cities[:2]:
            for kw in keywords[:2]:
                found = self._search_one(page, kw, city)
                jobs.extend(found)
                if len(jobs) >= self.max_per_run:
                    return jobs[:self.max_per_run]
        return jobs

    def _search_one(self, page, keyword: str, city: str) -> list[Job]:
        url = f"{BASE_URL}/jobs?q={quote(keyword)}&l={quote(city)}&iafilter=1"  # iafilter=1 = Indeed Apply
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            return []

        jobs = []
        cards = page.query_selector_all('[data-jk], .job_seen_beacon, .slider_item')
        for card in cards:
            try:
                title_el = card.query_selector('.jobTitle a, h2.jobTitle a, [class*="jobTitle"] a')
                company_el = card.query_selector('[data-testid="company-name"], .companyName')
                jk = card.get_attribute("data-jk") or ""
                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""

                if not title or not jk:
                    continue
                if self.should_skip_title(title):
                    continue

                url = f"{BASE_URL}/viewjob?jk={jk}"
                jobs.append(Job(id=jk, title=title, company=company, url=url, platform=self.name))
            except Exception:
                continue

        log.info(f"Indeed: '{keyword}' in {city} → {len(jobs)} jobs.")
        return jobs

    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool:
        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            return False

        # Look for "Apply now" (Indeed Apply, not external)
        try:
            btn = page.wait_for_selector(
                'button#indeedApplyButton, [id*="indeedApply"], button:has-text("Apply now")',
                timeout=8000,
            )
            if not btn or not btn.is_visible():
                return False

            btn_text = btn.inner_text().strip()
            if "company" in btn_text.lower():
                log.info(f"Indeed: skipping external apply: {job.title}")
                return False

            btn.click()
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            log.info(f"Indeed: no Indeed Apply button: {job.title}")
            return False

        # Walk through multi-step application
        for _ in range(8):
            page.wait_for_timeout(1500)
            self._fill_visible_fields(page, job)

            # Submit
            submit = page.query_selector('button[type="submit"]:has-text("Submit"), button:has-text("Submit your application")')
            if submit and submit.is_visible():
                submit.click()
                log.info(f"Indeed: submitted: {job.title} @ {job.company}")
                return True

            # Next step
            nxt = page.query_selector('button:has-text("Continue"), button:has-text("Next")')
            if nxt and nxt.is_visible():
                nxt.click()
            else:
                break

        return False

    def _fill_visible_fields(self, page, job: Job):
        for inp in page.query_selector_all('input:visible, select:visible, textarea:visible'):
            try:
                if not inp.is_visible():
                    continue
                tag = inp.evaluate("el => el.tagName.toLowerCase()")
                input_type = inp.get_attribute("type") or "text"
                if input_type in ("submit", "hidden", "file", "checkbox", "radio"):
                    continue

                label_id = inp.get_attribute("id") or ""
                label_el = page.query_selector(f'label[for="{label_id}"]') if label_id else None
                label = label_el.inner_text().strip() if label_el else (inp.get_attribute("placeholder") or "")

                if tag == "select":
                    options = inp.evaluate("el => Array.from(el.options).map(o => o.text)")
                    answer = answer_field(label, "select", options, job.title, job.company)
                    inp.select_option(label=answer)
                else:
                    current = inp.input_value()
                    if current:
                        continue
                    answer = answer_field(label, "text", [], job.title, job.company)
                    inp.fill(answer)
            except Exception:
                continue
