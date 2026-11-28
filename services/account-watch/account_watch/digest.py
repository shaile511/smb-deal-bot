"""The weekly digest: one Slack message with what needs the rep this week."""

from __future__ import annotations

import os
from datetime import date

import requests
from sqlalchemy.engine import Engine

from . import watch

TIMEOUT = 20
TOP = 10  # longest list in any one section


class SlackError(RuntimeError):
    pass


def build(engine: Engine, today: date) -> str:
    views = watch.book(engine, today)
    due = watch.renewals(views)
    at_risk = sorted((v for v in views if v.health.band == "At risk" and v.milestone is None),
                     key=lambda v: v.health.score)
    overdue = [(v, s) for v in views for s in v.overdue]
    upsell = [v for v in views if v.health.upsell]
    lines = [f"*Account Watch weekly digest, {today:%B} {today.day}, {today.year}*",
             f"{len(views)} accounts · {len(due)} renewing within 90 days · "
             f"{sum(v.health.band == 'At risk' for v in views)} at risk · {len(overdue)} onboarding steps overdue",
             ""]

    def section(title: str, items: list[str]) -> None:
        if items:
            lines.append(f"*{title}*")
            lines.extend(f"• {i}" for i in items[:TOP])
            if len(items) > TOP:
                lines.append(f"• and {len(items) - TOP} more in the dashboard")
            lines.append("")

    section("Renewals, most urgent first", [
        f"{v.code} {v.account['company']}: {watch.when(v.days_left)}, health {v.health.score} ({v.health.band})"
        for v in due])
    section("At risk, not renewing yet", [
        f"{v.code} {v.account['company']}: health {v.health.score}. {v.health.reasons[0]}" for v in at_risk])
    section("Onboarding overdue", [
        f"{v.code} {v.account['company']}: {s['name']}, due {s['due_on']}" for v, s in overdue])
    section("Upsell signals", [f"{v.code} {v.account['company']}: {v.health.upsell}" for v in upsell])
    if len(lines) == 3:
        lines.append("Nothing needs you this week.")
    return "\n".join(lines).rstrip()


def webhook_from_env() -> str | None:
    return os.environ.get("SLACK_WEBHOOK_URL") or None


def send(webhook_url: str, text: str, session: requests.Session | None = None) -> None:
    if not webhook_url.startswith("https://"):
        raise SlackError("SLACK_WEBHOOK_URL must be an https:// Slack incoming-webhook URL.")
    session = session or requests.Session()
    try:
        resp = session.post(webhook_url, json={"text": text}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise SlackError(f"Could not reach Slack ({type(exc).__name__}). Try again.") from exc
    if resp.status_code != 200:
        raise SlackError(f"Slack did not take the message (HTTP {resp.status_code}: {resp.text[:80]}). "
                         "Check SLACK_WEBHOOK_URL.")
