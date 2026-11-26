# Account Watch (onboarding and renewal)

**Problem:** after close, nobody checks that install, number porting and training happened, and renewals get noticed too late.

**Plan:**
1. Onboarding checklist with due dates for every closed deal from Quote Desk.
2. Health score per account from overdue steps, fake tickets and usage changes.
3. Daily Kubernetes CronJob raises renewal issues in Linear at 90, 60 and 30 days, ranked by health.
4. Weekly digest to Slack or the test inbox.

**Stack:** Python, Postgres, Kubernetes CronJob, Slack webhook, Streamlit dashboard.

Status: planned.
