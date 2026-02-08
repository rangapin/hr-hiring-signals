"""Unit tests for the scrapers package.

All tests are pure-unit -- NO network calls are made.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from hr_alerter.scrapers.utils import (
    detect_seniority,
    normalize_company_name,
    parse_polish_date,
)


# ======================================================================
# normalize_company_name
# ======================================================================


class TestNormalizeCompanyName:
    """Test company-name normalisation (5+ cases from docs.md Sec 4.4)."""

    def test_sp_z_oo(self):
        result = normalize_company_name("Samsung Electronics Polska Sp. z o.o.")
        assert result == "Samsung Electronics Polska"

    def test_sa(self):
        result = normalize_company_name("Allegro S.A.")
        assert result == "Allegro"

    def test_sp_z_o_o_spaced(self):
        result = normalize_company_name("Firma Testowa Sp. z o. o.")
        assert result == "Firma Testowa"

    def test_spolka_z_ograniczona(self):
        result = normalize_company_name(
            "ABC Corp Spółka z ograniczoną odpowiedzialnością"
        )
        assert result == "ABC Corp"

    def test_spolka_akcyjna(self):
        result = normalize_company_name("Bank Polski Spółka Akcyjna")
        assert result == "Bank Polski"

    def test_no_suffix(self):
        result = normalize_company_name("Google Poland")
        assert result == "Google Poland"

    def test_empty_string(self):
        result = normalize_company_name("")
        assert result == ""

    def test_whitespace_handling(self):
        result = normalize_company_name("  Firma ABC Sp. z o.o.  ")
        assert result == "Firma ABC"


# ======================================================================
# parse_polish_date
# ======================================================================


class TestParsePolishDate:
    """Test Polish-language date parsing."""

    def test_dzisiaj(self):
        result = parse_polish_date("dzisiaj")
        assert result == datetime.date.today()

    def test_dzis(self):
        result = parse_polish_date("dziś")
        assert result == datetime.date.today()

    def test_wczoraj(self):
        result = parse_polish_date("wczoraj")
        assert result == datetime.date.today() - datetime.timedelta(days=1)

    def test_dni_temu(self):
        result = parse_polish_date("3 dni temu")
        assert result == datetime.date.today() - datetime.timedelta(days=3)

    def test_dni_temu_large(self):
        result = parse_polish_date("14 dni temu")
        assert result == datetime.date.today() - datetime.timedelta(days=14)

    def test_iso_format(self):
        result = parse_polish_date("2026-02-08")
        assert result == datetime.date(2026, 2, 8)

    def test_dot_format(self):
        result = parse_polish_date("08.02.2026")
        assert result == datetime.date(2026, 2, 8)

    def test_none_input(self):
        result = parse_polish_date(None)
        assert result is None

    def test_empty_string(self):
        result = parse_polish_date("")
        assert result is None

    def test_unparseable(self):
        result = parse_polish_date("not a date")
        assert result is None


# ======================================================================
# detect_seniority
# ======================================================================


class TestDetectSeniority:
    """Test seniority-level detection from job titles."""

    def test_director(self):
        assert detect_seniority("HR Director") == "director"

    def test_dyrektor(self):
        assert detect_seniority("Dyrektor ds. HR") == "director"

    def test_c_level(self):
        assert detect_seniority("CHRO - Chief Human Resources Officer") == "director"

    def test_senior(self):
        assert detect_seniority("Senior HR Manager") == "senior"

    def test_starszy(self):
        assert detect_seniority("Starszy Specjalista HR") == "senior"

    def test_junior(self):
        assert detect_seniority("Junior Recruiter") == "junior"

    def test_mlodszy(self):
        assert detect_seniority("Młodszy specjalista ds. kadr") == "junior"

    def test_praktykant(self):
        assert detect_seniority("Praktykant HR") == "junior"

    def test_manager(self):
        assert detect_seniority("HR Manager") == "mid"

    def test_kierownik(self):
        assert detect_seniority("Kierownik działu HR") == "mid"

    def test_no_match(self):
        assert detect_seniority("Specjalista HR") is None

    def test_none_input(self):
        assert detect_seniority(None) is None

    def test_empty_string(self):
        assert detect_seniority("") is None

    def test_case_insensitive(self):
        assert detect_seniority("hr director") == "director"
        assert detect_seniority("SENIOR RECRUITER") == "senior"


# ======================================================================
# PracujScraper -- unit tests with mocked HTTP
# ======================================================================


class TestPracujScraperJSON:
    """Test PracujScraper._parse_json with synthetic HTML."""

    def test_parse_next_data(self):
        """__NEXT_DATA__ script tag is parsed correctly."""
        from hr_alerter.scrapers.pracuj import PracujScraper
        from bs4 import BeautifulSoup

        html = """
        <html><head>
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "data": {
                        "jobOffers": {
                            "groupedOffers": [
                                {
                                    "jobTitle": "HR Manager",
                                    "companyName": "TestCorp Sp. z o.o.",
                                    "offerAbsoluteUri": "https://www.pracuj.pl/praca/hr-manager,123",
                                    "lastPublicated": "2026-02-08",
                                    "locations": [{"city": "Warszawa"}],
                                    "employmentLevel": "mid"
                                }
                            ]
                        }
                    }
                }
            }
        }
        </script>
        </head><body></body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        scraper = PracujScraper()
        jobs = scraper._parse_json(soup)

        assert len(jobs) == 1
        job = jobs[0]
        assert job["source"] == "pracuj.pl"
        assert job["job_title"] == "HR Manager"
        assert job["company_name_raw"] == "TestCorp Sp. z o.o."
        assert job["job_url"] == "https://www.pracuj.pl/praca/hr-manager,123"
        assert job["location"] == "Warszawa"

    def test_parse_application_json(self):
        """application/json script tag is parsed correctly."""
        from hr_alerter.scrapers.pracuj import PracujScraper
        from bs4 import BeautifulSoup

        html = """
        <html><head>
        <script type="application/json">
        {
            "offers": [
                {
                    "jobTitle": "Senior Recruiter",
                    "companyName": "Allegro S.A.",
                    "offerAbsoluteUri": "https://www.pracuj.pl/praca/sr-recruiter,456",
                    "locations": [{"city": "Kraków"}]
                }
            ]
        }
        </script>
        </head><body></body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        scraper = PracujScraper()
        jobs = scraper._parse_json(soup)

        assert len(jobs) == 1
        assert jobs[0]["job_title"] == "Senior Recruiter"
        assert jobs[0]["seniority_level"] == "senior"

    def test_parse_json_no_data(self):
        """Returns empty list when no JSON data exists."""
        from hr_alerter.scrapers.pracuj import PracujScraper
        from bs4 import BeautifulSoup

        html = "<html><head></head><body><p>No jobs here</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        scraper = PracujScraper()
        jobs = scraper._parse_json(soup)
        assert jobs == []


class TestPracujScraperHTML:
    """Test PracujScraper._parse_html with synthetic HTML."""

    def test_parse_listing_items(self):
        """Strategy A card selectors work."""
        from hr_alerter.scrapers.pracuj import PracujScraper
        from bs4 import BeautifulSoup

        html = """
        <html><body>
        <div class="listing__item">
            <h2 class="offer-details__title-link">
                <a href="/praca/hr-specialist,789">HR Specialist</a>
            </h2>
            <h3 class="company-name">Google Poland</h3>
            <span class="offer-labels__item--location">Warszawa</span>
            <span class="offer-labels__item--date">dzisiaj</span>
        </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        scraper = PracujScraper()
        jobs = scraper._parse_html(soup)

        assert len(jobs) == 1
        job = jobs[0]
        assert job["job_title"] == "HR Specialist"
        assert job["company_name_raw"] == "Google Poland"
        assert job["location"] == "Warszawa"
        assert job["post_date"] == datetime.date.today().isoformat()
        assert "pracuj.pl" in job["job_url"]

    def test_parse_data_test_attrs(self):
        """Strategy B data-test attributes work."""
        from hr_alerter.scrapers.pracuj import PracujScraper
        from bs4 import BeautifulSoup

        html = """
        <html><body>
        <div data-test="default-offer">
            <h2 data-test="offer-title">
                <a href="https://www.pracuj.pl/praca/test,111">Junior HR</a>
            </h2>
            <h3 data-test="text-company-name">Startup XYZ</h3>
            <span data-test="text-region">Gdańsk</span>
            <span data-test="text-added">wczoraj</span>
        </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        scraper = PracujScraper()
        jobs = scraper._parse_html(soup)

        assert len(jobs) == 1
        assert jobs[0]["job_title"] == "Junior HR"
        assert jobs[0]["seniority_level"] == "junior"

    def test_no_cards_returns_empty(self):
        """Returns empty list when no cards are found."""
        from hr_alerter.scrapers.pracuj import PracujScraper
        from bs4 import BeautifulSoup

        html = "<html><body><p>Nothing to see</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        scraper = PracujScraper()
        jobs = scraper._parse_html(soup)
        assert jobs == []


class TestPracujScraperScrapeMethod:
    """Test the top-level scrape() method with mocked HTTP."""

    @patch("hr_alerter.scrapers.pracuj.sync_playwright")
    @patch.object(
        __import__("hr_alerter.scrapers.base", fromlist=["BaseScraper"]).BaseScraper,
        "rate_limit_delay",
    )
    def test_scrape_returns_job_dicts(self, mock_delay, mock_pw):
        """scrape() returns well-formed job_posting_dict list."""
        from hr_alerter.scrapers.pracuj import PracujScraper

        html_content = """
        <html><head>
        <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"data":{"jobOffers":{"groupedOffers":[
            {
                "jobTitle": "HR Manager",
                "companyName": "Acme Sp. z o.o.",
                "offerAbsoluteUri": "https://www.pracuj.pl/praca/hr,100",
                "locations": [{"city": "Wrocław"}],
                "lastPublicated": "2026-02-07"
            }
        ]}}}}}
        </script>
        </head><body></body></html>
        """

        # Mock the Playwright chain: sync_playwright() -> pw -> chromium -> browser -> context -> page
        mock_page = MagicMock()
        mock_page.content.return_value = html_content

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium.launch.return_value = mock_browser

        mock_pw.return_value.__enter__ = MagicMock(return_value=mock_pw_instance)
        mock_pw.return_value.__exit__ = MagicMock(return_value=False)

        scraper = PracujScraper()
        jobs = scraper.scrape(keywords=["HR"], max_pages=1)

        assert len(jobs) == 1
        job = jobs[0]

        # Verify all contract fields are present
        required_keys = {
            "source", "job_url", "job_title", "company_name_raw",
            "location", "post_date", "job_description",
            "seniority_level", "employment_type",
        }
        assert set(job.keys()) == required_keys
        assert job["source"] == "pracuj.pl"
        assert job["job_title"] == "HR Manager"
        assert job["company_name_raw"] == "Acme Sp. z o.o."


# ======================================================================
# scrape_pracuj step
# ======================================================================


class TestScrapePracujStep:
    """Test the pypyr step for Pracuj.pl scraping."""

    @patch("hr_alerter.steps.scrape_pracuj.PracujScraper")
    def test_run_step_stores_jobs(self, MockScraper):
        """run_step populates context['scraped_jobs']."""
        from hr_alerter.steps.scrape_pracuj import run_step

        mock_instance = MockScraper.return_value
        mock_instance.scrape.return_value = [
            {
                "source": "pracuj.pl",
                "job_url": "https://www.pracuj.pl/praca/1",
                "job_title": "HR",
                "company_name_raw": "Test",
                "location": None,
                "post_date": None,
                "job_description": None,
                "seniority_level": None,
                "employment_type": None,
            },
            {
                "source": "pracuj.pl",
                "job_url": "https://www.pracuj.pl/praca/1",  # duplicate
                "job_title": "HR",
                "company_name_raw": "Test",
                "location": None,
                "post_date": None,
                "job_description": None,
                "seniority_level": None,
                "employment_type": None,
            },
        ]

        context: dict = {"keywords": ["HR"], "max_pages": 1}
        run_step(context)

        # Deduplication should reduce 2 -> 1
        assert len(context["scraped_jobs"]) == 1
        assert context["scraped_jobs"][0]["job_url"] == "https://www.pracuj.pl/praca/1"

    @patch("hr_alerter.steps.scrape_pracuj.PracujScraper")
    def test_run_step_graceful_failure(self, MockScraper):
        """run_step does not crash when scraper raises."""
        from hr_alerter.steps.scrape_pracuj import run_step

        mock_instance = MockScraper.return_value
        mock_instance.scrape.side_effect = RuntimeError("network down")

        context: dict = {}
        run_step(context)

        assert context["scraped_jobs"] == []
