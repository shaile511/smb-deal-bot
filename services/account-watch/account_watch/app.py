"""Account Watch: onboarding checklists, account health and renewal reminders for a book of SMB accounts."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from account_watch import digest, importer, rules, sample, store, watch  # noqa: E402
from account_watch.linear import LinearError, client_from_env  # noqa: E402

load_dotenv()
st.set_page_config(page_title="Account Watch", page_icon="📋", layout="wide")


@st.cache_resource
def shared_engine():
    return store.get_engine()


SHARED_DB = store.has_configured_db()


def engine():
    """The cluster shares one database with the CronJobs. The public demo has none, so each visitor
    gets a private in-memory book, loaded with the sample accounts on the first visit."""
    if SHARED_DB:
        return shared_engine()
    if "engine" not in st.session_state:
        st.session_state.engine = store.memory_engine()
        store.add_accounts(st.session_state.engine, sample.book(date.today()), date.today())
    return st.session_state.engine


def md(text: str) -> str:
    """Escape dollar signs, which Streamlit markdown would otherwise read as LaTeX."""
    return text.replace("$", "\\$")


linear = client_from_env()
webhook = digest.webhook_from_env()

st.title("Account Watch")
st.caption(f"After the deal closes: onboarding checklists, account health with reasons, and renewal reminders "
           f"at {', '.join(str(m) for m in rules.RENEWAL_MILESTONES)} days, for **{sample.PROVIDER}** (a made-up provider).")
missing = [name for name, ok in (("Linear", linear is not None), ("Slack", webhook is not None)) if not ok]
if missing:
    st.info(f"Demo mode: no {' or '.join(missing)} key, so "
            + ("reminders are recorded in this app instead of Linear" if linear is None else "reminders go to Linear")
            + (" and the weekly digest is shown here instead of posted to Slack." if webhook is None else "."))
if not SHARED_DB:
    st.caption("This sample book is private to this browser tab and resets when you close it.")

today = st.columns([1, 3])[0].date_input("Pretend today is", date.today(), min_value=date.today() - timedelta(days=365),
                      max_value=date.today() + timedelta(days=730),
                      help="Jump ahead to watch steps go overdue and renewals reach their milestones.")

# Accounts
with st.expander("Add accounts", expanded=store.count_accounts(engine()) == 0):
    if store.count_accounts(engine()) == 0 and st.button("Load the sample book", type="primary"):
        saved, _ = store.add_accounts(engine(), sample.book(today), today)
        st.success(f"Loaded {len(saved)} made-up accounts.")
        st.rerun()
    upload = st.file_uploader("Or import a CSV of accounts", type=["csv"],
                              help=f"Columns: {', '.join(importer.REQUIRED)}, and optionally {', '.join(importer.OPTIONAL)}.")
    st.download_button("Download a CSV template", importer.TEMPLATE, file_name="accounts-template.csv", mime="text/csv")
    if upload is not None and st.button("Import these accounts"):
        try:
            saved, skipped = store.add_accounts(engine(), importer.parse(upload.getvalue()), today)
            st.success(f"Imported {len(saved)} accounts" + (f", skipped {skipped} already in the book." if skipped else "."))
        except importer.ImportProblem as exc:
            st.error("Nothing was imported. Fix these and try again:\n\n" + "\n".join(f"- {p}" for p in exc.problems))

views = watch.book(engine(), today)
if not views:
    st.stop()
by_band = {b: sum(v.health.band == b for v in views) for b in ("Healthy", "Watch", "At risk")}
due = watch.renewals(views)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Accounts", len(views))
c2.metric("Renewing within 90 days", len(due))
c3.metric("At risk", by_band["At risk"])
c4.metric("Onboarding steps overdue", sum(len(v.overdue) for v in views))

# 1. Renewals
st.header("1. Renewals, most urgent first")
if due:
    st.dataframe([{"Account": v.code, "Company": v.account["company"], "Renews": v.account["contract_end"],
                   "When": watch.when(v.days_left), "Milestone": f"{v.milestone} days",
                   "Health": v.health.score, "Band": v.health.band,
                   "Linear priority": {1: "Urgent", 2: "High", 3: "Medium"}[rules.renewal_priority(v.health.band, v.milestone)],
                   "Raised": f"{v.account['renewal_stage']}-day" if v.account["renewal_stage"] else "not yet",
                   "Linear": v.account["renewal_linear_identifier"] or ""} for v in due],
                 use_container_width=True, hide_index=True)
else:
    st.caption("No renewals in the next 90 days.")

# 2. Health
st.header("2. Account health")
st.dataframe([{"Account": v.code, "Company": v.account["company"], "Health": v.health.score, "Band": v.health.band,
               "Why": "; ".join(v.health.reasons), "Upsell": v.health.upsell or "",
               "Monthly": f"${v.account['monthly_value']:,.2f}", "Renews": v.account["contract_end"]}
              for v in sorted(views, key=lambda v: (v.health.score, v.code))],
             use_container_width=True, hide_index=True)

# 3. Onboarding
st.header("3. Onboarding")
all_steps = store.list_steps(engine())
open_accounts = sorted({s["account_id"] for s in all_steps if s["done_on"] is None})
if not open_accounts:
    st.caption("Every onboarding checklist is done.")
for account_id in open_accounts:
    account_steps = [s for s in all_steps if s["account_id"] == account_id]
    first = account_steps[0]
    late = sum(rules.is_overdue(s["due_on"], s["done_on"], today) for s in account_steps)
    with st.expander(f"{first['code']} {first['company']}: {sum(s['done_on'] is not None for s in account_steps)} "
                     f"of {len(account_steps)} done" + (f", {late} overdue" if late else ""), expanded=bool(late)):
        for s in account_steps:
            left, mid, right = st.columns([3, 2, 1])
            state = ("done " + str(s["done_on"]) if s["done_on"] else
                     "overdue" if rules.is_overdue(s["due_on"], s["done_on"], today) else "due")
            left.markdown(f"{'~~' if s['done_on'] else ''}{s['name']}{'~~' if s['done_on'] else ''}")
            mid.caption(f"Due {s['due_on']} · {state}" + (f" · {s['linear_identifier']}" if s["linear_identifier"] else ""))
            if s["done_on"] is None and right.button("Done", key=f"done-{s['id']}"):
                try:
                    closed = watch.complete_step(engine(), s["id"], today, linear)
                    st.toast(f"{s['name']} done" + (", Linear issue closed." if closed else "."))
                    st.rerun()
                except LinearError as exc:
                    st.error(str(exc))

# 4. Daily check
st.header("4. Daily check")
st.caption("What the daily CronJob does: flag newly overdue onboarding steps, and raise or escalate renewals "
           "that reached a milestone. Each is done once.")
if st.button("Run the daily check", type="primary"):
    try:
        done = watch.run_daily(engine(), today, linear)
        st.session_state.daily = done
        st.rerun()
    except LinearError as exc:
        st.error(str(exc))
if "daily" in st.session_state:
    done = st.session_state.daily
    if done:
        st.success(f"{len(done)} reminder(s)" + (" sent to Linear." if linear else " recorded here."))
        st.dataframe([{"What": d["kind"], "Account": d["code"], "Reminder": d["title"],
                       "Linear": d["identifier"] or ""} for d in done], use_container_width=True, hide_index=True)
    else:
        st.caption("Nothing new since the last check. Move the date ahead to see more.")

# 5. Weekly digest
st.header("5. Weekly digest")
text = digest.build(engine(), today)
st.code(text, language=None)
if webhook and st.button("Send to Slack"):
    try:
        digest.send(webhook, text)
        st.success("Posted to Slack.")
    except digest.SlackError as exc:
        st.error(str(exc))
