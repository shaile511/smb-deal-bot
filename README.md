# smb-deal-bot

Automation for the stages of a small-business (SMB) sales deal: prospecting, quoting, follow-up, onboarding and renewal.
Three small services, all on made-up data, run together on Kubernetes from one Helm chart. Work is planned and tracked in Linear.

**[Project site](https://shaile511.github.io/smb-deal-bot/)** · **[Try the Lead Radar demo](https://smb-deal-bot-3apc4tq4ht4vadxa98meca.streamlit.app/)** (demo mode: sample emails, Linear preview only).
**[Try the Quote Desk demo](https://smb-deal-bot-pb9vfrp4g6dybpmerysglx.streamlit.app/)** (demo mode: simple notes parser, follow-ups stay in the app).

> All companies, people, prices and products in this repo are fictional. The demo provider is "Northwind Connect", a made-up telecom and IT services company.

## The three services

| Service | Deal stages | What it does | Status |
| --- | --- | --- | --- |
| [Lead Radar](services/lead-radar/) | Prospecting | Scores a territory list on fit and contract timing, explains each score, drafts a first email | Working: scoring, email drafts, Linear issues |
| [Quote Desk](services/quote-desk/) ([demo](https://smb-deal-bot-pb9vfrp4g6dybpmerysglx.streamlit.app/)) | Quoting, follow-up | Turns call notes into a priced PDF quote, then runs follow-ups that stop when the client replies | Working: quotes, PDF, Linear follow-ups, CronJob |
| [Account Watch](services/account-watch/) | Onboarding, renewal | Tracks onboarding steps, scores account health with reasons, raises renewals in Linear at 90 days and escalates them at 60 and 30, posts a weekly Slack digest | Working: checklists, health, Linear renewals, daily and weekly CronJobs |

Each service also creates work in Linear through its API (top leads, follow-up tasks, overdue onboarding and renewal issues). See [docs/linear.md](docs/linear.md).

## Architecture

What runs in the cluster:

```
                 +------------------ Kubernetes namespace: smb-deal-bot ------------------+
                 |                                                                        |
  browser --(kubectl port-forward)--> lead-radar     (Deployment + Service)               |
                 |                    quote-desk     (Deployment + Service) ---+          |
                 |                    quote-desk-followups  (daily CronJob) ---+          |
                 |                    account-watch  (Deployment + Service) ---+-> Postgres
                 |                    account-watch-daily   (daily CronJob) ---+  (StatefulSet)
                 |                    account-watch-digest (weekly CronJob) ---+          |
                 |                                                                        |
                 +--------------------------------+---------------------------------------+
                                                  |
                         Claude API, Linear API and a Slack webhook (keys from a Secret)
```

Lead Radar generates its own fake leads and keeps nothing in Postgres. Quote Desk and Account Watch store their data there (in separate tables), so each app and its CronJobs see the same data. There is no Ingress.

## Repo layout

```
services/        one folder per service (Lead Radar, Quote Desk, Account Watch)
data/            fake-data rules and sources (the generator is services/lead-radar/lead_radar/generate.py)
deploy/helm/     one Helm chart for the whole stack
deploy/kind/     config for a free local Kubernetes cluster
docs/            planning notes, Linear setup
```

## Run it locally on Kubernetes

Needs [Docker](https://docs.docker.com/get-docker/), [kind](https://kind.sigs.k8s.io/), [kubectl](https://kubernetes.io/docs/tasks/tools/) and [Helm](https://helm.sh/docs/intro/install/).

```bash
kind create cluster --config deploy/kind/kind-config.yaml
cp .env.example .env            # fill in your own keys; .env is never committed
kubectl create namespace smb-deal-bot
kubectl -n smb-deal-bot create secret generic smb-deal-bot-secrets --from-env-file=.env
helm install smb-deal-bot deploy/helm/smb-deal-bot -n smb-deal-bot
kubectl -n smb-deal-bot get pods
```

### On Windows or Mac with Docker Desktop

No kind needed: Docker Desktop has Kubernetes built in. In Docker Desktop, open Settings > Kubernetes, tick **Enable Kubernetes**, choose **Kubeadm** (so the cluster can see images you build) and wait for the green "Kubernetes running" light. Install Helm with `winget install Helm.Helm` (Windows) or `brew install helm` (Mac). Then, from the repo root:

```powershell
docker build -t smb-deal-bot/lead-radar:dev services/lead-radar
kubectl create namespace smb-deal-bot
kubectl -n smb-deal-bot create secret generic smb-deal-bot-secrets --from-env-file=.env
helm upgrade --install smb-deal-bot deploy/helm/smb-deal-bot -n smb-deal-bot --set leadRadar.enabled=true
kubectl -n smb-deal-bot get pods
kubectl -n smb-deal-bot port-forward svc/lead-radar 8501:80
```

Open http://localhost:8501. Stop with Ctrl+C; remove everything with `helm uninstall smb-deal-bot -n smb-deal-bot`.

By default the chart starts Postgres only. Turn a service on with `--set leadRadar.enabled=true` (or `quoteDesk`, `accountWatch`); see each service README for building its image.

## Project tracking

Planned in Linear (workspace "The Deal Bot"). Pull requests reference Linear issue IDs so they link automatically.
