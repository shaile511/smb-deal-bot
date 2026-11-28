import json
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

from account_watch import cli, digest, linear, sample, store

TODAY = date(2026, 11, 28)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'aw.db'}")
    for name in ("LINEAR_API_KEY", "SLACK_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)
    engine = store.get_engine()
    store.add_accounts(engine, sample.book(TODAY), TODAY)
    return engine


def test_digest_lists_what_needs_the_rep(engine):
    text = digest.build(engine, TODAY)
    assert text.splitlines()[0] == "*Account Watch weekly digest, November 28, 2026*"
    assert "16 accounts · 7 renewing within 90 days · 2 at risk · 3 onboarding steps overdue" in text
    renewals = text.split("*Renewals, most urgent first*\n")[1].split("\n\n")[0].splitlines()
    assert renewals[0] == "• A-0005 Bluewater Physio: in 20 days, health 40 (At risk)"
    assert "• A-0012 Oakridge Construction: health 40. -25: 8 support tickets in the last 90 days" in text
    assert "• A-0001 Maple Ridge Dental: Port phone numbers, due 2026-11-26" in text
    assert "• A-0004 Corner Lantern Cafe: Usage up 25%: offer a bigger plan" in text


def test_digest_on_an_empty_book(tmp_path):
    empty = store.get_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    assert digest.build(empty, TODAY).endswith("Nothing needs you this week.")


def test_long_sections_are_cut_at_ten(tmp_path):
    e = store.get_engine(f"sqlite:///{tmp_path / 'many.db'}")
    store.add_accounts(e, [{"company": f"Co {i}", "contact_email": f"c{i}@x.example.com", "closed_on": date(2024, 1, 1),
                            "contract_end": TODAY + timedelta(days=20 + i)} for i in range(13)], TODAY)
    assert "• and 3 more in the dashboard" in digest.build(e, TODAY)


@pytest.fixture
def stand_in():
    """A local stand-in for Slack and Linear. The real requests library talks to it over HTTP."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, dict(self.headers), body))
            if self.path == "/slack/bad":
                status, reply = 404, b"no_service"
            elif self.path == "/linear":
                status, reply = 200, json.dumps({"data": {"teams": {"nodes": [
                    {"id": "t1", "key": "THE", "name": "The Deal Bot", "states": {"nodes": []}}]}}}).encode()
            else:
                status, reply = 200, b"ok"
            self.send_response(status)
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()


def test_slack_post_over_real_http(stand_in):
    base, seen = stand_in

    class ToStandIn(requests.Session):  # webhooks must be https; route the request to the local stand-in
        def post(self, url, **kw):
            return super().post(url.replace("https://hooks.slack.test", base), **kw)

    digest.send("https://hooks.slack.test/slack/ok", "hello", ToStandIn())
    path, headers, body = seen[-1]
    assert (path, body) == ("/slack/ok", {"text": "hello"}) and headers["Content-Type"] == "application/json"


def test_slack_errors_are_plain(stand_in, monkeypatch):
    base, _ = stand_in
    with pytest.raises(digest.SlackError, match="must be an https://"):
        digest.send("http://hooks.example.com/x", "hi")

    class ToStandIn(requests.Session):  # send the https URL to the local stand-in instead
        def post(self, url, **kw):
            return super().post(url.replace("https://hooks.slack.test", base), **kw)

    with pytest.raises(digest.SlackError, match=r"HTTP 404: no_service"):
        digest.send("https://hooks.slack.test/slack/bad", "hi", ToStandIn())
    digest.send("https://hooks.slack.test/slack/ok", "hi", ToStandIn())

    class Down(requests.Session):
        def post(self, url, **kw):
            raise requests.ConnectionError("down")

    with pytest.raises(digest.SlackError, match="Could not reach Slack"):
        digest.send("https://hooks.slack.test/x", "hi", Down())


def test_linear_request_over_real_http(stand_in, monkeypatch):
    base, seen = stand_in
    monkeypatch.setattr(linear, "API_URL", base + "/linear")
    assert linear.LinearClient("lin_api_test", "the").team()["id"] == "t1"
    path, headers, body = seen[-1]
    assert headers["Authorization"] == "lin_api_test" and "teams" in body["query"]


def test_cli_seed_run_daily_and_digest(engine, capsys):
    cli.main(["seed", "--today", "2026-11-28"])
    assert "already in the book" in capsys.readouterr().out
    cli.main(["run-daily", "--today", "2026-11-28", "--dry-run"])
    out = capsys.readouterr().out
    assert "[would raise] - Renewal 30-day check: Bluewater Physio (A-0005)" in out
    assert "10 reminder(s) (dry run: nothing written or sent)." in out
    assert all(a["renewal_stage"] is None for a in store.list_accounts(engine))
    cli.main(["run-daily", "--today", "2026-11-28"])
    assert "LINEAR_API_KEY not set" in capsys.readouterr().out
    cli.main(["run-daily", "--today", "2026-11-28"])
    assert "0 reminder(s)." in capsys.readouterr().out
    cli.main(["digest", "--today", "2026-11-28"])
    out = capsys.readouterr().out
    assert "SLACK_WEBHOOK_URL not set" in out and "weekly digest" in out


def test_cli_dry_run_digest_never_posts(engine, capsys, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setattr(digest, "send", lambda *a, **k: pytest.fail("dry run posted to Slack"))
    cli.main(["digest", "--dry-run", "--today", "2026-11-28"])
    assert "weekly digest" in capsys.readouterr().out


def test_cli_import_reports_problems(engine, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("company,contact_email,closed_on,contract_end\nA,a@a.example.com,soon,2027-01-01\n")
    with pytest.raises(SystemExit, match="Row 2: closed_on 'soon' is not a date"):
        cli.main(["import", str(bad)])
    good = tmp_path / "good.csv"
    good.write_text("company,contact_email,closed_on,contract_end\nA,a@a.example.com,2026-11-01,2027-01-01\n")
    cli.main(["import", str(good)])
    with pytest.raises(SystemExit, match="Could not read"):
        cli.main(["import", str(tmp_path / "missing.csv")])
