"""
Abstract base class for all job platform adapters.

Each platform implements:
  - login(page)        — authenticate
  - search_jobs(page)  — return list of job dicts
  - apply_to_job(page, job, resume_path) — apply and return True/False

The scheduler calls these in sequence per platform.
"""

from abc import ABC, abstractmethod
from pathlib import Path
import logging
import os
import yaml

log = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config"

def load_config() -> tuple[dict, dict, dict]:
    with open(_CONFIG_DIR / "profile.yaml") as f:
        profile = yaml.safe_load(f)
    with open(_CONFIG_DIR / "platforms.yaml") as f:
        platforms = yaml.safe_load(f)
    with open(_CONFIG_DIR / "search_params.yaml") as f:
        search = yaml.safe_load(f)
    return profile, platforms, search


class Job:
    """Uniform job representation across platforms."""
    __slots__ = ("id", "title", "company", "url", "description", "platform")

    def __init__(self, id: str, title: str, company: str, url: str,
                 platform: str, description: str = ""):
        self.id = id
        self.title = title
        self.company = company
        self.url = url
        self.platform = platform
        self.description = description

    def __repr__(self):
        return f"<Job {self.platform}:{self.id} '{self.title}' @ {self.company}>"


class BasePlatform(ABC):
    """All platform adapters inherit from this class."""

    name: str = ""   # e.g. "naukri", "linkedin"

    def __init__(self):
        self.profile, self.platform_config, self.search_config = load_config()
        cfg = self.platform_config["platforms"].get(self.name, {})
        self.max_per_run: int = cfg.get("max_per_run", 20)
        self.enabled: bool = cfg.get("enabled", True)

    @abstractmethod
    def login(self, page) -> None:
        """Authenticate on the platform. Raises on failure."""
        ...

    @abstractmethod
    def search_jobs(self, page) -> list[Job]:
        """Return a list of Job objects from search results."""
        ...

    @abstractmethod
    def apply_to_job(self, page, job: Job, resume_path: Path) -> bool:
        """
        Apply to a single job.
        Returns True if application was submitted (or attempted).
        Returns False to skip (already applied, external link, etc.).
        """
        ...

    def get_resume_path(self, city: str = "") -> Path:
        """Return the correct resume PDF for a city."""
        base = Path(__file__).parent.parent.parent / "resume"
        if city.lower() in ("gurgaon", "delhi", "ncr"):
            candidate = base / "HARSHIT_SINGH_RESUME.pdf"
        else:
            candidate = base / "HarshitResume.pdf"
        return candidate if candidate.exists() else (base / "HarshitResume.pdf")

    def should_skip_title(self, title: str) -> bool:
        """Return True if this job title should be skipped."""
        title_lower = title.lower()
        for kw in self.search_config.get("skip_keywords", []):
            if kw.lower() in title_lower:
                return True
        return False
