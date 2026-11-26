from types import SimpleNamespace

from lead_radar.drafts import MODEL, draft_email, lead_summary, template_draft

LEAD = {
    "company": "Test Dental",
    "contact_name": "Ana Lopez",
    "industry": "Dental clinic",
    "employees": 25,
    "locations": 2,
    "current_provider": "Bluepeak Telecom",
    "contract_end": "2027-02",
    "city": "Testville",
    "reasons": ["+40 Contract ends in 3 months: best time to reach out"],
}


class FakeMessages:
    def __init__(self, text, stop_reason="end_turn"):
        self.text, self.stop_reason, self.calls = text, stop_reason, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=self.text)],
        )


def fake_client(text, stop_reason="end_turn"):
    messages = FakeMessages(text, stop_reason)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_template_used_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = draft_email(LEAD)
    assert d.source == "template"
    assert "Ana" in d.body and "2027-02" in d.body


def test_summary_carries_the_reasons():
    assert "best time to reach out" in lead_summary(LEAD)


def test_claude_draft_parses_subject_and_sends_lead():
    client, messages = fake_client("Subject: Phones for your two clinics\n\nHi Ana, ...")
    d = draft_email(LEAD, client=client)
    assert d.source == "claude"
    assert d.subject == "Phones for your two clinics"
    assert d.body.startswith("Hi Ana")
    call = messages.calls[0]
    assert call["model"] == MODEL
    assert "Test Dental" in call["messages"][0]["content"]


def test_refusal_falls_back_to_template():
    client, _ = fake_client("", stop_reason="refusal")
    assert draft_email(LEAD, client=client).source == "template"


def test_template_without_contract():
    d = template_draft({**LEAD, "contract_end": "", "locations": 1})
    assert "home plan" in d.body
