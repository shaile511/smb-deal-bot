import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import anthropic
import pytest

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


def fake_response(payload: dict, stop_reason="end_turn"):
    block = SimpleNamespace(type="text", text=json.dumps(payload))
    return SimpleNamespace(content=[block], stop_reason=stop_reason)


def test_claude_json_output_is_used():
    payload = Needs(company="Harbour Bakery", locations=3, internet_speed=1000, phone_lines=8).to_dict()
    response = fake_response(payload)
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response)))
    needs, source = extract_needs(NOTES, client=client)
    assert source == "claude" and needs.company == "Harbour Bakery" and needs.phone_lines == 8


def test_refusal_falls_back_to_simple_parser():
    response = fake_response({}, stop_reason="refusal")
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response)))
    needs, source = extract_needs(NOTES, client=client)
    assert source == "simple" and "Claude unavailable" in needs.notes


@pytest.fixture
def local_api():
    """A stand-in for the Messages API. It records the request the real SDK sends, and answers
    with a 400 if the request forces a tool, the way Claude Opus 5.5 does."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            if body.get("tool_choice", {}).get("type") in ("tool", "any"):
                status, reply = 400, {"type": "error", "error": {"type": "invalid_request_error", "message":
                                      'tool_choice: type "tool" and "any" are not supported for this model.'}}
            else:
                needs = Needs(company="Harbour Bakery", contact_name="Sam", locations=3, staff=25,
                              internet_speed=1000, phone_lines=8, mobile_lines=4, mobile_plan="unlimited",
                              static_ip=True, backup_internet=True, term_months=24).to_dict()
                status, reply = 200, {"id": "msg_1", "type": "message", "role": "assistant",
                                      "model": body["model"], "stop_reason": "end_turn", "stop_sequence": None,
                                      "content": [{"type": "text", "text": json.dumps(needs)}],
                                      "usage": {"input_tokens": 10, "output_tokens": 10}}
            data = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = anthropic.Anthropic(api_key="test", base_url=f"http://127.0.0.1:{server.server_port}", max_retries=0)
    yield client, seen
    server.shutdown()


def test_real_sdk_request_is_accepted(local_api):
    client, seen = local_api
    needs, source = extract_needs(NOTES, client=client)
    assert source == "claude", needs.notes
    assert (needs.company, needs.locations, needs.phone_lines, needs.term_months) == ("Harbour Bakery", 3, 8, 24)
    body = seen[0]
    assert body["model"] == "claude-opus-5-5"
    assert "tool_choice" not in body and "tools" not in body
    schema = body["output_config"]["format"]["schema"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert schema["additionalProperties"] is False and set(schema["required"]) == set(schema["properties"])


def test_pdf_renders():
    n = parse_notes_simple(NOTES)
    n.company = "Harbour Bakery — Main St"
    data = render_pdf(n, build_quote(n), "Q-0001")
    assert data.startswith(b"%PDF") and len(data) > 1000
