# Lead Radar (prospecting)

**Problem:** reps waste hours deciding which small businesses in a territory to call first, then rewrite the same cold email.

**Plan:**
1. Load a CSV of fictional SMBs (industry, employees, locations, current provider, contract end month).
2. Score each lead on fit and timing, with the reasons shown.
3. Draft a first-touch email per top lead with the Claude API; the rep edits before sending.
4. Create a Linear issue per top-10 lead, assigned to the rep.

**Stack:** Python, pandas, Postgres, Streamlit, Claude API.

Status: planned. Code arrives in a later pull request.
