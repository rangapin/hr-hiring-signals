"""pypyr step: scrape Pracuj.pl for job postings.

Reads from context
------------------
- ``keywords``    (list[str]) -- search terms, default ``["HR"]``
- ``max_pages``   (int)       -- pages per keyword, default ``1``
- ``user_agents`` (list[str] | None) -- custom UA strings (optional)

Writes to context
-----------------
- ``scraped_jobs`` (list[dict]) -- deduplicated job posting dicts
"""

import logging

from hr_alerter.scrapers.pracuj import PracujScraper

logger = logging.getLogger(__name__)


def run_step(context: dict) -> None:
    """Entry point called by the pypyr pipeline runner."""
    keywords: list[str] = context.get("keywords", ["HR"])
    max_pages: int = int(context.get("max_pages", 1))
    user_agents: list[str] | None = context.get("user_agents")

    logger.info(
        "scrape_pracuj step: keywords=%s, max_pages=%d", keywords, max_pages
    )

    scraper = PracujScraper(user_agents=user_agents)

    try:
        jobs = scraper.scrape(keywords=keywords, max_pages=max_pages)
    except Exception:
        logger.exception("Pracuj.pl scraping failed unexpectedly")
        jobs = []

    # Deduplicate by job_url, keeping the first occurrence
    seen_urls: set[str] = set()
    unique_jobs: list[dict] = []
    for job in jobs:
        url = job.get("job_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)
        elif not url:
            # Keep jobs without a URL (rare, but don't drop data)
            unique_jobs.append(job)

    logger.info(
        "scrape_pracuj step: %d total -> %d unique jobs",
        len(jobs),
        len(unique_jobs),
    )

    # Merge with any existing scraped_jobs already in context
    existing: list[dict] = context.get("scraped_jobs", [])
    existing_urls = {j.get("job_url") for j in existing if j.get("job_url")}

    for job in unique_jobs:
        url = job.get("job_url", "")
        if url and url not in existing_urls:
            existing.append(job)
            existing_urls.add(url)
        elif not url:
            existing.append(job)

    context["scraped_jobs"] = existing
