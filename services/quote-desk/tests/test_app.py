from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "quote_desk" / "app.py")


def test_app_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Quote and Follow-up Desk"
    at.button[0].click().run()  # Read the notes
    assert not at.exception
    assert any("Monthly total" in m.label for m in at.metric)
    send = next(b for b in at.button if b.label.startswith("Mark as sent"))
    send.click().run()
    assert not at.exception
    assert any("Q-0001" in s.value for s in at.success)
    run = next(b for b in at.button if b.label == "Run due follow-ups")
    run.click().run()
    assert not at.exception
