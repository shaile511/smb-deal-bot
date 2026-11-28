"""Lead Radar screen: a ranked territory list, the reasons behind each score,
email drafts, and a button that turns the top leads into Linear issues."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# `streamlit run lead_radar/app.py` only puts lead_radar/ on the import path, so add its
# parent too. Without this the app fails with "No module named 'lead_radar'" unless
# PYTHONPATH is set (it is in the Docker image, but not on a laptop or Streamlit Cloud).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from dotenv import find_dotenv, load_dotenv

from lead_radar.drafts import draft_email
from lead_radar.generate import generate_leads
from lead_radar.linear import LinearError, issue_title, push_leads
from lead_radar.scoring import REQUIRED_COLUMNS, check_leads, rank_leads

# Read API keys from the nearest .env (repo root), on any OS. Real env vars win.
load_dotenv(find_dotenv(usecwd=True))

st.set_page_config(page_title="Lead Radar", layout="wide")
st.title("Lead Radar")
st.caption("Who to call first, and why. All businesses here are fictional.")

has_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
has_linear = bool(os.environ.get("LINEAR_API_KEY"))
if not (has_claude and has_linear):
    missing = [name for name, ok in [("Claude", has_claude), ("Linear", has_linear)] if not ok]
    st.info(f"Demo mode for {' and '.join(missing)}: no API key set, so drafts use a template "
            f"and Linear runs as a dry run.")

uploaded = st.sidebar.file_uploader("Upload a lead CSV", type="csv",
                                    help="Columns: " + ", ".join(REQUIRED_COLUMNS) + " (contact_email optional).")
seed = st.sidebar.number_input("Or generate fake leads (seed)", value=42, step=1)
top_n = st.sidebar.slider("Show top", 5, 50, 10)

if uploaded is not None:
    leads = pd.read_csv(uploaded, dtype={"contract_end": str})
    problems = check_leads(leads)
    if problems:
        st.error("This CSV can't be scored yet:\n\n" + "\n".join(f"- {p}" for p in problems[:10])
                 + (f"\n- ...and {len(problems) - 10} more" if len(problems) > 10 else ""))
        st.stop()
    if "contact_email" not in leads.columns:
        leads["contact_email"] = ""
else:
    leads = generate_leads(200, int(seed))

ranked = rank_leads(leads)
skipped = len(leads) - len(ranked)
st.write(f"**{len(leads)}** businesses loaded, **{skipped}** are already customers and left out.")

top = ranked.head(top_n)
st.dataframe(
    top[["score", "company", "industry", "employees", "locations", "current_provider", "contract_end", "city"]],
    use_container_width=True,
    hide_index=True,
)

drafts: dict[str, str] = st.session_state.setdefault("drafts", {})

st.subheader("Why each lead scored the way it did")
for i, row in top.iterrows():
    lead = row.to_dict()
    # Keyed by contact and company (and row), since two leads can share a company name.
    title = issue_title(lead)
    with st.expander(f"{row['score']}  ·  {row['company']}  ·  {row['contact_name']}"):
        for reason in row["reasons"]:
            st.write(reason)
        if st.button("Draft first email", key=f"draft-{i}-{title}"):
            with st.spinner("Drafting..."):
                d = draft_email(lead)
            drafts[title] = f"Subject: {d.subject}\n\n{d.body}"
        if title in drafts:
            drafts[title] = st.text_area(
                "Edit before sending (nothing is sent from here)", drafts[title],
                height=220, key=f"text-{i}-{title}",
            )

st.sidebar.divider()
label = f"Send top {top_n} to Linear" if has_linear else f"Preview top {top_n} as Linear issues"
if st.sidebar.button(label):
    try:
        results = push_leads(top.to_dict(orient="records"), drafts)
        if all(r.status == "dry-run" for r in results):
            st.sidebar.info(f"Dry run: these {len(results)} issues would be created in Linear.")
        else:
            st.sidebar.success(f"{sum(r.status == 'created' for r in results)} created, "
                               f"{sum(r.status == 'exists' for r in results)} already there")
        for r in results:
            st.sidebar.write(f"[{r.status}] [{r.identifier or r.title}]({r.url})" if r.url else f"[{r.status}] {r.title}")
    except LinearError as exc:
        st.sidebar.error(f"Linear: {exc}")
