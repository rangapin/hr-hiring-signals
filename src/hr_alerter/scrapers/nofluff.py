"""NoFluffJobs scraper using their public REST API.

Fetches HR job postings from https://nofluffjobs.com/api/posting
and filters for HR-relevant categories and keywords.
"""

import logging
from datetime import datetime

import requests

from hr_alerter.scrapers.base import BaseScraper
from hr_alerter.scrapers.utils import detect_seniority

logger = logging.getLogger(__name__)

API_URL = "https://nofluffjobs.com/api/posting"

# Categories to include from the NoFluffJobs taxonomy
HR_CATEGORIES = {"hr"}

# Additional keywords to catch HR jobs filed under other categories
HR_TITLE_KEYWORDS = [
    "hr", "human resources", "kadry", "people", "wellbeing",
    "culture", "rekrutacja", "talent", "payroll", "employer branding",
    "employee experience", "onboarding",
]


class NoFluffScraper(BaseScraper):
    """Scraper for NoFluffJobs using their public JSON API.

    Fetches all postings in a single API call (the endpoint returns
    the full list), then filters client-side for HR-relevant jobs.
    """

    SOURCE = "nofluffjobs"

    def scrape(
        self,
        keywords: list[str] | None = None,
        max_pages: int = 1,
    ) -> list[dict]:
        """Fetch and filter HR jobs from NoFluffJobs API.

        Args:
            keywords: Extra title keywords to match (added to defaults).
            max_pages: Not used (API returns all postings at once).

        Returns:
            A list of dicts conforming to the job_posting_dict contract.
        """
        extra_keywords = [k.lower() for k in (keywords or [])]
        all_keywords = list(set(HR_TITLE_KEYWORDS + extra_keywords))

        try:
            resp = requests.get(
                API_URL,
                headers=self.get_headers(),
                timeout=60,
            )
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception("Failed to fetch NoFluffJobs API")
            return []

        try:
            data = resp.json()
        except ValueError:
            logger.error("NoFluffJobs API returned non-JSON response")
            return []

        postings = data.get("postings", [])
        logger.info("NoFluffJobs API returned %d total postings", len(postings))

        jobs = []
        for posting in postings:
            category = (posting.get("category") or "").lower()
            title = (posting.get("title") or "").lower()

            # Include if HR category OR title matches an HR keyword
            is_hr_category = category in HR_CATEGORIES
            is_hr_title = any(kw in title for kw in all_keywords)

            if is_hr_category or is_hr_title:
                job = self._posting_to_dict(posting)
                if job:
                    jobs.append(job)

        logger.info("Filtered to %d HR-relevant jobs", len(jobs))
        return jobs

    @staticmethod
    def _posting_to_dict(posting: dict) -> dict | None:
        """Convert a NoFluffJobs API posting to job_posting_dict."""
        title = posting.get("title", "").strip()
        company = posting.get("name", "").strip()

        if not title or not company:
            return None

        # URL
        url_slug = posting.get("url", "")
        job_url = f"https://nofluffjobs.com/pl/job/{url_slug}" if url_slug else ""

        # Location: extract cities from places
        places = posting.get("location", {}).get("places", [])
        cities = []
        for place in places:
            city = place.get("city")
            if city and city != "Remote":
                cities.append(city)
        if posting.get("fullyRemote"):
            cities.append("Remote")
        location = ", ".join(cities) if cities else None

        # Date: timestamp in milliseconds
        ts = posting.get("posted", 0)
        post_date = None
        if ts:
            try:
                post_date = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

        # Seniority
        seniority_list = posting.get("seniority", [])
        seniority_raw = seniority_list[0] if seniority_list else ""
        seniority = detect_seniority(seniority_raw) or detect_seniority(title)

        return {
            "source": "nofluffjobs",
            "job_url": job_url,
            "job_title": title,
            "company_name_raw": company,
            "location": location,
            "post_date": post_date,
            "job_description": None,
            "seniority_level": seniority,
            "employment_type": None,
        }
