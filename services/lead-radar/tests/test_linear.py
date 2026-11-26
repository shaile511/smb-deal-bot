from lead_radar.linear import LinearClient, issue_priority, issue_title, push_leads

LEAD = {
    "company": "Test Dental", "contact_name": "Ana Lopez", "contact_email": "ana.lopez@example.com",
    "industry": "Dental clinic", "employees": 25, "locations": 2, "city": "Testville",
    "current_provider": "Bluepeak Telecom", "contract_end": "2027-02", "score": 95,
    "reasons": ["+40 Contract ends in 3 months: best time to reach out"],
}


class FakeResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data
        self.text = ""

    def json(self):
        return {"data": self._data}


class FakeSession:
    """Answers Linear's three queries and records every call."""

    def __init__(self, existing=None):
        self.existing = existing or []
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append(json)
        q = json["query"]
        if "teams" in q:
            return FakeResponse({"teams": {"nodes": [{"id": "team-1", "key": "DEAL", "name": "Deal Desk"}]}})
        if "issues(" in q:
            return FakeResponse({"issues": {"nodes": self.existing}})
        return FakeResponse({"issueCreate": {"success": True, "issue": {"identifier": "DEAL-7", "url": "https://linear.app/x/DEAL-7"}}})


def test_dry_run_without_key(monkeypatch):
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    results = push_leads([LEAD])
    assert results[0].status == "dry-run"


def test_creates_issue_with_priority_and_draft():
    session = FakeSession()
    client = LinearClient(api_key="test", session=session)
    results = push_leads([LEAD], {"Test Dental": "Hi Ana"}, client=client)
    assert results[0].status == "created" and results[0].identifier == "DEAL-7"
    create = session.calls[-1]["variables"]["input"]
    assert create["teamId"] == "team-1"
    assert create["priority"] == 2
    assert "Hi Ana" in create["description"]


def test_does_not_duplicate():
    session = FakeSession(existing=[{"identifier": "DEAL-3", "url": "https://linear.app/x/DEAL-3"}])
    results = push_leads([LEAD], client=LinearClient(api_key="test", session=session))
    assert results[0].status == "exists"
    assert not any("issueCreate" in c["query"] for c in session.calls)


def test_title_and_priority():
    assert issue_title(LEAD) == "Call Ana Lopez at Test Dental (score 95)"
    assert [issue_priority(s) for s in (90, 75, 40)] == [2, 3, 4]
