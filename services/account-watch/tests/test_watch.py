from datetime import date, timedelta

import pytest

from account_watch import store, watch
from account_watch.linear import LinearClient, LinearError, client_from_env
from fakes import TEAMS, FakeLinear, FakeResponse

TODAY = date(2026, 11, 28)


@pytest.fixture
def engine(tmp_path):
    return store.get_engine(f"sqlite:///{tmp_path / 'aw.db'}")


def add(engine, **overrides):
    row = {"company": "Bluewater Physio", "contact_email": "hannah@bluewater.example.com", "contact_name": "Hannah",
           "closed_on": date(2024, 1, 1), "contract_end": TODAY + timedelta(days=80), "monthly_value": 845.0,
           "tickets_90d": 7, "usage_change_pct": -35, **overrides}
    saved, _ = store.add_accounts(engine, [row], TODAY)
    return saved[0]


def linear(session=None):
    session = session or FakeLinear()
    return LinearClient("key", "THE", session), session


def test_renewal_raised_once_then_escalated_at_60_and_30(engine):
    a = add(engine)
    client, session = linear()
    [first] = watch.run_daily(engine, TODAY, client)
    assert first["title"] == "Renewal 90-day check: Bluewater Physio (A-0001)" and first["identifier"] == "THE-1"
    create = session.of("issueCreate")[0]["variables"]["input"]
    assert (create["priority"], create["dueDate"]) == (2, (TODAY + timedelta(days=80)).isoformat())
    assert "Health 50/100, Watch" in create["description"] and "-25: 7 support tickets" in create["description"]
    assert watch.run_daily(engine, TODAY + timedelta(days=5), client) == []  # still the 90-day window

    [second] = watch.run_daily(engine, TODAY + timedelta(days=20), client)  # 60 days left
    assert second["kind"] == "renewal escalated" and second["identifier"] == "THE-1"
    assert len(session.of("issueCreate")) == 1
    update = session.of("issueUpdate")[-1]["variables"]
    assert update == {"id": "i1", "input": {"title": "Renewal 60-day check: Bluewater Physio (A-0001)", "priority": 2}}
    assert "Now at the 60-day mark (in 60 days)" in session.of("commentCreate")[-1]["variables"]["input"]["body"]

    watch.run_daily(engine, TODAY + timedelta(days=50), client)  # 30 days left: Watch becomes urgent
    assert session.of("issueUpdate")[-1]["variables"]["input"]["priority"] == 1
    assert store.get_account(engine, a["id"])["renewal_stage"] == 30


def test_first_seen_at_30_days_is_raised_at_30(engine):
    add(engine, contract_end=TODAY + timedelta(days=10), tickets_90d=0, usage_change_pct=0)
    [item] = watch.run_daily(engine, TODAY, None)
    assert item["title"].startswith("Renewal 30-day check") and item["priority"] == 2  # healthy, one step up


def test_renewals_ranked_by_milestone_then_health(engine):
    add(engine, company="Healthy Soon", contact_email="a@x.example.com", contract_end=TODAY + timedelta(days=5),
        tickets_90d=0, usage_change_pct=0)
    add(engine, company="Weak Soon", contact_email="b@x.example.com", contract_end=TODAY + timedelta(days=25))
    add(engine, company="Weak Later", contact_email="c@x.example.com", contract_end=TODAY + timedelta(days=55))
    assert [v.account["company"] for v in watch.renewals(watch.book(engine, TODAY))] == [
        "Weak Soon", "Healthy Soon", "Weak Later"]


def test_overdue_step_raised_once_and_closed_when_done(engine):
    a = add(engine, closed_on=TODAY - timedelta(days=3), contract_end=TODAY + timedelta(days=700), phone=True)
    client, session = linear()
    [item] = watch.run_daily(engine, TODAY, client)  # welcome call was due day 2
    assert item["title"] == "Overdue onboarding: Welcome call for Bluewater Physio (A-0001)"
    create = session.of("issueCreate")[0]["variables"]["input"]
    assert (create["priority"], create["dueDate"]) == (2, (TODAY - timedelta(days=1)).isoformat())
    assert watch.run_daily(engine, TODAY, client) == []
    welcome = store.list_steps(engine, a["id"])[0]
    assert watch.complete_step(engine, welcome["id"], TODAY, client) is True
    assert session.of("issueUpdate")[-1]["variables"]["input"] == {"stateId": "s-done"}
    assert store.get_step(engine, welcome["id"])["done_on"] == TODAY
    assert watch.complete_step(engine, welcome["id"], TODAY, client) is False  # already done: no second close


def test_a_failed_linear_close_leaves_the_step_open(engine):
    a = add(engine, closed_on=TODAY - timedelta(days=3), contract_end=TODAY + timedelta(days=700))
    client, session = linear()
    watch.run_daily(engine, TODAY, client)
    welcome = store.list_steps(engine, a["id"])[0]
    session.fail_on = "commentCreate"
    with pytest.raises(LinearError, match="Could not reach Linear"):
        watch.complete_step(engine, welcome["id"], TODAY, client)
    assert store.get_step(engine, welcome["id"])["done_on"] is None
    assert watch.complete_step(engine, welcome["id"], TODAY, client) is True


def test_a_failed_create_is_retried_next_run(engine):
    add(engine)
    client, session = linear(FakeLinear(fail_on="issueCreate"))
    with pytest.raises(LinearError):
        watch.run_daily(engine, TODAY, client)
    assert store.list_accounts(engine)[0]["renewal_stage"] is None
    assert [i["identifier"] for i in watch.run_daily(engine, TODAY, client)] == ["THE-2"]


def test_dry_run_writes_and_sends_nothing(engine):
    add(engine, closed_on=TODAY - timedelta(days=3))
    client, session = linear()
    items = watch.run_daily(engine, TODAY, client, dry_run=True)
    assert [i["kind"] for i in items] == ["overdue step", "renewal"]
    assert session.calls == []
    assert store.list_accounts(engine)[0]["renewal_stage"] is None
    assert all(s["raised_on"] is None for s in store.list_steps(engine))


def test_without_linear_reminders_stay_local_then_move_to_linear(engine):
    add(engine)
    [local] = watch.run_daily(engine, TODAY, None)
    assert local["identifier"] is None
    assert store.list_accounts(engine)[0]["renewal_stage"] == 90
    # A key is added later: at the next milestone the reminder is created in Linear, not "escalated".
    client, session = linear()
    [item] = watch.run_daily(engine, TODAY + timedelta(days=20), client)
    assert (item["kind"], item["identifier"]) == ("renewal", "THE-1")
    assert session.of("issueUpdate") == []


@pytest.mark.parametrize("team_key, team_id", [("", "team1"), ("  ", "team1"), ("ops", "team2"),
                                               ("operations", "team2"), ("The Deal Bot", "team1")])
def test_team_rule_matches_the_other_tools(team_key, team_id):
    assert LinearClient("k", team_key, FakeLinear()).team()["id"] == team_id


def test_unknown_team_is_a_friendly_error():
    with pytest.raises(LinearError, match="Linear team 'AUTO' not found. Your teams: THE, OPS"):
        LinearClient("k", "AUTO", FakeLinear()).team()


def test_unset_team_key_means_first_team(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "k")
    monkeypatch.delenv("LINEAR_TEAM_KEY", raising=False)
    client = client_from_env()
    client.session = FakeLinear(teams=[TEAMS[1], TEAMS[0]])
    assert client.team()["key"] == "OPS"


def test_bad_key_and_non_json_replies_are_linear_errors():
    class Session:
        def __init__(self, response):
            self.response = response

        def post(self, *a, **kw):
            return self.response

    with pytest.raises(LinearError, match="rejected the API key"):
        LinearClient("k", "", Session(FakeResponse({}, status_code=401))).team()
    with pytest.raises(LinearError, match="not JSON"):
        LinearClient("k", "", Session(FakeResponse(ValueError("bad json")))).team()
