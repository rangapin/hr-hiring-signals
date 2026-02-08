"""pypyr step: scrape NoFluffJobs for HR job postings.

Reads ``max_pages`` from the pypyr context (default 1), runs the
:class:`NoFluffScraper`, and stores the results in
``context['scraped_jobs_nofluff']``.

If playwright is not installed the step logs a warning and sets the
context key to an empty list so the pipeline can continue.
"""

import logging

logger = logging.getLogger(__name__)


def run_step(context: dict) -> None:
    """pypyr entry-point for the NoFluffJobs scrape step.

    Context keys read:
        max_pages (int): Number of listing pages to scrape.  Default ``1``.

    Context keys written:
        scraped_jobs_nofluff (list[dict]): Job postings scraped from
            NoFluffJobs, conforming to the ``job_posting_dict`` contract.
    """
    max_pages: int = context.get("max_pages", 1)

    try:
        from hr_alerter.scrapers.nofluff import NoFluffScraper
    except ImportError:
        logger.warning(
            "Could not import NoFluffScraper (playwright likely not installed). "
            "Skipping NoFluffJobs scrape."
        )
        context["scraped_jobs_nofluff"] = []
        return

    try:
        scraper = NoFluffScraper()
        jobs = scraper.scrape(max_pages=max_pages)
        logger.info("NoFluffJobs scrape returned %d jobs.", len(jobs))
    except Exception:
        logger.exception(
            "NoFluffJobs scrape failed unexpectedly. "
            "Storing empty result so the pipeline can continue."
        )
        jobs = []

    context["scraped_jobs_nofluff"] = jobs
