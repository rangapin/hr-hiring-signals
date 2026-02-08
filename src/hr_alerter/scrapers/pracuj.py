"""Pracuj.pl scraper implementation.

Fetches job listings from https://www.pracuj.pl, first attempting to
extract structured data from embedded JSON (``__NEXT_DATA__`` or
``application/json`` script tags), falling back to HTML parsing when
JSON is unavailable.
"""

import json
import logging
from typing import Any
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from hr_alerter.scrapers.base import BaseScraper
from hr_alerter.scrapers.utils import detect_seniority, parse_polish_date

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.pracuj.pl/praca"

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright not installed — Pracuj.pl scraper will not work")


class PracujScraper(BaseScraper):
    """Scraper for Pracuj.pl job board.

    Uses Playwright to bypass Cloudflare protection, then applies a
    two-tier parsing strategy:

    1. **JSON** -- parse ``__NEXT_DATA__`` or ``application/json`` script
       tags embedded in the page.
    2. **HTML** -- fall back to BeautifulSoup CSS-selector parsing when
       embedded JSON is not available or does not contain offers.
    """

    SOURCE = "pracuj.pl"

    def scrape(self, keywords: list[str], max_pages: int = 1) -> list[dict]:
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("playwright not available, cannot scrape Pracuj.pl")
            return []

        all_jobs: list[dict] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                locale="pl-PL",
                user_agent=self.get_headers()["User-Agent"],
            )
            page = context.new_page()

            try:
                for keyword in keywords:
                    for page_num in range(1, max_pages + 1):
                        try:
                            jobs = self._scrape_page(page, keyword, page_num)
                            all_jobs.extend(jobs)
                            logger.info(
                                "Scraped %d jobs for keyword=%r page=%d",
                                len(jobs),
                                keyword,
                                page_num,
                            )
                        except Exception:
                            logger.exception(
                                "Error scraping keyword=%r page=%d",
                                keyword,
                                page_num,
                            )

                        if page_num < max_pages or keyword != keywords[-1]:
                            self.rate_limit_delay()
            finally:
                context.close()
                browser.close()

        return all_jobs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scrape_page(self, page, keyword: str, page_num: int) -> list[dict]:
        """Navigate to a results page and return parsed job dicts."""
        url = f"{_BASE_URL}?q={quote_plus(keyword)}&pn={page_num}"
        logger.debug("Navigating to %s", url)

        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Wait for content to render
        page.wait_for_timeout(3000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Try JSON first, then fall back to HTML
        jobs = self._parse_json(soup)
        if not jobs:
            logger.debug("JSON parsing yielded no results; trying HTML")
            jobs = self._parse_html(soup)

        return jobs

    # ------------------------------------------------------------------
    # JSON parsing strategy
    # ------------------------------------------------------------------

    def _parse_json(self, soup: BeautifulSoup) -> list[dict]:
        """Attempt to extract offers from embedded JSON script tags.

        Looks for ``<script id="__NEXT_DATA__">`` first, then any
        ``<script type="application/json">`` tag.  Recursively searches
        the parsed JSON tree for an array of offer objects.
        """
        jobs: list[dict] = []

        # Strategy 1: __NEXT_DATA__
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                data = json.loads(script.string)
                offers = self._find_offers_in_json(data)
                if offers:
                    jobs = self._offers_to_dicts(offers)
                    return jobs
            except (json.JSONDecodeError, Exception):
                logger.debug("Failed to parse __NEXT_DATA__", exc_info=True)

        # Strategy 2: application/json script tags
        for tag in soup.find_all("script", {"type": "application/json"}):
            if not tag.string:
                continue
            try:
                data = json.loads(tag.string)
                offers = self._find_offers_in_json(data)
                if offers:
                    jobs = self._offers_to_dicts(offers)
                    return jobs
            except (json.JSONDecodeError, Exception):
                continue

        return jobs

    def _find_offers_in_json(self, data: Any, depth: int = 0) -> list[dict] | None:
        """Recursively locate an offers array inside *data*.

        Returns ``None`` when no array of offer-like dicts is found.
        Limits recursion to 12 levels to avoid runaway traversals.
        """
        if depth > 12:
            return None

        if isinstance(data, list):
            # Check if this looks like a list of offers
            if len(data) > 0 and isinstance(data[0], dict):
                sample = data[0]
                # Heuristic: an offer dict contains title/jobTitle and
                # companyName/employer or similar keys.
                offer_keys = {k.lower() for k in sample}
                if offer_keys & {
                    "jobtitle", "job_title", "title", "name",
                    "offerid", "offer_id", "offerId",
                    "groupid", "group_id",
                }:
                    return data

        if isinstance(data, dict):
            # Check well-known key names first
            for key in (
                "offers", "jobOffers", "groupedOffers", "results",
                "data", "props", "pageProps", "jobs", "items",
                "offersList", "searchResults",
            ):
                if key in data:
                    result = self._find_offers_in_json(data[key], depth + 1)
                    if result:
                        return result
            # Fall through: try every value
            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = self._find_offers_in_json(value, depth + 1)
                    if result:
                        return result

        return None

    def _offers_to_dicts(self, offers: list[dict]) -> list[dict]:
        """Convert raw JSON offer objects to ``job_posting_dict`` dicts."""
        results: list[dict] = []
        for offer in offers:
            try:
                job = self._json_offer_to_dict(offer)
                if job and job.get("job_title") and job.get("company_name_raw"):
                    results.append(job)
            except Exception:
                logger.debug("Skipping malformed JSON offer", exc_info=True)
        return results

    def _json_offer_to_dict(self, offer: dict) -> dict:
        """Map a single JSON offer object to a ``job_posting_dict``."""
        title = (
            offer.get("jobTitle")
            or offer.get("job_title")
            or offer.get("title")
            or offer.get("name")
            or ""
        )

        company = self._extract_company_from_json(offer)

        # Location may be a string, a list of dicts, or nested.
        location = self._extract_location_from_json(offer)

        # URL
        job_url = (
            offer.get("offerAbsoluteUri")
            or offer.get("uri")
            or offer.get("url")
            or offer.get("offerUrl")
            or offer.get("job_url")
            or ""
        )
        if job_url and not job_url.startswith("http"):
            job_url = urljoin("https://www.pracuj.pl", job_url)

        # Date
        raw_date = (
            offer.get("lastPublicated")
            or offer.get("publishedAt")
            or offer.get("posted")
            or offer.get("post_date")
            or offer.get("expirationDate")
            or ""
        )
        post_date = None
        if raw_date:
            parsed = parse_polish_date(str(raw_date)[:10])
            post_date = parsed.isoformat() if parsed else None

        # Description
        description = (
            offer.get("jobDescription")
            or offer.get("description")
            or offer.get("job_description")
            or None
        )

        # Employment type
        employment_type = self._extract_employment_type(offer)

        # Seniority
        seniority_raw = (
            offer.get("employmentLevel")
            or offer.get("seniorityLevel")
            or offer.get("experienceLevel")
            or ""
        )
        seniority = detect_seniority(seniority_raw) or detect_seniority(title)

        return {
            "source": self.SOURCE,
            "job_url": job_url,
            "job_title": title.strip() if title else "",
            "company_name_raw": company,
            "location": location,
            "post_date": post_date,
            "job_description": description,
            "seniority_level": seniority,
            "employment_type": employment_type,
        }

    @staticmethod
    def _extract_company_from_json(offer: dict) -> str:
        """Pull company name from various JSON shapes."""
        company = (
            offer.get("companyName")
            or offer.get("company_name")
            or offer.get("employer")
            or ""
        )
        if isinstance(company, dict):
            company = company.get("name", "") or company.get("companyName", "")
        return str(company).strip()

    @staticmethod
    def _extract_location_from_json(offer: dict) -> str | None:
        """Pull location from various JSON shapes."""
        loc = offer.get("location") or offer.get("locations") or offer.get("city")

        if isinstance(loc, str):
            return loc.strip() or None

        if isinstance(loc, list):
            parts: list[str] = []
            for item in loc:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    city = (
                        item.get("city")
                        or item.get("name")
                        or item.get("label")
                        or ""
                    )
                    if city:
                        parts.append(str(city))
            return ", ".join(parts) if parts else None

        if isinstance(loc, dict):
            return (
                loc.get("city")
                or loc.get("name")
                or loc.get("label")
                or None
            )

        return None

    @staticmethod
    def _extract_employment_type(offer: dict) -> str | None:
        """Pull employment type from various JSON shapes."""
        raw = (
            offer.get("employmentType")
            or offer.get("employment_type")
            or offer.get("typesOfContract")
            or None
        )
        if raw is None:
            return None
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if isinstance(raw, dict):
            raw = raw.get("name") or raw.get("label")
        if raw is None:
            return None

        text = str(raw).lower()
        if "full" in text or "pełny" in text or "pełen" in text:
            return "full-time"
        if "contract" in text or "zlecen" in text or "b2b" in text:
            return "contract"
        if "part" in text or "częś" in text or "pół" in text:
            return "part-time"
        return str(raw).strip()

    # ------------------------------------------------------------------
    # HTML parsing strategy (fallback)
    # ------------------------------------------------------------------

    def _parse_html(self, soup: BeautifulSoup) -> list[dict]:
        """Extract jobs from HTML using multiple CSS selector strategies.

        Pracuj.pl periodically changes its markup, so we try several
        sets of selectors and return results from the first set that
        produces matches.
        """
        strategies = [
            # Strategy A -- class names observed 2024-2026
            {
                "card": ("div", {"class_": "listing__item"}),
                "title": ("h2", {"class_": "offer-details__title-link"}),
                "title_link": "a",
                "company": ("h3", {"class_": "company-name"}),
                "location": ("span", {"class_": "offer-labels__item--location"}),
                "date": ("span", {"class_": "offer-labels__item--date"}),
            },
            # Strategy B -- data-test attributes
            {
                "card": ("div", {"attrs": {"data-test": "default-offer"}}),
                "title": ("h2", {"attrs": {"data-test": "offer-title"}}),
                "title_link": "a",
                "company": ("h3", {"attrs": {"data-test": "text-company-name"}}),
                "location": ("span", {"attrs": {"data-test": "text-region"}}),
                "date": ("span", {"attrs": {"data-test": "text-added"}}),
            },
            # Strategy C -- broader class-based
            {
                "card": ("div", {"class_": "c1fljezf"}),
                "title": ("a", {"class_": "tiles_o1859gd9"}),
                "title_link": None,
                "company": ("span", {"class_": "tiles_e1dypgnt"}),
                "location": ("span", {"class_": "tiles_l1dvlr6y"}),
                "date": ("span", {"class_": "tiles_d1e6phdx"}),
            },
            # Strategy D -- generic article / section based
            {
                "card": ("article", {}),
                "title": ("a", {}),
                "title_link": None,
                "company": ("span", {}),
                "location": ("span", {}),
                "date": ("time", {}),
            },
        ]

        for strategy in strategies:
            tag, kwargs = strategy["card"]
            cards = soup.find_all(tag, **kwargs) if kwargs else soup.find_all(tag)

            if not cards:
                continue

            jobs: list[dict] = []
            for card in cards:
                try:
                    job = self._parse_card(card, strategy)
                    if job and job.get("job_title") and job.get("company_name_raw"):
                        jobs.append(job)
                except Exception:
                    logger.debug("Error parsing HTML card", exc_info=True)
                    continue

            if jobs:
                logger.debug(
                    "HTML strategy matched %d cards -> %d jobs",
                    len(cards),
                    len(jobs),
                )
                return jobs

        return []

    def _parse_card(self, card: Any, strategy: dict) -> dict | None:
        """Parse a single HTML job card using the given *strategy*."""
        # Title
        tag, kwargs = strategy["title"]
        title_elem = card.find(tag, **kwargs) if kwargs else card.find(tag)
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)

        # URL from the title link
        job_url = ""
        if strategy.get("title_link"):
            link = title_elem.find(strategy["title_link"])
            if link:
                job_url = link.get("href", "")
        else:
            job_url = title_elem.get("href", "")

        if job_url and not job_url.startswith("http"):
            job_url = urljoin("https://www.pracuj.pl", job_url)

        # Company
        tag, kwargs = strategy["company"]
        company_elem = card.find(tag, **kwargs) if kwargs else card.find(tag)
        company = company_elem.get_text(strip=True) if company_elem else ""

        # Location
        tag, kwargs = strategy["location"]
        loc_elem = card.find(tag, **kwargs) if kwargs else card.find(tag)
        location = loc_elem.get_text(strip=True) if loc_elem else None

        # Date
        tag, kwargs = strategy["date"]
        date_elem = card.find(tag, **kwargs) if kwargs else card.find(tag)
        post_date = None
        if date_elem:
            raw_date = date_elem.get_text(strip=True)
            parsed = parse_polish_date(raw_date)
            post_date = parsed.isoformat() if parsed else None

        seniority = detect_seniority(title)

        return {
            "source": self.SOURCE,
            "job_url": job_url,
            "job_title": title,
            "company_name_raw": company,
            "location": location,
            "post_date": post_date,
            "job_description": None,
            "seniority_level": seniority,
            "employment_type": None,
        }
