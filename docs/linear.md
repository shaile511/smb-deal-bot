# Linear setup

Linear plans the build and is also used by the apps themselves. It does not host anything; Kubernetes runs the apps.

## Planning the build

- Workspace: **The Deal Bot**
- One Linear project per service (Lead Radar, Quote Desk, Account Watch) plus **Platform** for Kubernetes, CI and Docker.
- Two-week cycles, each ending with something demoable.
- Labels: `feature`, `bug`, `infra`, `docs`, `data`.
- Issues are written as user stories, for example: "As a rep, I can see why a lead scored 82 so I trust the ranking."
- GitHub is connected: put the Linear issue ID (for example `DEAL-12`) in a branch name or pull request title and the issue updates on its own.

## Linear inside the apps

| Service | What it creates in Linear |
| --- | --- |
| Lead Radar | An issue per top-10 lead, with score reasons and the email draft |
| Quote Desk | Follow-up tasks due on day 2, 5 and 10, closed when the client replies |
| Account Watch | Issues for overdue onboarding steps and renewals at 90, 60 and 30 days |

The apps call Linear's GraphQL API with a personal API key stored as a Kubernetes Secret (`LINEAR_API_KEY`).
Linear is used here as the rep's to-do layer, not as a CRM.
