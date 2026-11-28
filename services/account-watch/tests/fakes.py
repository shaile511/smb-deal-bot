import requests

STATES = {"nodes": [{"id": "s-done", "name": "Done", "type": "completed"},
                    {"id": "s-cancel", "name": "Canceled", "type": "canceled"}]}
TEAMS = [{"id": "team1", "key": "THE", "name": "The Deal Bot", "states": STATES},
         {"id": "team2", "key": "OPS", "name": "Operations", "states": STATES}]


class FakeResponse:
    def __init__(self, body, status_code=200, text=""):
        self.body, self.status_code, self.text = body, status_code, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class FakeLinear:
    """Answers Linear GraphQL calls and records them."""

    def __init__(self, teams=TEAMS, fail_on=None):
        self.calls, self.teams, self.fail_on = [], teams, fail_on

    def post(self, url, json, headers, timeout):
        self.calls.append(json)
        q = json["query"]
        if self.fail_on and self.fail_on in q:
            self.fail_on = None
            raise requests.ConnectionError("network down")
        if "teams" in q:
            data = {"teams": {"nodes": self.teams}}
        elif "issueCreate" in q:
            n = sum("issueCreate" in c["query"] for c in self.calls)
            data = {"issueCreate": {"success": True, "issue": {
                "id": f"i{n}", "identifier": f"THE-{n}", "url": f"https://linear.example.com/THE-{n}"}}}
        elif "commentCreate" in q:
            data = {"commentCreate": {"success": True}}
        else:
            data = {"issueUpdate": {"success": True}}
        return FakeResponse({"data": data})

    def of(self, name):
        return [c for c in self.calls if name in c["query"]]
