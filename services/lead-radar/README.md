# Lead Radar (prospecting)

**Problem:** reps waste hours deciding which small businesses in a territory to call first.

**What it does now:**
1. Generates 200 fictional small businesses (or takes your own CSV).
2. Scores each one out of 100 on **fit** (staff size, number of locations, industry) and **timing** (when their current contract ends).
3. Shows every score's reasons, so a rep can trust or challenge the ranking.
4. Leaves out businesses that are already customers.

![Lead Radar screen](docs/screenshot.png)

## How scoring works

| Part | Max points | Highest when |
| --- | --- | --- |
| Staff size | 20 | 20 to 49 staff |
| Locations | 20 | 4 or more sites |
| Industry | 20 | Dental clinics, law offices, real estate |
| Timing | 40 | Contract ends in 2 to 4 months |

The weights are a starting point from sales experience, not a trained model. They live in [`lead_radar/scoring.py`](lead_radar/scoring.py).

## Run it

On your laptop:

```bash
cd services/lead-radar
pip install -r requirements-dev.txt
python -m pytest -q tests
PYTHONPATH=. streamlit run lead_radar/app.py
```

On the local Kubernetes cluster (see the main README for creating it):

```bash
docker build -t smb-deal-bot/lead-radar:dev services/lead-radar
kind load docker-image smb-deal-bot/lead-radar:dev --name smb-deal-bot
helm upgrade --install smb-deal-bot deploy/helm/smb-deal-bot -n smb-deal-bot --set leadRadar.enabled=true
kubectl -n smb-deal-bot port-forward svc/lead-radar 8501:80
```

Then open http://localhost:8501.

## Coming next

- Draft a first email per top lead with the Claude API.
- Create a Linear issue for each top-10 lead.
- Save leads and scores in the shared Postgres database.
