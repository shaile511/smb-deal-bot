"""One test per row of "The rules" in the README, with the exact values typed out by hand."""

from datetime import date, timedelta

import pytest

from account_watch import rules

TODAY = date(2026, 11, 1)


def plan_days(**services):
    s = {"internet": False, "phone": False, "mobile": False, **services}
    return [(key, (due - TODAY).days) for key, _, due in rules.onboarding_plan(TODAY, s["internet"], s["phone"],
                                                                              s["mobile"], TODAY)]


def test_onboarding_steps_and_days_with_every_service():
    assert plan_days(internet=True, phone=True, mobile=True) == [
        ("welcome", 2), ("mobile", 7), ("internet", 10), ("porting", 14), ("training", 21), ("checkin", 30)]


def test_onboarding_skips_steps_for_services_not_bought():
    assert plan_days() == [("welcome", 2), ("training", 21), ("checkin", 30)]
    assert plan_days(phone=True) == [("welcome", 2), ("porting", 14), ("training", 21), ("checkin", 30)]


@pytest.mark.parametrize("closed_days_ago, has_plan", [(0, True), (90, True), (91, False), (700, False)])
def test_onboarding_only_for_accounts_closed_within_90_days(closed_days_ago, has_plan):
    closed = TODAY - timedelta(days=closed_days_ago)
    assert bool(rules.onboarding_plan(closed, True, True, True, TODAY)) is has_plan


@pytest.mark.parametrize("due_offset, done, overdue", [(-1, False, True), (0, False, False), (1, False, False),
                                                       (-5, True, False)])
def test_overdue_means_past_due_and_not_done(due_offset, done, overdue):
    assert rules.is_overdue(TODAY + timedelta(days=due_offset), TODAY if done else None, TODAY) is overdue


def score(overdue=0, tickets=0, usage=0, last_contact_days=None):
    last = None if last_contact_days is None else TODAY - timedelta(days=last_contact_days)
    return rules.health(overdue, tickets, usage, last, TODAY)


def test_health_starts_at_100():
    h = score()
    assert (h.score, h.band, h.reasons) == (100, "Healthy", ["No warning signs"])


@pytest.mark.parametrize("overdue, points", [(1, 85), (2, 70), (3, 55), (4, 55), (6, 55)])
def test_overdue_steps_cost_15_each_capped_at_45(overdue, points):
    assert score(overdue=overdue).score == points


@pytest.mark.parametrize("tickets, points", [(0, 100), (2, 100), (3, 90), (5, 90), (6, 75), (40, 75)])
def test_ticket_bands(tickets, points):
    assert score(tickets=tickets).score == points


@pytest.mark.parametrize("usage, points", [(0, 100), (-9, 100), (-10, 90), (-29, 90), (-30, 75), (-100, 75), (50, 100)])
def test_usage_drop_bands(usage, points):
    assert score(usage=usage).score == points


@pytest.mark.parametrize("days, points", [(None, 100), (0, 100), (90, 100), (91, 90), (400, 90)])
def test_no_contact_for_more_than_90_days(days, points):
    assert score(last_contact_days=days).score == points


def test_everything_at_once_never_goes_below_zero():
    h = score(overdue=6, tickets=9, usage=-80, last_contact_days=200)
    assert h.score == 0 and h.band == "At risk"
    assert h.reasons == ["-45: 6 onboarding steps overdue", "-25: 9 support tickets in the last 90 days",
                         "-25: usage down 80% on the previous 90 days", "-10: no contact for 200 days"]


@pytest.mark.parametrize("points, band", [(100, "Healthy"), (75, "Healthy"), (74, "Watch"), (50, "Watch"),
                                          (49, "At risk"), (0, "At risk")])
def test_bands(points, band):
    assert rules.band_for(points) == band


@pytest.mark.parametrize("usage, upsell", [(19, None), (20, "Usage up 20%: offer a bigger plan"), (60, "Usage up 60%: offer a bigger plan")])
def test_upsell_signal_from_usage_growth(usage, upsell):
    assert score(usage=usage).upsell == upsell


@pytest.mark.parametrize("days_left, milestone", [(120, None), (91, None), (90, 90), (61, 90), (60, 60), (31, 60),
                                                  (30, 30), (0, 30), (-45, 30)])
def test_renewal_milestones(days_left, milestone):
    assert rules.renewal_milestone(TODAY + timedelta(days=days_left), TODAY) == milestone


@pytest.mark.parametrize("stage, milestone, act", [(None, None, False), (None, 90, True), (None, 30, True),
                                                   (90, 90, False), (90, 60, True), (60, 30, True), (30, 30, False),
                                                   (30, 60, False)])
def test_raised_once_then_escalated_at_tighter_milestones(stage, milestone, act):
    assert rules.needs_renewal_action(stage, milestone) is act


@pytest.mark.parametrize("band, milestone, priority", [
    ("At risk", 90, 1), ("At risk", 60, 1), ("At risk", 30, 1),
    ("Watch", 90, 2), ("Watch", 60, 2), ("Watch", 30, 1),
    ("Healthy", 90, 3), ("Healthy", 60, 3), ("Healthy", 30, 2),
])
def test_linear_priority_from_health_and_milestone(band, milestone, priority):
    assert rules.renewal_priority(band, milestone) == priority


def test_ranking_closest_milestone_then_weakest_health_then_days_left():
    rows = {"60-day weak": (60, 40, 50), "30-day strong": (30, 100, 5), "30-day weak": (30, 40, 25),
            "30-day weak, sooner": (30, 40, 10), "90-day weakest": (90, 0, 80)}
    order = sorted(rows, key=lambda k: rules.renewal_rank_key(*rows[k]))
    assert order == ["30-day weak, sooner", "30-day weak", "30-day strong", "60-day weak", "90-day weakest"]
