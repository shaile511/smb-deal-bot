"""Quote and Follow-up Desk: call notes in, priced quote and a follow-up plan out."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from quote_desk import followups, price_book as pb, store  # noqa: E402
from quote_desk.extract import extract_needs  # noqa: E402
from quote_desk.pdf import render_pdf  # noqa: E402
from quote_desk.quote import Needs, build_quote  # noqa: E402

load_dotenv()

SAMPLE_NOTES = """Call with Priya Raman, office manager at Maple Ridge Dental (priya@mapleridge-dental.example.com).
2 clinics, about 18 staff total. Internet keeps dropping during patient check-in, they want fibre,
probably 1 gig is enough. Need 12 desk phone lines across both sites and 6 mobile plans for the
dentists, nothing fancy. They want managed wifi for the waiting rooms and a backup connection
so the booking system never goes down. Open to a 3 year term if the price is right."""

st.set_page_config(page_title="Quote Desk", page_icon="🧾", layout="wide")


@st.cache_resource
def engine():
    return store.get_engine()


def md(text: str) -> str:
    """Escape dollar signs, which Streamlit markdown would otherwise read as LaTeX."""
    return text.replace("$", "\\$")


def quote_dict(q) -> dict:
    return {
        "lines": [{"code": l.code, "description": l.description, "quantity": l.quantity,
                   "unit_price": float(l.unit_price), "monthly": float(l.monthly)} for l in q.lines],
        "adjustments": [{"label": a.label, "amount": float(a.amount)} for a in q.adjustments],
        "list_monthly": float(q.list_monthly), "monthly": float(q.monthly), "one_time": float(q.one_time),
        "term_months": q.term_months, "margin": float(q.margin),
    }


has_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
linear = followups.client_from_env()

st.title("Quote and Follow-up Desk")
st.caption(f"Paste discovery-call notes, get a priced quote for **{pb.PROVIDER}** (a made-up provider), "
           "and let the follow-ups take care of themselves.")
if not has_claude or linear is None:
    missing = [name for name, ok in (("Claude", has_claude), ("Linear", linear is not None)) if not ok]
    st.info(f"Demo mode: no {' or '.join(missing)} key, so "
            + ("notes are read by a simple keyword parser" if not has_claude else "Claude reads the notes")
            + (" and follow-ups stay in this app instead of Linear." if linear is None else "."))

# 1. Call notes
st.header("1. Call notes")
notes = st.text_area("What you heard on the call", value=SAMPLE_NOTES, height=160)
if st.button("Read the notes", type="primary"):
    with st.spinner("Reading the notes..."):
        needs, source = extract_needs(notes)
    st.session_state.needs = needs.to_dict()
    st.session_state.source = source

if "needs" not in st.session_state:
    st.stop()

# 2. Needs (editable)
st.header("2. Check what they need")
st.caption("Read by Claude." if st.session_state.source == "claude"
           else "Read by the simple parser. Check every field.")
n = Needs.from_dict(st.session_state.needs)
c1, c2, c3 = st.columns(3)
with c1:
    n.company = st.text_input("Company", n.company)
    n.contact_name = st.text_input("Contact", n.contact_name)
    n.contact_email = st.text_input("Email", n.contact_email)
    n.staff = st.number_input("Staff", 0, 10000, int(n.staff))
    n.locations = st.number_input("Locations", 1, 100, int(n.locations))
with c2:
    speeds = [None, 300, 1000, 3000]
    n.internet_speed = st.selectbox("Internet", speeds, index=speeds.index(n.internet_speed),
                                    format_func=lambda s: "None" if s is None else pb.INTERNET[s].name)
    n.phone_lines = st.number_input("Desk phone lines", 0, 1000, int(n.phone_lines))
    n.mobile_lines = st.number_input("Mobile lines", 0, 1000, int(n.mobile_lines))
    n.mobile_plan = st.radio("Mobile plan", ["essential", "unlimited"],
                             index=["essential", "unlimited"].index(n.mobile_plan), horizontal=True)
with c3:
    n.static_ip = st.checkbox("Static IP", n.static_ip)
    n.managed_wifi = st.checkbox("Managed Wi-Fi", n.managed_wifi)
    n.backup_internet = st.checkbox("Backup internet", n.backup_internet)
    n.term_months = st.radio("Term (months)", [12, 24, 36], index=[12, 24, 36].index(n.term_months),
                             horizontal=True)
if n.notes:
    st.caption(f"Note: {n.notes}")

# 3. Quote
st.header("3. Quote")
base = build_quote(n)
max_pct = float(base.max_extra_discount * 100)
extra = st.slider("Extra discount you want to give (%)", 0.0, 25.0, 0.0, 0.5,
                  help=f"The floor allows up to {max_pct:.1f}% on this deal. Anything above that is capped.")
q = build_quote(n, Decimal(str(extra)) / 100)

left, right = st.columns([3, 2])
with left:
    st.dataframe([{"Service": l.description, "Qty": l.quantity, "Unit": f"${l.unit_price:,.2f}",
                   "Monthly": f"${l.monthly:,.2f}"} for l in q.lines],
                 use_container_width=True, hide_index=True)
    for a in q.adjustments:
        st.markdown(md(f"{a.label}: " + ("included" if a.amount == 0 else f"-${-a.amount:,.2f}")))
with right:
    st.metric("Monthly total", f"${q.monthly:,.2f}", delta=f"-${q.savings:,.2f} vs list" if q.savings else None,
              delta_color="inverse")
    st.metric("Margin", f"{q.margin * 100:.1f}%", help=f"Floor is {pb.MARGIN_FLOOR * 100:.0f}%")
    st.markdown(md(f"One-time: ${q.one_time:,.2f}  \n{q.term_months}-month total: ${q.term_total:,.2f}"))
for w in q.warnings:
    st.warning(md(w))

existing = len(store.list_quotes(engine()))
preview_number = f"Q-{existing + 1:04d}"
st.download_button("Download quote PDF", render_pdf(n, q, preview_number), file_name=f"{preview_number}.pdf",
                   mime="application/pdf", disabled=not q.lines)
if st.button("Mark as sent and schedule follow-ups", disabled=not q.lines):
    saved = store.save_quote(engine(), n.to_dict(), quote_dict(q), float(q.monthly))
    days = ", ".join(str(d) for d in store.FOLLOWUP_DAYS)
    st.success(f"{saved['number']} saved. Follow-ups scheduled for day {days}.")

# 4. Follow-ups
st.header("4. Follow-ups")
rows = store.list_followups(engine())
if not rows:
    st.caption("Nothing scheduled yet. Send a quote above.")
else:
    pretend = st.date_input("Pretend today is", date.today() + timedelta(days=2),
                            help="Jump ahead to see follow-ups come due.")
    if st.button("Run due follow-ups"):
        try:
            done = followups.run_due(engine(), pretend, linear)
            st.success(f"{len(done)} follow-up(s) due" + (", added to Linear." if linear and done else "."))
        except followups.LinearError as exc:
            st.error(str(exc))
        rows = store.list_followups(engine())
    st.dataframe([{"Quote": r["number"], "Company": r["company"], "Step": r["step"], "Due": r["due_on"],
                   "Status": r["status"], "Linear": r["linear_identifier"] or ""} for r in rows],
                 use_container_width=True, hide_index=True)
    waiting = [x for x in store.list_quotes(engine()) if x["status"] == "sent"]
    if waiting:
        pick = st.selectbox("Client replied to", waiting, format_func=lambda x: f"{x['number']} {x['company']}")
        if st.button("Client replied: stop follow-ups"):
            try:
                closed = followups.client_replied(engine(), pick["id"], linear)
                st.success(f"Follow-ups stopped for {pick['number']}" +
                           (f", {closed} Linear task(s) closed." if closed else "."))
                st.rerun()
            except followups.LinearError as exc:
                st.error(str(exc))
