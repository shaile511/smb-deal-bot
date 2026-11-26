"""Turn due follow-ups into Linear issues, and close them when the client replies."""

from __future__ import annotations

import os
from datetime import date

import requests

from . import store

API_URL = "https://api.linear.app/graphql"
TIMEOUT = 20


class LinearError(RuntimeError):
    pass


TEAM_QUERY = """query($key: String!) { teams(filter: { key: { eq: $key } }) { nodes { id key
  states { nodes { id name type } } } } }"""
CREATE_MUTATION = """mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success
  issue { id identifier url } } }"""
UPDATE_MUTATION = """mutation($id: String!, $input: IssueUpdateInput!) { issueUpdate(id: $id, input: $input)
  { success } }"""
COMMENT_MUTATION = """mutation($input: CommentCreateInput!) { commentCreate(input: $input) { success } }"""


def issue_title(f: dict) -> str:
    who = f["contact_name"] or "the client"
    return f"Follow up #{f['step']} with {who} at {f['company']} ({f['number']})"


def issue_description(f: dict, quote: dict) -> str:
    lines = [f"**Quote {f['number']}**: ${quote['monthly_total']:,.2f}/month, sent {quote['sent_on']}.", ""]
    nudges = {
        1: "Check they received the quote and answer any first questions.",
        2: "Offer a short call to walk through the bundle and the term.",
        3: "Last nudge. Ask if the timing is wrong or if something else is in the way.",
    }
    lines.append(nudges.get(f["step"], "Follow up on the quote."))
    if quote.get("contact_email"):
        lines.append(f"\nContact: {quote['contact_email']}")
    lines.append("\n_Created by Quote and Follow-up Desk (portfolio demo, made-up data)._")
    return "\n".join(lines)


class LinearClient:
    def __init__(self, api_key: str, team_key: str, session: requests.Session | None = None):
        self.api_key = api_key
        self.team_key = team_key
        self.session = session or requests.Session()
        self._team = None

    def _gql(self, query: str, variables: dict) -> dict:
        resp = self.session.post(API_URL, json={"query": query, "variables": variables},
                                 headers={"Authorization": self.api_key, "Content-Type": "application/json"},
                                 timeout=TIMEOUT)
        if resp.status_code == 401 or resp.status_code == 400 and "authentication" in resp.text.lower():
            raise LinearError("Linear rejected the API key. Check LINEAR_API_KEY in your .env.")
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            raise LinearError(f"Linear error: {body['errors'][0].get('message')}")
        return body["data"]

    def team(self) -> dict:
        if self._team is None:
            nodes = self._gql(TEAM_QUERY, {"key": self.team_key})["teams"]["nodes"]
            if not nodes:
                raise LinearError(f"Linear team '{self.team_key}' not found. Set LINEAR_TEAM_KEY in your .env.")
            self._team = nodes[0]
        return self._team

    def create_issue(self, title: str, description: str, due: date) -> dict:
        data = self._gql(CREATE_MUTATION, {"input": {
            "teamId": self.team()["id"], "title": title, "description": description,
            "dueDate": due.isoformat(), "priority": 2}})["issueCreate"]
        if not data["success"]:
            raise LinearError("Linear did not create the issue.")
        return data["issue"]

    def close_issue(self, issue_id: str, note: str) -> None:
        states = self.team()["states"]["nodes"]
        target = next((s for s in states if s["type"] == "canceled"), None) or \
            next((s for s in states if s["type"] == "completed"), None)
        self._gql(COMMENT_MUTATION, {"input": {"issueId": issue_id, "body": note}})
        if target:
            self._gql(UPDATE_MUTATION, {"id": issue_id, "input": {"stateId": target["id"]}})


def client_from_env() -> LinearClient | None:
    key = os.environ.get("LINEAR_API_KEY")
    if not key:
        return None
    return LinearClient(key, os.environ.get("LINEAR_TEAM_KEY", "THE"))


def run_due(engine, today: date | None = None, linear: LinearClient | None = None) -> list[dict]:
    """Make each due follow-up a Linear issue (or a local task without a key). Returns what was done."""
    today = today or date.today()
    done = []
    for f in store.due_followups(engine, today):
        quote = store.get_quote(engine, f["quote_id"])
        title = issue_title(f)
        if linear:
            issue = linear.create_issue(title, issue_description(f, quote), f["due_on"])
            store.mark_due(engine, f["id"], issue["id"], issue["identifier"], issue["url"])
            done.append({"title": title, "identifier": issue["identifier"], "url": issue["url"]})
        else:
            store.mark_due(engine, f["id"], None, None, None)
            done.append({"title": title, "identifier": None, "url": None})
    return done


def client_replied(engine, quote_id: int, linear: LinearClient | None = None,
                   today: date | None = None) -> int:
    """Stop the quote's follow-ups and close their Linear issues. Returns how many issues were closed."""
    with_issues = store.mark_replied(engine, quote_id, today)
    closed = 0
    if linear:
        for f in with_issues:
            linear.close_issue(f["linear_id"], "Client replied, so this follow-up is no longer needed.")
            closed += 1
    return closed
