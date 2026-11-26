"""Smoke test: the dashboard renders on the pinned Streamlit version without errors.

Catches calls to Streamlit features newer than requirements.txt allows.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "lead_radar" / "app.py")


def test_dashboard_renders_in_demo_mode(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Lead Radar"
    assert len(at.dataframe) == 1
