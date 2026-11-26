from datetime import date

import pytest

from quote_desk import followups, store


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append(json)
        q = json["query"]
        if "teams(" in q:
            data = {"teams": {"nodes": [{"id": "team1", "key": "THE", "states": {"nodes": [
                {"id": "s-done", "name": "Done", "type": "completed"},
                {"id": "s-cancel", "name": "Canceled", "type": "canceled"}]}}]}}
        elif "issueCreate" in q:
            n = sum("issueCreate" in c["query"] for c in self.calls)
            data = {"issueCreate": {"success": True, "issue": {
                "id": f"i{n}", "identifier": f"THE-{n}", "url": f"https://linear.example.com/THE-{n}"}}}
        elif "commentCreate" in q:
            data = {"commentCreate": {"success": True}}
        else:
            data = {"issueUpdate": {"success": True}}
        return FakeResponse({"data": data})


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


@pytest.fixture
def engine(tmp_path):
    return store.get_engine(f"sqlite:///{tmp_path / 'qd.db'}")


def send(engine, sent=date(2026, 11, 2)):
    return store.save_quote(engine, {"company": "Harbour Bakery", "contact_name": "Sam"},
                            {"lines": []}, 512.4, sent_on=sent)


def test_quote_numbers_and_schedule(engine):
    a, b = send(engine), send(engine)
    assert (a["number"], b["number"]) == ("Q-0001", "Q-0002")
    dues = [f["due_on"] for f in store.list_followups(engine, a["id"])]
    assert dues == [date(2026, 11, 4), date(2026, 11, 7), date(2026, 11, 12)]


def test_due_followups_become_linear_issues_once(engine):
    send(engine)
    session = FakeSession()
    linear = followups.LinearClient("key", "THE", session)
    done = followups.run_due(engine, date(2026, 11, 7), linear)
    assert [d["identifier"] for d in done] == ["THE-1", "THE-2"]
    assert done[0]["title"] == "Follow up #1 with Sam at Harbour Bakery (Q-0001)"
    assert followups.run_due(engine, date(2026, 11, 7), linear) == []
    create = next(c for c in session.calls if "issueCreate" in c["query"])
    assert create["variables"]["input"]["dueDate"] == "2026-11-04"


def test_reply_stops_followups_and_closes_issues(engine):
    q = send(engine)
    session = FakeSession()
    linear = followups.LinearClient("key", "THE", session)
    followups.run_due(engine, date(2026, 11, 4), linear)
    closed = followups.client_replied(engine, q["id"], linear)
    assert closed == 1
    assert {f["status"] for f in store.list_followups(engine, q["id"])} == {"stopped"}
    update = next(c for c in session.calls if "issueUpdate" in c["query"])
    assert update["variables"]["input"]["stateId"] == "s-cancel"
    assert followups.run_due(engine, date(2026, 12, 1), linear) == []


def test_without_linear_followups_stay_local(engine):
    send(engine)
    done = followups.run_due(engine, date(2026, 11, 30), None)
    assert len(done) == 3 and all(d["identifier"] is None for d in done)


def test_missing_team_is_a_friendly_error(engine):
    class NoTeam(FakeSession):
        def post(self, url, json, headers, timeout):
            return FakeResponse({"data": {"teams": {"nodes": []}}})
    send(engine)
    with pytest.raises(followups.LinearError, match="LINEAR_TEAM_KEY"):
        followups.run_due(engine, date(2026, 11, 30), followups.LinearClient("k", "AUTO", NoTeam()))
