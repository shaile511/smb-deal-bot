from datetime import date, timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "account_watch" / "app.py")
STREAMLIT_CLOUD = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


def demo_env(monkeypatch):
    for name in ("DATABASE_URL", "POSTGRES_HOST", "ACCOUNT_WATCH_DATA", "LINEAR_API_KEY", "SLACK_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)


def start(path=APP):
    at = AppTest.from_file(path, default_timeout=60).run()
    assert not at.exception
    return at


def test_demo_loads_the_sample_book_with_no_keys(monkeypatch):
    demo_env(monkeypatch)
    at = start()
    assert at.title[0].value == "Account Watch"
    assert any("Demo mode: no Linear or Slack key" in i.value for i in at.info)
    assert next(m for m in at.metric if m.label == "Accounts").value == "16"
    assert any("weekly digest" in c.value for c in at.code)


def test_streamlit_cloud_entry_point(monkeypatch):
    demo_env(monkeypatch)
    assert start(STREAMLIT_CLOUD).title[0].value == "Account Watch"


def test_daily_check_runs_once_then_has_nothing_new(monkeypatch):
    demo_env(monkeypatch)
    at = start()
    next(b for b in at.button if b.label == "Run the daily check").click().run()
    assert not at.exception
    assert any("10 reminder(s) recorded here." in s.value for s in at.success)
    next(b for b in at.button if b.label == "Run the daily check").click().run()
    assert any("Nothing new" in c.value for c in at.caption)


def test_done_button_is_keyed_by_step_and_clears_the_overdue_step(monkeypatch):
    demo_env(monkeypatch)
    at = start()
    assert next(m for m in at.metric if m.label == "Onboarding steps overdue").value == "3"
    done = [b for b in at.button if b.label == "Done"]
    assert len({b.key for b in done}) == len(done) and all(b.key.startswith("done-") for b in done)
    # The lowest open step id is Maple Ridge Dental's overdue "Install internet".
    first_open = min(int(b.key.split("-")[1]) for b in done)
    next(b for b in done if b.key == f"done-{first_open}").click().run()
    assert not at.exception
    assert next(m for m in at.metric if m.label == "Onboarding steps overdue").value == "2"


def test_demo_visitors_do_not_share_a_book(monkeypatch):
    demo_env(monkeypatch)
    a = start()
    next(b for b in a.button if b.label == "Run the daily check").click().run()
    b = start()
    renewals = b.dataframe[0].value
    assert set(renewals["Raised"]) == {"not yet"}


def test_pretend_date_moves_renewals_forward(monkeypatch):
    demo_env(monkeypatch)
    at = start()
    at.date_input[0].set_value(date.today() + timedelta(days=60)).run()
    assert not at.exception
    assert int(next(m for m in at.metric if m.label == "Renewing within 90 days").value) > 7


def test_shared_database_starts_empty_with_a_load_button(tmp_path, monkeypatch):
    demo_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    at = start()
    load = next(b for b in at.button if b.label == "Load the sample book")
    load.click().run()
    assert not at.exception
    assert next(m for m in at.metric if m.label == "Accounts").value == "16"
    assert not any(b.label == "Load the sample book" for b in at.button)
