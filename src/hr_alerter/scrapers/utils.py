"""Utility functions shared across all scrapers.

Includes company-name normalisation, Polish date parsing, and
seniority-level detection.
"""

import datetime
import logging
import re

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Company name normalisation
# ------------------------------------------------------------------

# Ordered longest-first so that longer suffixes are tried before their
# shorter sub-strings (e.g. "Sp. z o. o." before "Sp. z o.o.").
_LEGAL_SUFFIXES: list[str] = [
    "Spółka z ograniczoną odpowiedzialnością",
    "spółka z ograniczoną odpowiedzialnością",
    "Spółka Akcyjna",
    "spółka akcyjna",
    "Sp. z o. o.",
    "sp. z o. o.",
    "Sp. z o.o.",
    "sp. z o.o.",
    "S.A.",
    "s.a.",
]


def normalize_company_name(raw: str) -> str:
    """Strip Polish legal suffixes from a company name.

    Examples::

        >>> normalize_company_name("Samsung Electronics Polska Sp. z o.o.")
        'Samsung Electronics Polska'
        >>> normalize_company_name("Allegro S.A.")
        'Allegro'
    """
    if not raw:
        return raw

    name = raw.strip()
    for suffix in _LEGAL_SUFFIXES:
        # Use case-insensitive removal so we handle mixed-case input.
        idx = name.lower().rfind(suffix.lower())
        if idx != -1:
            name = name[:idx] + name[idx + len(suffix):]
    return name.strip().rstrip(",").strip()


# ------------------------------------------------------------------
# Polish date parsing
# ------------------------------------------------------------------

def parse_polish_date(date_str: str) -> datetime.date | None:
    """Parse a Polish-language date string into a ``datetime.date``.

    Recognised formats:

    * ``"dzisiaj"`` / ``"dziś"`` -- today
    * ``"wczoraj"``              -- yesterday
    * ``"X dni temu"``           -- *X* days ago
    * ISO format ``YYYY-MM-DD``
    * Dot-separated ``dd.mm.yyyy``

    Returns ``None`` when the string cannot be parsed.
    """
    if not date_str:
        return None

    text = date_str.strip().lower()
    today = datetime.date.today()

    # "dzisiaj" / "dziś"
    if "dzisiaj" in text or "dziś" in text or "dzis" in text:
        return today

    # "wczoraj"
    if "wczoraj" in text:
        return today - datetime.timedelta(days=1)

    # "X dni temu"
    match = re.search(r"(\d+)\s*dni\s*temu", text)
    if match:
        days = int(match.group(1))
        return today - datetime.timedelta(days=days)

    # ISO format  YYYY-MM-DD
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        pass

    # dd.mm.yyyy
    try:
        return datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        pass

    logger.warning("Could not parse date string: %r", date_str)
    return None


# ------------------------------------------------------------------
# Seniority detection
# ------------------------------------------------------------------

# Mapping of keyword patterns to seniority labels.
# Patterns are checked in order; the first match wins.
_SENIORITY_PATTERNS: list[tuple[list[str], str]] = [
    (
        ["director", "dyrektor", "c-level", "ceo", "cfo", "cto",
         "cpo", "chro", "vp ", "vice president"],
        "director",
    ),
    (
        ["senior", "starszy", "sr ", "sr."],
        "senior",
    ),
    (
        ["junior", "młodszy", "praktykant", "intern", "stażysta",
         "trainee"],
        "junior",
    ),
    (
        ["manager", "kierownik", "lead", "team lead", "head of"],
        "mid",
    ),
]


def detect_seniority(title: str) -> str | None:
    """Detect seniority level from a job title string.

    Returns one of ``'director'``, ``'senior'``, ``'junior'``,
    ``'mid'``, or ``None`` if no pattern matches.
    """
    if not title:
        return None

    lower = title.lower()

    for keywords, level in _SENIORITY_PATTERNS:
        for kw in keywords:
            if kw in lower:
                return level

    return None
