"""Tests for the hr-alerter Click CLI."""

from click.testing import CliRunner

from hr_alerter.cli import main


def test_cli_help():
    """hr-alerter --help should exit 0 and show usage text."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_scrape_help():
    """hr-alerter scrape --help should list the --pages option."""
    runner = CliRunner()
    result = runner.invoke(main, ["scrape", "--help"])
    assert result.exit_code == 0
    assert "--pages" in result.output


def test_score_help():
    """hr-alerter score --help should exit 0."""
    runner = CliRunner()
    result = runner.invoke(main, ["score", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_report_help():
    """hr-alerter report --help should list the --recipient option."""
    runner = CliRunner()
    result = runner.invoke(main, ["report", "--help"])
    assert result.exit_code == 0
    assert "--recipient" in result.output


def test_pipeline_help():
    """hr-alerter pipeline --help should list daily and weekly choices."""
    runner = CliRunner()
    result = runner.invoke(main, ["pipeline", "--help"])
    assert result.exit_code == 0
    assert "daily" in result.output
    assert "weekly" in result.output
