"""
Naukri.com platform adapter.
Ported from /resume/naukri_apply.py with the base class interface.
"""

import logging
import os
import re
import sys
import time
from pathlib import Path

import keyring
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from platforms.base_platform import BasePlatform, Job
from core.answer_engine import answer_field

log = logging.getLogger(__name__)

KEYRING_SERVICE = "naukri_auto_upload"
RECOMMENDED_URL = "https://www.naukri.com/mnjuser/recommendedjobs"


class NaukriPlatform(BasePlatform):
    name = "naukri"

    def login(self, page) -> None:
        email = self.profile["email"]
        password = keyring.get_password(KEYRING_SERVICE, email)
        if not password:
            password = os.environ.get("NAUKRI_PASSWORD", "")
        if not password:
            raise RuntimeError("Naukri password not found in Keychain or NAUKRI_PASSWORD env var.")

        log.info("Naukri: visiting homepage to warm cookies...")
        page.goto("https://www.naukri.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        page.fill('input[placeholder="Enter Email ID / Username"]', email, timeout=15000)
        page.wait_for_timeout(400)
        page.fill('input[type="password"]', password, timeout=10000)
        page.wait_for_timeout(400)
        page.click('button[type="submit"]', timeout=10000)

        try:
            page.wait_for_url(
                lambda url: "nlogin" not in url and "/login" not in url,
                timeout=20000,
            )
        except PlaywrightTimeoutError:
            pass

        page.wait_for_timeout(2000)
        if "nlogin" in page.url or "/login" in page.url:
            raise RuntimeError(f"Naukri login failed — still on: {page.url}")
        log.info(f"Naukri: logged in. URL: {page.url}")

    def search_jobs(self, page) -> list[Job]:
        log.info("Naukri: loading recommended jobs...")
        try:
            page.goto(RECOMMENDED_URL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            log.error("Naukri: timeout loading recommended jobs.")
            return []

        return self._extract_job_cards(page)

    def _extract_job_cards(self, page) -> list[Job]:
        jobs = []
        try:
            page.wait_for_selector(
                '.jobTuple, .cust-job-tuple, article.jobTuple, [class*="jobCard"]',
                timeout=10000,
            )
        except PlaywrightTimeoutError:
            return jobs

        cards = page.query_selector_all(
            '.jobTuple, .cust-job-tuple, article.jobTuple, [class*="jobCard"]'
        )
        for card in cards:
            try:
                title_el = card.query_selector('a.title, .title a, [class*="title"] a, h2 a')
                title = title_el.inner_text().strip() if title_el else ""
                href = title_el.get_attribute("href") if title_el else ""

                company_el = card.query_selector(
                    '.subTitle, .companyInfo a, [class*="company"] a, [class*="companyName"]'
                )
                company = company_el.inner_text().strip() if company_el else ""

                if not title or not href:
                    continue
                if self.should_skip_title(title):
                    continue

                job_id = self._extract_job_id(href)
                url = href if href.startswith("http") else f"https://www.naukri.com{href}"
                jobs.append(Job(id=job_id, title=title, company=company, url=url, platform=self.name))
            except Exception:
                continue

        log.info(f"Naukri: found {len(jobs)} job cards.")
        return jobs

    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool:
        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1500)

            if page.query_selector('button:text("Applied"), [class*="already-applied"], .applied-btn'):
                log.info(f"Naukri: already applied (platform says so): {job.title}")
                return False

            apply_btn = page.query_selector(
                'button.apply-button, a.apply-button, [class*="applyBtn"], '
                'button[id*="apply"], button[id*="Apply"], '
                'div.apply-button, [class*="apply-btn"], [class*="applyButton"]'
            )

            if not apply_btn:
                for btn in page.query_selector_all('button, a[role="button"]'):
                    try:
                        if not btn.is_visible():
                            continue
                        txt = btn.inner_text().strip()
                        if txt in ("Apply", "Apply on company site"):
                            apply_btn = btn
                            break
                    except Exception:
                        continue

            if not apply_btn:
                log.info(f"Naukri: no Apply button found: {job.title}")
                return False

            btn_text = apply_btn.inner_text().strip()
            if "company site" in btn_text.lower() or "company website" in btn_text.lower():
                log.info(f"Naukri: skipping external apply: {job.title}")
                return False

            apply_btn.click()

        except Exception as e:
            log.warning(f"Naukri: apply click error: {e}")
            return False

        try:
            page.wait_for_selector(
                'div.textArea[contenteditable="true"], div[data-placeholder="Type message here..."]',
                timeout=5000,
            )
            log.info("Naukri: chatbot questions detected.")
            return self._handle_chatbot(page, job)
        except PlaywrightTimeoutError:
            log.info(f"Naukri: Easy Apply (no questions): {job.title}")
            return True

    def _handle_chatbot(self, page, job: Job) -> bool:
        for _ in range(15):
            page.wait_for_timeout(1500)

            question = self._get_chatbot_question(page)

            try:
                chat_input = page.wait_for_selector(
                    'div.textArea[contenteditable="true"], div[data-placeholder="Type message here..."]',
                    timeout=4000,
                )
            except PlaywrightTimeoutError:
                chat_input = None

            option_buttons = page.query_selector_all(
                '[class*="ssQuestionWrapper"] button, '
                '[class*="botOption"] button, '
                '[class*="quick-reply"] button'
            )

            if chat_input and chat_input.is_visible():
                answer = answer_field(question, "text", [], job.title, job.company)
                log.info(f"Naukri chatbot Q: {question!r} → A: {answer!r}")
                chat_input.click(click_count=3)
                page.keyboard.type(answer)
                page.wait_for_timeout(400)

                send_btn = page.query_selector(
                    'button[class*="sendBtn"], button[class*="send-btn"], '
                    '[class*="chatFooter"] button, [class*="chat-footer"] button'
                )
                if send_btn and send_btn.is_visible():
                    send_btn.click()
                else:
                    page.keyboard.press("Enter")

            elif option_buttons and any(b.is_visible() for b in option_buttons):
                visible = [b for b in option_buttons if b.is_visible()]
                answer = answer_field(question, "select", [b.inner_text() for b in visible], job.title, job.company)
                best = next((b for b in visible if answer.lower() in b.inner_text().lower()), None)
                btn = best or visible[0]
                log.info(f"Naukri chatbot option: {btn.inner_text().strip()!r}")
                btn.click()
            else:
                done_markers = [
                    '[class*="success"]', '[class*="applied"]',
                    'text=Application submitted', 'text=Successfully applied',
                ]
                if any(page.query_selector(m) for m in done_markers):
                    log.info("Naukri: chatbot flow — application submitted.")
                return True

        return True

    def _get_chatbot_question(self, page) -> str:
        for sel in [
            '[class*="ssQuestionWrapper"]',
            '[class*="questionText"]',
            '[class*="bot-message"]',
            '[class*="botMsg"]',
        ]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    return text
        return ""

    @staticmethod
    def _extract_job_id(url: str) -> str:
        match = re.search(r'-(\d{15,})', url)
        if match:
            return match.group(1)
        return str(abs(hash(url)))
