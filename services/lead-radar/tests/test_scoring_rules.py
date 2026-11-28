"""One test per row of "How scoring works" in the README, with exact points typed out by hand."""

from datetime import date

import pandas as pd
import pytest

from lead_radar import cli
from lead_radar.generate import NO_BUSINESS_PLAN
from lead_radar.scoring import check_leads, months_until, score_lead

TODAY = date(2026, 11, 1)


def lead(**overrides):
    base = {"company": "Test Co", "contact_name": "Ana", "city": "Halifax", "industry": "Dental clinic",
            "employees": 25, "locations": 2, "current_provider": "Bluepeak Telecom", "contract_end": "2027-02"}
    return {**base, **overrides}


def points(reason_start, **overrides):
    """Points from the one reason that starts with `reason_start`'s part (size, sites, ...)."""
    s = score_lead(lead(**overrides), TODAY)
    reason = next(r for r in s.reasons if reason_start in r)
    return int(reason.split()[0])


@pytest.mark.parametrize("staff, pts", [(1, 5), (4, 5), (5, 12), (19, 12), (20, 20), (49, 20), (50, 14), (400, 14)])
def test_staff_size_points(staff, pts):
    assert points("staff", employees=staff) == pts


@pytest.mark.parametrize("sites, pts", [(1, 5), (2, 15), (3, 15), (4, 20), (12, 20)])
def test_location_points(sites, pts):
    assert points("location", locations=sites) == pts


@pytest.mark.parametrize("industry, pts", [("Dental clinic", 20), ("Law office", 18), ("Real estate agency", 18),
                                           ("Accounting firm", 16), ("Retail store", 15), ("Restaurant", 12),
                                           ("Auto repair", 10), ("Fitness studio", 10), ("Construction", 8),
                                           ("Salon", 6), ("Bakery", 8)])
def test_industry_points(industry, pts):
    assert points("fits the bundle", industry=industry) == pts


@pytest.mark.parametrize("end, pts", [
    ("2026-10", 20),   # already ended
    ("2026-11", 25),   # this month
    ("2026-12", 25),   # 1 month
    ("2027-01", 40),   # 2 months: best window starts
    ("2027-03", 40),   # 4 months: best window ends
    ("2027-04", 25),   # 5 months
    ("2027-05", 25),   # 6 months
    ("2027-06", 10),   # 7 months
    ("2027-11", 10),   # 12 months
    ("2027-12", 0),    # 13 months
])
def test_timing_points(end, pts):
    assert points("ontract", contract_end=end) == pts


def test_consumer_plan_scores_30_for_timing():
    s = score_lead(lead(current_provider=NO_BUSINESS_PLAN, contract_end=""), TODAY)
    assert s.reasons[-1] == f"+30 On a {NO_BUSINESS_PLAN.lower()}, can switch any time"
    assert s.total == 20 + 15 + 20 + 30


def test_unknown_contract_end_is_not_called_a_consumer_plan():
    s = score_lead(lead(industry="Law office", contract_end=""), TODAY)
    assert s.reasons[-1] == "+15 Contract end unknown: ask on the first call"
    assert s.total == 20 + 15 + 18 + 15
    # Knowing the end is 6 months out should not score lower than not knowing it at all... by much.
    assert score_lead(lead(industry="Law office", contract_end="2027-05"), TODAY).total > s.total


@pytest.mark.parametrize("value, months", [("2027-02", 3), ("2027-02-15", 3), ("2027/2", 3), ("02/2027", 3),
                                           ("2/2027", 3), ("", None), (None, None)])
def test_contract_end_formats(value, months):
    assert months_until(value, TODAY) == months


def test_bad_csv_gives_plain_messages():
    bad = pd.DataFrame([lead(contract_end="next spring"), lead(employees="lots")])
    problems = check_leads(bad)
    assert problems == ["Line 2: contract end 'next spring' is not a date like 2027-02 or 02/2027.",
                        "Line 3: employees 'lots' is not a number."]
    missing = check_leads(pd.DataFrame([{"company": "X"}]))
    assert missing[0].startswith("Missing column(s): contact_name")
    assert check_leads(pd.DataFrame([lead(), lead(contract_end="2027-02-15")])) == []


def test_dry_run_spends_no_claude_credits(monkeypatch, capsys):
    monkeypatch.setenv("LINEAR_API_KEY", "set")
    monkeypatch.setattr(cli, "draft_email", lambda lead: pytest.fail("drafted on a dry run"))
    monkeypatch.setattr("sys.argv", ["lead-radar", "--top", "3", "--dry-run"])
    cli.main()
    out = capsys.readouterr().out
    assert "no Claude credits" in out and out.count("[dry-run]") == 3
