from datetime import date

import pytest
import requests

from quote_desk import followups, store

STATES = {"nodes": [{"id": "s-done", "name": "Done", "type": "completed"},
                    {"id": "s-cancel", "name": "Canceled", "type": "canceled"}]}
TEAMS = [{"id": "team1", "key": "THE", "name": "The Deal Bot", "states": STATES},
         {"id": "team2", "key": "OPS", "name": "Operations", "states": STATES}]


class FakeSession:
    def __init__(self, teams=TEAMS, fail_on=None):
        self.calls = []
        self.teams = teams
        self.fail_on = fail_on  # e.g. "commentCreate": the first such call raises a network error

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
    send(engine)
    with pytest.raises(followups.LinearError, match="LINEAR_TEAM_KEY.*Your teams: THE, OPS|Your teams: THE, OPS"):
        followups.run_due(engine, date(2026, 11, 30), followups.LinearClient("k", "AUTO", FakeSession()))


@pytest.mark.parametrize("team_key, team_id", [
    ("", "team1"),             # blank, as .env.example ships it: first team
    ("  ", "team1"),
    ("ops", "team2"),          # key, any case
    ("operations", "team2"),   # name, any case
    ("The Deal Bot", "team1"),
])
def test_team_rule_matches_lead_radar(team_key, team_id):
    assert followups.LinearClient("k", team_key, FakeSession()).team()["id"] == team_id


def test_unset_team_key_means_first_team(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "k")
    monkeypatch.delenv("LINEAR_TEAM_KEY", raising=False)
    client = followups.client_from_env()
    client.session = FakeSession(teams=[TEAMS[1], TEAMS[0]])
    assert client.team()["key"] == "OPS"


def test_network_error_is_a_linear_error(engine):
    send(engine)
    linear = followups.LinearClient("k", "", FakeSession(fail_on="teams"))
    with pytest.raises(followups.LinearError, match="Could not reach Linear"):
        followups.run_due(engine, date(2026, 11, 30), linear)


def test_failed_close_can_be_retried(engine):
    q = send(engine)
    session = FakeSession()
    linear = followups.LinearClient("key", "THE", session)
    followups.run_due(engine, date(2026, 11, 7), linear)  # two issues open
    session.fail_on = "commentCreate"
    with pytest.raises(followups.LinearError):
        followups.client_replied(engine, q["id"], linear)
    # Nothing was stopped, so the retry still knows about both issues and closes them.
    assert followups.client_replied(engine, q["id"], linear) == 2
    assert {f["status"] for f in store.list_followups(engine, q["id"])} == {"stopped"}
    assert store.get_quote(engine, q["id"])["status"] == "replied"


def test_quote_number_is_fixed_by_the_row_id(engine):
    a = send(engine)
    with engine.begin() as conn:  # even if rows are removed, a number is never handed out twice
        conn.execute(store.followups.delete())
        conn.execute(store.quotes.delete().where(store.quotes.c.id == a["id"]))
    b = send(engine)
    assert b["number"] == "Q-0002" and b["number"] == store.quote_number(b["id"])
