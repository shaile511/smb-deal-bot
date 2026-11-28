"""Account Watch business rules. Every number here is in the README table and pinned by a test.

Pure functions only: no database, no network. `today` is always passed in so the rules can be
tested on fixed dates and the dashboard can "pretend today is" a later day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# Onboarding checklist: (key, step, days after the deal closed, service it needs or None for all).
ONBOARDING_STEPS = (
    ("welcome", "Welcome call", 2, None),
    ("mobile", "Activate mobile lines", 7, "mobile"),
    ("internet", "Install internet", 10, "internet"),
    ("porting", "Port phone numbers", 14, "phone"),
    ("training", "Staff training", 21, None),
    ("checkin", "30-day check-in", 30, None),
)
# Accounts that closed longer ago than this are past onboarding, so no checklist is made for them.
ONBOARDING_WINDOW_DAYS = 90

# Health starts at 100 and loses points for each warning sign; it never goes below 0.
HEALTH_START = 100
OVERDUE_STEP_POINTS = 15      # per onboarding step past its due date
OVERDUE_STEP_CAP = 45         # at most this much from overdue steps
TICKET_BANDS = ((6, 25), (3, 10))   # (at least this many tickets in 90 days, points lost)
USAGE_DROP_BANDS = ((30, 25), (10, 10))  # (usage down at least this %, points lost)
NO_CONTACT_DAYS = 90          # no contact for more than this many days
NO_CONTACT_POINTS = 10
HEALTHY_FROM = 75
WATCH_FROM = 50
UPSELL_USAGE_GROWTH = 20      # usage up at least this % is an upsell signal, not a health change

# Renewal reminders. A renewal is raised once, at the first milestone it reaches, and then
# escalated at each later one. A contract that has already ended counts as the 30-day milestone
# (it is rolling month to month and can leave any time).
RENEWAL_MILESTONES = (90, 60, 30)
BAND_PRIORITY = {"At risk": 1, "Watch": 2, "Healthy": 3}  # Linear: 1 urgent, 2 high, 3 medium


@dataclass
class Health:
    score: int
    band: str
    reasons: list[str] = field(default_factory=list)
    upsell: str | None = None


def onboarding_plan(closed_on: date, internet: bool, phone: bool, mobile: bool,
                    today: date) -> list[tuple[str, str, date]]:
    """The checklist for a newly closed deal: (key, step, due date). Empty past the window."""
    if (today - closed_on).days > ONBOARDING_WINDOW_DAYS:
        return []
    services = {"internet": internet, "phone": phone, "mobile": mobile}
    return [(key, name, closed_on + timedelta(days=days)) for key, name, days, needs in ONBOARDING_STEPS
            if needs is None or services[needs]]


def is_overdue(due_on: date, done_on: date | None, today: date) -> bool:
    """Overdue means not done and the due date has passed. Due today is not overdue yet."""
    return done_on is None and due_on < today


def band_for(score: int) -> str:
    if score >= HEALTHY_FROM:
        return "Healthy"
    if score >= WATCH_FROM:
        return "Watch"
    return "At risk"


def health(overdue_steps: int, tickets_90d: int, usage_change_pct: int,
           last_contact_on: date | None, today: date) -> Health:
    """Score an account from 0 to 100 and say why. Blank last contact means unknown: no points."""
    score = HEALTH_START
    reasons = []
    if overdue_steps:
        lost = min(overdue_steps * OVERDUE_STEP_POINTS, OVERDUE_STEP_CAP)
        score -= lost
        reasons.append(f"-{lost}: {overdue_steps} onboarding step{'s' if overdue_steps > 1 else ''} overdue")
    for at_least, lost in TICKET_BANDS:
        if tickets_90d >= at_least:
            score -= lost
            reasons.append(f"-{lost}: {tickets_90d} support tickets in the last 90 days")
            break
    for at_least, lost in USAGE_DROP_BANDS:
        if -usage_change_pct >= at_least:
            score -= lost
            reasons.append(f"-{lost}: usage down {-usage_change_pct}% on the previous 90 days")
            break
    if last_contact_on is not None and (today - last_contact_on).days > NO_CONTACT_DAYS:
        score -= NO_CONTACT_POINTS
        reasons.append(f"-{NO_CONTACT_POINTS}: no contact for {(today - last_contact_on).days} days")
    score = max(0, score)
    upsell = (f"Usage up {usage_change_pct}%: offer a bigger plan"
              if usage_change_pct >= UPSELL_USAGE_GROWTH else None)
    if not reasons:
        reasons.append("No warning signs")
    return Health(score, band_for(score), reasons, upsell)


def days_left(contract_end: date, today: date) -> int:
    return (contract_end - today).days


def renewal_milestone(contract_end: date, today: date) -> int | None:
    """The tightest milestone reached (30, 60 or 90), or None if renewal is more than 90 days off."""
    left = days_left(contract_end, today)
    for milestone in sorted(RENEWAL_MILESTONES):
        if left <= milestone:
            return milestone
    return None


def renewal_priority(band: str, milestone: int) -> int:
    """Linear priority from health, one step more urgent at the 30-day milestone (never above urgent)."""
    priority = BAND_PRIORITY[band]
    if milestone == min(RENEWAL_MILESTONES):
        priority = max(1, priority - 1)
    return priority


def needs_renewal_action(stage: int | None, milestone: int | None) -> bool:
    """Raise when first reached; escalate only when a tighter milestone is reached."""
    return milestone is not None and (stage is None or milestone < stage)


def renewal_rank_key(milestone: int, score: int, left: int) -> tuple[int, int, int]:
    """Closest milestone first, then weakest health, then fewest days left."""
    return (milestone, score, left)
