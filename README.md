# smb-deal-bot

Automation for the stages of a small-business (SMB) sales deal: prospecting, quoting, follow-up, onboarding and renewal.
Three small services share one fake dataset and run together on Kubernetes. Work is planned and tracked in Linear.

> All companies, people, prices and products in this repo are fictional. The demo provider is "Northwind Connect", a made-up telecom and IT services company.

## The three services

| Service | Deal stages | What it does | Status |
| --- | --- | --- | --- |
| [Lead Radar](services/lead-radar/) | Prospecting | Scores a territory list on fit and contract timing, explains each score, drafts a first email | Working: scoring, email drafts, Linear issues |
| [Quote Desk](services/quote-desk/) | Quoting, follow-up | Turns call notes into a priced PDF quote, then runs follow-ups that stop when the client replies | Planned |
| [Account Watch](services/account-watch/) | Onboarding, renewal | Tracks onboarding steps, scores account health, flags renewals at 90, 60 and 30 days | Planned |

Each service also creates work in Linear through its API (top leads, follow-up tasks, onboarding and renewal issues). See [docs/linear.md](docs/linear.md).

## Architecture

```
                 +-------------------- Kubernetes namespace: smb-deal-bot --------------------+
                 |                                                                            |
  browser ---> Ingress ---> lead-radar    (Deployment + Service)                              |
                 |      \-> quote-desk    (Deployment + Service, follow-up CronJob)           |
                 |      \-> account-watch (Deployment + Service, daily renewal CronJob)       |
                 |                  \           |            /                                |
                 |                   +---- Postgres (StatefulSet) ----+                       |
                 |                                                                            |
                 +-------------------------------+--------------------------------------------+
                                                 |
                                  Linear API, Claude API, Slack webhook (via Secrets)
```

## Repo layout

```
services/        one folder per service (code arrives in later pull requests)
data/            fake-data generator and rules
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

By default the chart starts Postgres only. Turn a service on with `--set leadRadar.enabled=true`; see each service README for building its image.

## Project tracking

Planned in Linear (workspace "The Deal Bot"). Pull requests reference Linear issue IDs so they link automatically.
