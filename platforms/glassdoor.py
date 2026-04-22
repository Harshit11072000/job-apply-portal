"""
Glassdoor platform adapter.
Uses Glassdoor Easy Apply where available.
Credentials: GLASSDOOR_EMAIL / GLASSDOOR_PASSWORD env vars.
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

BASE_URL = "https://www.glassdoor.co.in"


class GlassdoorPlatform(BasePlatform):
    name = "glassdoor"

    def login(self, page) -> None:
        email = os.environ.get("GLASSDOOR_EMAIL", self.profile["email"])
        password = os.environ.get("GLASSDOOR_PASSWORD", "")
        if not password:
            raise RuntimeError("Set GLASSDOOR_PASSWORD env var.")

        page.goto(f"{BASE_URL}/profile/login_input.htm", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        page.fill('input[name="username"], input[type="email"]', email, timeout=10000)
        page.fill('input[name="password"], input[type="password"]', password, timeout=10000)
        page.click('button[type="submit"], [data-test="email-login-button"]', timeout=10000)

        try:
            page.wait_for_url(lambda u: "login" not in u, timeout=20000)
        except PlaywrightTimeoutError:
            pass

        log.info(f"Glassdoor: login attempted. URL: {page.url}")

    def search_jobs(self, page) -> list[Job]:
        jobs: list[Job] = []
        cities = self.profile.get("target_cities", ["Bangalore"])
        keywords = self.search_config.get("keywords", ["Backend Engineer"])

        for city in cities[:2]:
            for kw in keywords[:2]:
                jobs.extend(self._search_one(page, kw, city))
                if len(jobs) >= self.max_per_run:
                    return jobs[:self.max_per_run]
        return jobs

    def _search_one(self, page, keyword: str, city: str) -> list[Job]:
        url = (
            f"{BASE_URL}/Job/jobs.htm"
            f"?suggestCount=0&suggestChosen=false"
            f"&clickSource=searchBtn&sc.keyword={quote(keyword)}"
            f"&locT=C&locId=&jobType=&easy=true"
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            return []

        jobs = []
        cards = page.query_selector_all('[data-test="jobListing"], .react-job-listing, .JobCard_jobCardContainer__Yvqtl')
        for card in cards:
            try:
                title_el = card.query_selector('[data-test="job-title"], .job-title, .JobCard_jobTitle__rbjTE')
                company_el = card.query_selector('[data-test="employer-short-name"], .employer-name')
                link_el = card.query_selector('a[href*="/job-listing/"]')

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

        log.info(f"Glassdoor: '{keyword}' in {city} → {len(jobs)} jobs.")
        return jobs

    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool:
        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            return False

        try:
            btn = page.wait_for_selector(
                'button[data-test="easyApplyButton"], button:has-text("Easy Apply")',
                timeout=8000,
            )
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(2000)
                log.info(f"Glassdoor: Easy Apply clicked: {job.title}")
                # Glassdoor Easy Apply opens Indeed-powered form or simple modal
                return self._complete_modal(page, job)
        except PlaywrightTimeoutError:
            log.info(f"Glassdoor: no Easy Apply button: {job.title}")
        return False

    def _complete_modal(self, page, job: Job) -> bool:
        for _ in range(6):
            page.wait_for_timeout(1500)
            for inp in page.query_selector_all('input:visible, select:visible, textarea:visible'):
                try:
                    tag = inp.evaluate("el => el.tagName.toLowerCase()")
                    inp_type = inp.get_attribute("type") or "text"
                    if inp_type in ("submit", "hidden", "file"):
                        continue
                    label_id = inp.get_attribute("id") or ""
                    label_el = page.query_selector(f'label[for="{label_id}"]') if label_id else None
                    label = label_el.inner_text().strip() if label_el else (inp.get_attribute("placeholder") or "")
                    if tag == "select":
                        opts = inp.evaluate("el => Array.from(el.options).map(o => o.text)")
                        inp.select_option(label=answer_field(label, "select", opts, job.title, job.company))
                    else:
                        if inp.input_value():
                            continue
                        inp.fill(answer_field(label, "text", [], job.title, job.company))
                except Exception:
                    continue

            submit = page.query_selector('button:has-text("Submit"), button[type="submit"]')
            if submit and submit.is_visible():
                submit.click()
                log.info(f"Glassdoor: submitted: {job.title}")
                return True
            nxt = page.query_selector('button:has-text("Next"), button:has-text("Continue")')
            if nxt and nxt.is_visible():
                nxt.click()
            else:
                break
        return False
