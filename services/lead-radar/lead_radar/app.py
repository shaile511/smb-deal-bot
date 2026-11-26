"""Lead Radar screen: a ranked territory list with the reasons behind each score."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from lead_radar.generate import generate_leads
from lead_radar.scoring import rank_leads

st.set_page_config(page_title="Lead Radar", layout="wide")
st.title("Lead Radar")
st.caption("Who to call first, and why. All businesses here are fictional.")

uploaded = st.sidebar.file_uploader("Upload a lead CSV", type="csv")
seed = st.sidebar.number_input("Or generate fake leads (seed)", value=42, step=1)
top_n = st.sidebar.slider("Show top", 5, 50, 10)

if uploaded is not None:
    leads = pd.read_csv(uploaded, dtype={"contract_end": str})
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

st.subheader("Why each lead scored the way it did")
for _, row in top.iterrows():
    with st.expander(f"{row['score']}  ·  {row['company']}  ·  {row['contact_name']}"):
        for reason in row["reasons"]:
            st.write(reason)
