"""Scrapers sub-package -- job board scraping infrastructure.

Public API
----------
- :class:`PracujScraper` -- Pracuj.pl job board scraper
- :func:`normalize_company_name` -- strip Polish legal suffixes
- :func:`parse_polish_date` -- parse Polish-language date strings
"""

from hr_alerter.scrapers.pracuj import PracujScraper
from hr_alerter.scrapers.utils import normalize_company_name, parse_polish_date

__all__ = [
    "PracujScraper",
    "normalize_company_name",
    "parse_polish_date",
]
