"""Base scraper abstract class for all job board scrapers."""

import logging
import random
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Default User-Agent strings for rotation
DEFAULT_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
        "Gecko/20100101 Firefox/121.0"
    ),
]


class BaseScraper(ABC):
    """Abstract base class for all job board scrapers.

    Provides shared infrastructure for HTTP header rotation and
    rate-limit delays.  Concrete subclasses must implement ``scrape``.
    """

    def __init__(self, user_agents: list[str] | None = None) -> None:
        self.user_agents = user_agents or DEFAULT_USER_AGENTS
        self._ua_index = 0

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def scrape(self, keywords: list[str], max_pages: int = 1) -> list[dict]:
        """Scrape the job board for the given *keywords*.

        Args:
            keywords: Search terms to query.
            max_pages: Maximum number of result pages to fetch per keyword.

        Returns:
            A list of dicts conforming to the ``job_posting_dict`` contract.
        """
        ...

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def get_headers(self) -> dict:
        """Return HTTP headers with a rotated User-Agent.

        Each call cycles through the configured User-Agent list
        round-robin and includes headers that mimic a real browser.
        """
        ua = self.user_agents[self._ua_index % len(self.user_agents)]
        self._ua_index += 1
        return {
            "User-Agent": ua,
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;"
                "q=0.8,application/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

    @staticmethod
    def rate_limit_delay(min_sec: float = 2, max_sec: float = 4) -> None:
        """Sleep for a random duration between *min_sec* and *max_sec*.

        This is called between HTTP requests to avoid overwhelming the
        target server.
        """
        delay = random.uniform(min_sec, max_sec)
        logger.debug("Rate-limit delay: %.2f s", delay)
        time.sleep(delay)
