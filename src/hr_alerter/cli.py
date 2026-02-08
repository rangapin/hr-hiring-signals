"""Click CLI for hr-alerter.

Commands:
    scrape   -- Scrape job boards for HR postings.
    score    -- Run the scoring engine on stored companies.
    report   -- Generate and send the weekly report.
    pipeline -- Invoke a full pypyr pipeline (daily / weekly).
"""

from __future__ import annotations

import os
import logging

import click
from dotenv import load_dotenv

from hr_alerter import DEFAULT_DB_PATH

logger = logging.getLogger("hr_alerter.cli")


def _resolve_db_path(ctx_db: str | None) -> str:
    """Return the database path from --db flag, env var, or default."""
    if ctx_db:
        return ctx_db
    env_path = os.environ.get("HR_ALERTER_DB")
    if env_path:
        return env_path
    return DEFAULT_DB_PATH


def _ensure_db_dir(db_path: str) -> None:
    """Create parent directory for the database file if it does not exist."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)


@click.group()
@click.option(
    "--db",
    default=None,
    envvar="HR_ALERTER_DB",
    help="Path to the SQLite database file.",
)
@click.pass_context
def main(ctx: click.Context, db: str | None) -> None:
    """hr-alerter: Polish HR Job Market monitoring tool."""
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = _resolve_db_path(db)


@main.command()
@click.option(
    "--pages",
    default=1,
    show_default=True,
    type=int,
    help="Number of result pages to scrape per keyword.",
)
@click.option(
    "--keyword",
    default="HR",
    show_default=True,
    help="Search keyword for job boards.",
)
@click.option(
    "--source",
    default="nofluff",
    show_default=True,
    type=click.Choice(["nofluff", "pracuj", "all"]),
    help="Which job board to scrape.",
)
@click.pass_context
def scrape(ctx: click.Context, pages: int, keyword: str, source: str) -> None:
    """Scrape Polish job boards for HR postings."""
    from hr_alerter.db.manager import get_connection, init_db, insert_jobs

    db_path = ctx.obj["db_path"]
    _ensure_db_dir(db_path)

    conn = get_connection(db_path)
    init_db(conn)

    all_jobs: list[dict] = []

    # NoFluffJobs (API-based, reliable)
    if source in ("nofluff", "all"):
        click.echo(click.style("Scraping NoFluffJobs API...", fg="cyan"))
        try:
            from hr_alerter.scrapers.nofluff import NoFluffScraper

            nf = NoFluffScraper()
            nf_jobs = nf.scrape(keywords=[keyword], max_pages=pages)
            all_jobs.extend(nf_jobs)
            click.echo(f"  NoFluffJobs: {len(nf_jobs)} HR jobs found")
        except Exception as exc:
            logger.error("NoFluffJobs scraping failed: %s", exc)
            click.echo(click.style(f"  NoFluffJobs error: {exc}", fg="red"))

    # Pracuj.pl (Playwright-based, may be blocked by Cloudflare)
    if source in ("pracuj", "all"):
        click.echo(
            click.style(
                f"Scraping Pracuj.pl for '{keyword}' (pages={pages})...",
                fg="cyan",
            )
        )
        try:
            from hr_alerter.scrapers.pracuj import PracujScraper

            pracuj = PracujScraper()
            pracuj_jobs = pracuj.scrape(keywords=[keyword], max_pages=pages)
            all_jobs.extend(pracuj_jobs)
            click.echo(f"  Pracuj.pl: {len(pracuj_jobs)} jobs found")
        except Exception as exc:
            logger.error("Pracuj.pl scraping failed: %s", exc)
            click.echo(click.style(f"  Pracuj.pl error: {exc}", fg="red"))

    if all_jobs:
        inserted = insert_jobs(conn, all_jobs)
        click.echo(
            click.style(
                f"Done. {len(all_jobs)} jobs found, {inserted} new jobs inserted.",
                fg="green",
            )
        )
    else:
        click.echo(click.style("No jobs returned by scrapers.", fg="yellow"))

    conn.close()


@main.command()
@click.pass_context
def score(ctx: click.Context) -> None:
    """Run scoring engine on all companies with recent postings."""
    from hr_alerter.db.manager import (
        get_connection,
        init_db,
        save_signal,
    )
    from hr_alerter.scoring.composite import calculate_final_score

    db_path = ctx.obj["db_path"]
    _ensure_db_dir(db_path)

    conn = get_connection(db_path)
    init_db(conn)

    # Find companies with postings linked via company_id
    rows = conn.execute(
        """
        SELECT company_id, COUNT(*) AS posting_count
        FROM job_postings
        WHERE company_id IS NOT NULL
          AND post_date >= date('now', '-90 days')
          AND is_relevant = 1
        GROUP BY company_id
        HAVING COUNT(*) >= 1
        ORDER BY posting_count DESC
        """
    ).fetchall()
    click.echo(f"Scoring {len(rows)} companies...")

    hot = warm = cold = 0
    for company in rows:
        company_id = company["company_id"]
        result = calculate_final_score(conn, company_id)

        save_signal(conn, result)

        temp = result.get("lead_temperature", "cold")
        if temp == "hot":
            hot += 1
        elif temp == "warm":
            warm += 1
        else:
            cold += 1

    conn.close()

    click.echo(
        click.style(f"Hot: {hot}", fg="red")
        + " | "
        + click.style(f"Warm: {warm}", fg="yellow")
        + " | "
        + click.style(f"Cold: {cold}", fg="blue")
    )


@main.command()
@click.option(
    "--recipient",
    default=None,
    envvar="RECIPIENT_EMAIL",
    help="Email address of the report recipient.",
)
@click.pass_context
def report(ctx: click.Context, recipient: str | None) -> None:
    """Generate and send the weekly email report."""
    import datetime
    from hr_alerter.db.manager import get_connection, init_db
    from hr_alerter.reporting.composer import compose_weekly_report
    from hr_alerter.reporting.sender import send_email

    if not recipient:
        recipient = os.environ.get("RECIPIENT_EMAIL")
    if not recipient:
        click.echo(
            click.style(
                "Error: --recipient or RECIPIENT_EMAIL env var required.",
                fg="red",
            )
        )
        raise SystemExit(1)

    db_path = ctx.obj["db_path"]
    _ensure_db_dir(db_path)

    conn = get_connection(db_path)
    init_db(conn)

    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    click.echo(
        click.style(
            f"Generating report for {week_start} to {week_end}...",
            fg="cyan",
        )
    )

    report_data = compose_weekly_report(conn)
    conn.close()

    click.echo(
        f"Report: {report_data['hot_count']} hot, "
        f"{report_data['warm_count']} warm signals."
    )

    success = send_email(
        recipient=recipient,
        subject=report_data["subject"],
        html_body=report_data["html_body"],
    )
    if success:
        click.echo(click.style(f"Report sent to {recipient}.", fg="green"))
    else:
        click.echo(
            click.style(
                "Failed to send email. Check SMTP credentials.", fg="red"
            )
        )


@main.command()
@click.argument("name", type=click.Choice(["daily", "weekly"]))
@click.pass_context
def pipeline(ctx: click.Context, name: str) -> None:
    """Run a full pypyr pipeline (daily or weekly)."""
    from pypyr import pipelinerunner
    from hr_alerter import PACKAGE_DIR

    db_path = ctx.obj["db_path"]
    _ensure_db_dir(db_path)

    pipelines_dir = str(PACKAGE_DIR / "pipelines")

    pipeline_map = {
        "daily": "daily_scrape",
        "weekly": "weekly_report",
    }

    pipeline_name = pipeline_map[name]
    click.echo(
        click.style(f"Running pipeline: {pipeline_name}", fg="cyan")
    )

    try:
        pipelinerunner.main(
            pipeline_name=pipeline_name,
            working_dir=pipelines_dir,
            groups=None,
            dict_in={"db_path": db_path},
        )
        click.echo(
            click.style(f"Pipeline '{pipeline_name}' completed.", fg="green")
        )
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        click.echo(
            click.style(f"Pipeline failed: {exc}", fg="red")
        )
        raise SystemExit(1)
