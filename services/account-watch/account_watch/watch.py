"""The book of accounts as the rep sees it, and the daily check the CronJob runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.engine import Engine

from . import rules, store
from .linear import LinearClient

FOOTER = "\n\n_Created by Account Watch (portfolio demo, made-up data)._"


@dataclass
class AccountView:
    account: dict
    health: rules.Health
    overdue: list[dict]
    days_left: int
    milestone: int | None

    @property
    def code(self) -> str:
        return self.account["code"]


def book(engine: Engine, today: date) -> list[AccountView]:
    """Every account with its health, overdue steps and renewal milestone as of `today`."""
    steps_by_account: dict[int, list[dict]] = {}
    for s in store.list_steps(engine):
        steps_by_account.setdefault(s["account_id"], []).append(s)
    views = []
    for a in store.list_accounts(engine):
        overdue = [s for s in steps_by_account.get(a["id"], []) if rules.is_overdue(s["due_on"], s["done_on"], today)]
        h = rules.health(len(overdue), a["tickets_90d"], a["usage_change_pct"], a["last_contact_on"], today)
        views.append(AccountView(a, h, overdue, rules.days_left(a["contract_end"], today),
                                 rules.renewal_milestone(a["contract_end"], today)))
    return views


def renewals(views: list[AccountView]) -> list[AccountView]:
    """Accounts within 90 days of renewal, closest milestone first, then weakest health."""
    due = [v for v in views if v.milestone is not None]
    return sorted(due, key=lambda v: rules.renewal_rank_key(v.milestone, v.health.score, v.days_left))


def when(days: int) -> str:
    if days < 0:
        return f"ended {-days} days ago, now month to month"
    if days == 0:
        return "ends today"
    return f"in {days} days"


def renewal_title(v: AccountView) -> str:
    return f"Renewal {v.milestone}-day check: {v.account['company']} ({v.code})"


def renewal_description(v: AccountView) -> str:
    a = v.account
    lines = [f"**{a['company']}** ({v.code}) renews on {a['contract_end']} ({when(v.days_left)}).",
             f"Monthly value: ${a['monthly_value']:,.2f}.", "",
             f"**Health {v.health.score}/100, {v.health.band}**"]
    lines += [f"- {r}" for r in v.health.reasons]
    if v.health.upsell:
        lines += ["", f"**Upsell:** {v.health.upsell}"]
    if a["contact_name"] or a["contact_email"]:
        lines += ["", f"Contact: {a['contact_name']} {a['contact_email']}".rstrip()]
    return "\n".join(lines) + FOOTER


def step_title(step: dict) -> str:
    return f"Overdue onboarding: {step['name']} for {step['company']} ({step['code']})"


def step_description(step: dict, today: date) -> str:
    late = (today - step["due_on"]).days
    return (f"**{step['name']}** for {step['company']} ({step['code']}) was due {step['due_on']}, "
            f"{late} day{'s' if late != 1 else ''} ago. Tick it off in Account Watch when it is done, "
            "and this issue closes." + FOOTER)


def run_daily(engine: Engine, today: date, linear: LinearClient | None = None,
              dry_run: bool = False) -> list[dict]:
    """Flag newly overdue onboarding steps and renewals that reached a milestone.

    With a Linear client each becomes (or escalates) a Linear issue; without one they are recorded
    in the app only. Each Linear call happens before the local record, so if Linear fails part
    way, the rest are retried on the next run. With dry_run nothing is written or sent.
    """
    done = []
    for s in store.list_steps(engine):
        if s["raised_on"] is None and rules.is_overdue(s["due_on"], s["done_on"], today):
            item = {"kind": "overdue step", "code": s["code"], "title": step_title(s), "identifier": None, "url": None}
            if not dry_run:
                issue = linear.create_issue(step_title(s), step_description(s, today), s["due_on"], 2) if linear else None
                store.mark_step_raised(engine, s["id"], today, *(
                    (issue["id"], issue["identifier"], issue["url"]) if issue else (None, None, None)))
                if issue:
                    item.update(identifier=issue["identifier"], url=issue["url"])
            done.append(item)
    for v in renewals(book(engine, today)):
        a = v.account
        if not rules.needs_renewal_action(a["renewal_stage"], v.milestone):
            continue
        priority = rules.renewal_priority(v.health.band, v.milestone)
        # Escalate the existing reminder; or, if it was only recorded in the app (no Linear key at
        # the time), create the Linear issue now.
        escalate = a["renewal_stage"] is not None and (bool(a["renewal_linear_id"]) or linear is None)
        item = {"kind": "renewal escalated" if escalate else "renewal", "code": v.code, "title": renewal_title(v),
                "priority": priority, "identifier": a["renewal_linear_identifier"], "url": a["renewal_linear_url"]}
        if not dry_run:
            issue = None
            if linear and escalate:
                note = (f"Now at the {v.milestone}-day mark ({when(v.days_left)}). "
                        f"Health {v.health.score}/100, {v.health.band}: " + "; ".join(v.health.reasons) + ".")
                linear.escalate(a["renewal_linear_id"], renewal_title(v), priority, note)
            elif linear:
                issue = linear.create_issue(renewal_title(v), renewal_description(v), a["contract_end"], priority)
                item.update(identifier=issue["identifier"], url=issue["url"])
            store.set_renewal(engine, a["id"], v.milestone, *(
                (issue["id"], issue["identifier"], issue["url"]) if issue else ()))
        done.append(item)
    return done


def complete_step(engine: Engine, step_id: int, today: date, linear: LinearClient | None = None) -> bool:
    """Tick off an onboarding step. Its Linear issue is closed first, so a Linear failure leaves the
    step open and the rep can retry. Returns True if a Linear issue was closed."""
    step = store.get_step(engine, step_id)
    closed = False
    if step["done_on"] is not None:
        return False
    if linear and step["linear_id"]:
        linear.complete(step["linear_id"], "Done: ticked off in Account Watch.")
        closed = True
    store.mark_step_done(engine, step_id, today)
    return closed
