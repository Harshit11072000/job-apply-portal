"""
LinkedIn platform adapter — Easy Apply flow.
Credentials: LINKEDIN_EMAIL and LINKEDIN_PASSWORD env vars.
"""

import hashlib
import logging
import os
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from platforms.base_platform import BasePlatform, Job
from core.answer_engine import answer_field

log = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com"


class LinkedInPlatform(BasePlatform):
    name = "linkedin"

    def login(self, page) -> None:
        email = os.environ.get("LINKEDIN_EMAIL", self.profile["email"])
        password = os.environ.get("LINKEDIN_PASSWORD", "")
        if not password:
            raise RuntimeError("Set LINKEDIN_PASSWORD env var.")

        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)
        page.fill('#username', email, timeout=10000)
        page.fill('#password', password, timeout=10000)
        page.click('button[type="submit"]', timeout=10000)

        try:
            page.wait_for_url(lambda u: "/feed" in u or "/jobs" in u, timeout=20000)
        except PlaywrightTimeoutError:
            pass

        if "/login" in page.url or "/checkpoint" in page.url:
            raise RuntimeError(f"LinkedIn login failed — URL: {page.url}")
        log.info("LinkedIn: logged in.")

    def search_jobs(self, page) -> list[Job]:
        jobs: list[Job] = []
        cities = self.profile.get("target_cities", ["Bangalore"])
        keywords = self.search_config.get("keywords", ["Backend Engineer"])

        for city in cities[:2]:           # limit to 2 cities per run to avoid rate limits
            for kw in keywords[:2]:
                jobs.extend(self._search_one(page, kw, city))
                if len(jobs) >= self.max_per_run:
                    return jobs[:self.max_per_run]
        return jobs

    def _search_one(self, page, keyword: str, city: str) -> list[Job]:
        from urllib.parse import quote
        url = (
            f"{BASE_URL}/jobs/search/?keywords={quote(keyword)}"
            f"&location={quote(city + ', India')}"
            f"&f_AL=true"          # Easy Apply only
            f"&f_E=4"              # Mid-Senior level
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            return []

        jobs = []
        cards = page.query_selector_all('.jobs-search__results-list li, .job-card-container')
        for card in cards:
            try:
                title_el = card.query_selector('.job-card-list__title, a.job-card-container__link')
                company_el = card.query_selector('.job-card-container__primary-description, .artdeco-entity-lockup__subtitle')
                link_el = card.query_selector('a[href*="/jobs/view/"]')

                if not title_el or not link_el:
                    continue
                title = title_el.inner_text().strip()
                company = company_el.inner_text().strip() if company_el else ""
                href = link_el.get_attribute("href") or ""
                if self.should_skip_title(title):
                    continue
                job_id = hashlib.md5(href.encode()).hexdigest()[:16]
                jobs.append(Job(id=job_id, title=title, company=company,
                                url=href if href.startswith("http") else BASE_URL + href,
                                platform=self.name))
            except Exception:
                continue

        log.info(f"LinkedIn: '{keyword}' in {city} → {len(jobs)} jobs.")
        return jobs

    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool:
        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            return False

        # Click "Easy Apply" button
        try:
            btn = page.wait_for_selector(
                'button.jobs-apply-button:has-text("Easy Apply"), '
                '.jobs-s-apply button:has-text("Easy Apply")',
                timeout=8000,
            )
            btn.click()
        except PlaywrightTimeoutError:
            log.info(f"LinkedIn: no Easy Apply button: {job.title}")
            return False

        # Walk through modal steps
        for step in range(10):
            page.wait_for_timeout(1500)

            # Fill any visible text / select fields
            self._fill_visible_fields(page, job)

            # Check for "Submit application" button
            submit = page.query_selector('button[aria-label="Submit application"]')
            if submit and submit.is_visible():
                submit.click()
                log.info(f"LinkedIn: submitted: {job.title} @ {job.company}")
                page.wait_for_timeout(2000)
                # Close modal if still open
                close = page.query_selector('button[aria-label="Dismiss"]')
                if close:
                    close.click()
                return True

            # "Next" or "Review" to advance
            next_btn = page.query_selector(
                'button[aria-label="Continue to next step"], '
                'button[aria-label="Review your application"]'
            )
            if next_btn and next_btn.is_visible():
                next_btn.click()
            else:
                break

        log.warning(f"LinkedIn: could not complete apply flow: {job.title}")
        # Close modal
        close = page.query_selector('button[aria-label="Dismiss"]')
        if close:
            close.click()
        return False

    def _fill_visible_fields(self, page, job: Job):
        """Fill text inputs and selects in the Easy Apply modal."""
        inputs = page.query_selector_all('.jobs-easy-apply-modal input, .jobs-easy-apply-modal select, .jobs-easy-apply-modal textarea')
        for inp in inputs:
            try:
                if not inp.is_visible():
                    continue
                tag = inp.evaluate("el => el.tagName.toLowerCase()")
                label_el = page.query_selector(f'label[for="{inp.get_attribute("id")}"]')
                label = label_el.inner_text().strip() if label_el else inp.get_attribute("placeholder") or ""

                if tag == "select":
                    options = inp.evaluate("el => Array.from(el.options).map(o => o.text)")
                    answer = answer_field(label, "select", options, job.title, job.company)
                    inp.select_option(label=answer)
                elif tag in ("input", "textarea"):
                    current = inp.input_value()
                    if current:
                        continue   # already filled (e.g. name/email pre-populated)
                    answer = answer_field(label, "text", [], job.title, job.company)
                    inp.fill(answer)
            except Exception:
                continue
