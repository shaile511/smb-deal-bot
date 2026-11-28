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


def demo_env(monkeypatch):
    for name in ("DATABASE_URL", "POSTGRES_HOST", "QUOTE_DESK_DATA", "ANTHROPIC_API_KEY", "LINEAR_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def save_a_quote(at, company):
    at.button[0].click().run()  # Read the notes
    next(t for t in at.text_input if t.label == "Company").set_value(company).run()
    next(b for b in at.button if b.label.startswith("Mark as sent")).click().run()
    assert not at.exception
    return at


def test_demo_visitors_do_not_share_quotes(monkeypatch):
    demo_env(monkeypatch)
    a = save_a_quote(AppTest.from_file(APP, default_timeout=60).run(), "Visitor A Bakery")
    assert any("Visitor A Bakery" in str(df.value) for df in a.dataframe)
    b = AppTest.from_file(APP, default_timeout=60).run()
    b.button[0].click().run()
    assert not b.exception
    assert not any("Visitor A Bakery" in str(df.value) for df in b.dataframe)
    assert not any(s.label == "Client replied to" for s in b.selectbox)


def test_a_quote_is_saved_once_and_the_pdf_has_its_number(monkeypatch):
    demo_env(monkeypatch)
    at = save_a_quote(AppTest.from_file(APP, default_timeout=60).run(), "Harbour Bakery")
    send = next(b for b in at.button if b.label.startswith("Mark as sent"))
    assert send.disabled
    assert any("Q-0001" in s.value for s in at.success)


def test_notes_beyond_the_form_limits_do_not_crash(monkeypatch):
    demo_env(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.text_area[0].set_value("Call with Dana at Corner Grocers. 120 stores, 1500 phone lines, need internet.").run()
    at.button[0].click().run()
    assert not at.exception
    assert next(n for n in at.number_input if n.label == "Locations").value == 100
    assert any("120" in w.value for w in at.warning)
