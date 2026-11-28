"""A small Linear GraphQL client. Same team rule as Lead Radar and Quote Desk."""

from __future__ import annotations

import os
from datetime import date

import requests

API_URL = "https://api.linear.app/graphql"
TIMEOUT = 20

TEAMS_QUERY = """query { teams { nodes { id key name states { nodes { id name type } } } } }"""
CREATE_MUTATION = """mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success
  issue { id identifier url } } }"""
UPDATE_MUTATION = """mutation($id: String!, $input: IssueUpdateInput!) { issueUpdate(id: $id, input: $input)
  { success } }"""
COMMENT_MUTATION = """mutation($input: CommentCreateInput!) { commentCreate(input: $input) { success } }"""


class LinearError(RuntimeError):
    pass


class LinearClient:
    def __init__(self, api_key: str, team_key: str = "", session: requests.Session | None = None):
        self.api_key = api_key
        self.team_key = team_key
        self.session = session or requests.Session()
        self._team = None

    def _gql(self, query: str, variables: dict) -> dict:
        try:
            resp = self.session.post(API_URL, json={"query": query, "variables": variables},
                                     headers={"Authorization": self.api_key, "Content-Type": "application/json"},
                                     timeout=TIMEOUT)
            if resp.status_code == 401 or resp.status_code == 400 and "authentication" in resp.text.lower():
                raise LinearError("Linear rejected the API key. Check LINEAR_API_KEY in your .env.")
            resp.raise_for_status()
            body = resp.json()
        except requests.RequestException as exc:  # network errors and HTTP errors alike
            raise LinearError(f"Could not reach Linear ({type(exc).__name__}). Try again.") from exc
        except ValueError as exc:  # a reply that is not JSON
            raise LinearError("Linear sent back something that is not JSON. Try again.") from exc
        if body.get("errors"):
            raise LinearError(f"Linear error: {body['errors'][0].get('message')}")
        return body["data"]

    def team(self) -> dict:
        """Blank means the first team; a team key or name matches in any case."""
        if self._team is None:
            teams = self._gql(TEAMS_QUERY, {})["teams"]["nodes"]
            if not teams:
                raise LinearError("No teams found in this Linear workspace.")
            wanted = (self.team_key or "").strip().lower()
            if not wanted:
                self._team = teams[0]
            else:
                match = [t for t in teams if wanted in (t["key"].lower(), t["name"].lower())]
                if not match:
                    keys = ", ".join(t["key"] for t in teams)
                    raise LinearError(f"Linear team {self.team_key!r} not found. Your teams: {keys}. Set "
                                      "LINEAR_TEAM_KEY in your .env to one of those, or leave it blank for the first team.")
                self._team = match[0]
        return self._team

    def create_issue(self, title: str, description: str, due: date, priority: int) -> dict:
        data = self._gql(CREATE_MUTATION, {"input": {
            "teamId": self.team()["id"], "title": title, "description": description,
            "dueDate": due.isoformat(), "priority": priority}})["issueCreate"]
        if not data["success"]:
            raise LinearError("Linear did not create the issue.")
        return data["issue"]

    def escalate(self, issue_id: str, title: str, priority: int, note: str) -> None:
        self._gql(COMMENT_MUTATION, {"input": {"issueId": issue_id, "body": note}})
        self._gql(UPDATE_MUTATION, {"id": issue_id, "input": {"title": title, "priority": priority}})

    def complete(self, issue_id: str, note: str) -> None:
        states = self.team()["states"]["nodes"]
        target = next((s for s in states if s["type"] == "completed"), None)
        self._gql(COMMENT_MUTATION, {"input": {"issueId": issue_id, "body": note}})
        if target:
            self._gql(UPDATE_MUTATION, {"id": issue_id, "input": {"stateId": target["id"]}})


def client_from_env() -> LinearClient | None:
    key = os.environ.get("LINEAR_API_KEY")
    if not key:
        return None
    return LinearClient(key, os.environ.get("LINEAR_TEAM_KEY", ""))
