"""
Instahyre platform adapter.
Login: uses Google SSO via the real Chrome profile (already signed into Google).
No password needed — Chrome auto-completes the Google OAuth flow silently.
"""

import hashlib
import logging
import os
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from platforms.base_platform import BasePlatform, Job

log = logging.getLogger(__name__)

BASE_URL = "https://www.instahyre.com"

# Path to your real Chrome profile — already signed into Google
CHROME_USER_DATA = os.path.expanduser("~/Library/Application Support/Google/Chrome")
CHROME_PROFILE = "Default"


class InstahyrePlatform(BasePlatform):
    name = "instahyre"

    # Tell the scheduler to launch with the real Chrome profile
    use_chrome_profile = True

    def login(self, page) -> None:
        """
        Instahyre uses Google SSO. Since we launch with the real Chrome profile
        (already signed into Google), we just click 'Sign in with Google' and
        Chrome completes the OAuth silently — no password required.
        """
        page.goto(f"{BASE_URL}/login/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # If already logged in (session persists in Chrome profile), skip
        if "/login" not in page.url:
            log.info("Instahyre: already logged in via Chrome session.")
            return

        # Click Google SSO button
        try:
            google_btn = page.wait_for_selector(
                'a[href*="google"], button:has-text("Google"), '
                '[class*="google"], a:has-text("Sign in with Google")',
                timeout=8000,
            )
            google_btn.click()
        except PlaywrightTimeoutError:
            raise RuntimeError("Instahyre: could not find Google sign-in button.")

        # Google OAuth — Chrome auto-selects the account already signed in
        # Wait for redirect back to Instahyre
        try:
            page.wait_for_url(
                lambda u: "instahyre.com" in u and "/login" not in u,
                timeout=30000,
            )
        except PlaywrightTimeoutError:
            # May need account selection — pick the right email
            email = self.profile["email"]
            try:
                account_btn = page.wait_for_selector(
                    f'[data-email="{email}"], div:has-text("{email}")',
                    timeout=8000,
                )
                account_btn.click()
                page.wait_for_url(
                    lambda u: "instahyre.com" in u and "/login" not in u,
                    timeout=20000,
                )
            except PlaywrightTimeoutError:
                raise RuntimeError(f"Instahyre: Google OAuth did not complete. URL: {page.url}")

        log.info(f"Instahyre: logged in via Google SSO. URL: {page.url}")

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
