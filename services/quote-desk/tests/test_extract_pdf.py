from types import SimpleNamespace

from quote_desk.extract import extract_needs, parse_notes_simple
from quote_desk.pdf import render_pdf
from quote_desk.quote import Needs, build_quote

NOTES = ("Spoke with Sam at Harbour Bakery (sam@harbour.example.com). 3 locations, 25 staff. "
         "Need 1 gig internet, 8 phone lines, 4 unlimited mobile plans, a static IP and backup. 2 year term.")


def test_simple_parser_reads_the_basics():
    n = parse_notes_simple(NOTES)
    assert (n.locations, n.staff, n.phone_lines, n.mobile_lines) == (3, 25, 8, 4)
    assert n.internet_speed == 1000 and n.mobile_plan == "unlimited"
    assert n.static_ip and n.backup_internet and n.term_months == 24
    assert n.contact_email == "sam@harbour.example.com"


def test_no_key_uses_simple_parser(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _, source = extract_needs(NOTES)
    assert source == "simple"


def test_claude_tool_output_is_used():
    payload = Needs(company="Harbour Bakery", locations=3, internet_speed=1000, phone_lines=8).to_dict()
    block = SimpleNamespace(type="tool_use", name="record_needs", input=payload)
    response = SimpleNamespace(content=[block], stop_reason="tool_use")
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response)))
    needs, source = extract_needs(NOTES, client=client)
    assert source == "claude" and needs.company == "Harbour Bakery" and needs.phone_lines == 8


def test_pdf_renders():
    n = parse_notes_simple(NOTES)
    n.company = "Harbour Bakery — Main St"
    data = render_pdf(n, build_quote(n), "Q-0001")
    assert data.startswith(b"%PDF") and len(data) > 1000
