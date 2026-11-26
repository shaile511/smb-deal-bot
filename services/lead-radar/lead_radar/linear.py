"""Create a Linear issue for each top lead, so the rep's call list lives in their to-do tool.

Uses Linear's GraphQL API with a personal API key (LINEAR_API_KEY). Without a key, or with
dry_run=True, it only returns what it would create. Re-running does not create duplicates:
an issue with the same title in the same team is reused.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests

API_URL = "https://api.linear.app/graphql"

TEAMS_QUERY = "query { teams { nodes { id key name } } }"
FIND_QUERY = """
query Find($teamId: ID!, $title: String!) {
  issues(filter: { team: { id: { eq: $teamId } }, title: { eq: $title } }) {
    nodes { identifier url }
  }
}
"""
CREATE_MUTATION = """
mutation Create($input: IssueCreateInput!) {
  issueCreate(input: $input) { success issue { identifier url } }
}
"""


class LinearError(RuntimeError):
    pass


@dataclass
class Result:
    title: str
    status: str  # "created", "exists" or "dry-run"
    identifier: str = ""
    url: str = ""


def issue_title(lead: dict) -> str:
    return f"Call {lead['contact_name']} at {lead['company']} (score {lead['score']})"


def issue_priority(score: int) -> int:
    """Linear priority: 1 urgent, 2 high, 3 medium, 4 low."""
    if score >= 85:
        return 2
    if score >= 70:
        return 3
    return 4


def issue_description(lead: dict, draft_body: str | None = None) -> str:
    reasons = "\n".join(f"- {r}" for r in lead.get("reasons", []))
    text = (
        f"**{lead['company']}** · {lead['industry']} · {lead['employees']} staff · "
        f"{lead['locations']} location(s) · {lead['city']}\n\n"
        f"Contact: {lead['contact_name']} ({lead['contact_email']})\n"
        f"Current provider: {lead['current_provider']}, contract end: {lead.get('contract_end') or 'none'}\n\n"
        f"### Why this lead\n{reasons}\n"
    )
    if draft_body:
        text += f"\n### Draft email (edit before sending)\n{draft_body}\n"
    text += "\n_Created by Lead Radar. All data is fictional._"
    return text


class LinearClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self.api_key = api_key or os.environ.get("LINEAR_API_KEY", "")
        self.session = session or requests.Session()

    def _call(self, query: str, variables: dict | None = None) -> dict:
        resp = self.session.post(
            API_URL,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": self.api_key, "Content-Type": "application/json"},
            timeout=20,
        )
        if resp.status_code != 200:
            raise LinearError(f"Linear returned HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        if payload.get("errors"):
            raise LinearError(payload["errors"][0].get("message", "Linear error"))
        return payload["data"]

    def team_id(self, team_key: str | None = None) -> str:
        teams = self._call(TEAMS_QUERY)["teams"]["nodes"]
        if not teams:
            raise LinearError("No teams found in this Linear workspace")
        if team_key:
            for team in teams:
                if team["key"].lower() == team_key.lower() or team["name"].lower() == team_key.lower():
                    return team["id"]
            raise LinearError(f"Team {team_key!r} not found. Teams: {', '.join(t['key'] for t in teams)}")
        return teams[0]["id"]

    def find_issue(self, team_id: str, title: str) -> dict | None:
        nodes = self._call(FIND_QUERY, {"teamId": team_id, "title": title})["issues"]["nodes"]
        return nodes[0] if nodes else None

    def create_issue(self, team_id: str, title: str, description: str, priority: int) -> dict:
        data = self._call(
            CREATE_MUTATION,
            {"input": {"teamId": team_id, "title": title, "description": description, "priority": priority}},
        )["issueCreate"]
        if not data["success"]:
            raise LinearError(f"Linear did not create {title!r}")
        return data["issue"]


def push_leads(leads: list[dict], drafts: dict[str, str] | None = None, client: LinearClient | None = None,
               team_key: str | None = None, dry_run: bool = False) -> list[Result]:
    """Create one Linear issue per lead. `drafts` maps company name to an email body."""
    drafts = drafts or {}
    client = client or LinearClient()
    if dry_run or not client.api_key:
        return [Result(issue_title(lead), "dry-run") for lead in leads]

    team_id = client.team_id(team_key or os.environ.get("LINEAR_TEAM_KEY"))
    results = []
    for lead in leads:
        title = issue_title(lead)
        existing = client.find_issue(team_id, title)
        if existing:
            results.append(Result(title, "exists", existing["identifier"], existing["url"]))
            continue
        issue = client.create_issue(
            team_id, title, issue_description(lead, drafts.get(lead["company"])), issue_priority(int(lead["score"]))
        )
        results.append(Result(title, "created", issue["identifier"], issue["url"]))
    return results
