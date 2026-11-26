"""First-touch email drafts for top leads.

With ANTHROPIC_API_KEY set, Claude writes the draft. Without it, a plain template is used,
so the demo still runs. Either way the rep edits before anything is sent; nothing is sent here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .generate import OUR_COMPANY

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = f"""You write short first-touch sales emails for a rep at {OUR_COMPANY}, a fictional
provider of business internet, phone lines and mobile plans for small businesses in Canada.

Write like a helpful local rep, not a marketer:
- 90 words or fewer, plain language, no hype words, no exclamation marks.
- Open with something specific to the business (industry, size, locations or contract timing).
- Offer one concrete reason to talk, and ask for a 15-minute call.
- Never invent prices, discounts or facts that are not in the lead details.
- Return the subject on the first line as "Subject: ...", then a blank line, then the body.
"""


@dataclass
class Draft:
    subject: str
    body: str
    source: str  # "claude" or "template"


def lead_summary(lead: dict) -> str:
    contract = lead.get("contract_end") or "none (on a consumer plan)"
    reasons = "\n".join(f"- {r}" for r in lead.get("reasons", []))
    return (
        f"Company: {lead['company']}\n"
        f"Contact: {lead['contact_name']}\n"
        f"Industry: {lead['industry']}\n"
        f"Staff: {lead['employees']}\n"
        f"Locations: {lead['locations']}\n"
        f"Current provider: {lead['current_provider']}\n"
        f"Contract end (YYYY-MM): {contract}\n"
        f"Why this lead ranked high:\n{reasons}"
    )


def _split(text: str) -> tuple[str, str]:
    lines = text.strip().splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        return lines[0].split(":", 1)[1].strip(), "\n".join(lines[1:]).strip()
    return "Quick question", text.strip()


def template_draft(lead: dict) -> Draft:
    first_name = lead["contact_name"].split()[0]
    sites = f"your {lead['locations']} locations" if int(lead["locations"]) > 1 else "your team"
    if lead.get("contract_end"):
        timing = f"Your current service is up for renewal around {lead['contract_end']}, so it is a good moment to compare options."
    else:
        timing = "Many businesses your size start on a home plan and outgrow it, especially for phones and uptime."
    body = (
        f"Hi {first_name},\n\n"
        f"I work with {lead['industry'].lower()}s in your area on internet, phone lines and mobile plans. "
        f"{timing} I can put together a simple side-by-side for {sites} in about 15 minutes.\n\n"
        f"Would a quick call next week work?\n\n"
        f"Thanks,\nYour {OUR_COMPANY} rep"
    )
    return Draft(subject=f"Internet and phones for {lead['company']}", body=body, source="template")


def claude_draft(lead: dict, client=None) -> Draft:
    import anthropic

    client = client or anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        # A short email does not need deep reasoning.
        output_config={"effort": "low"},
        # If a request is ever declined, the API retries it on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Write the email for this lead.\n\n{lead_summary(lead)}"}],
    )
    if response.stop_reason == "refusal":
        return template_draft(lead)
    text = "".join(block.text for block in response.content if block.type == "text")
    subject, body = _split(text)
    return Draft(subject=subject, body=body, source="claude")


def draft_email(lead: dict, client=None) -> Draft:
    """Claude when a key is set (or a client is passed in), otherwise the template."""
    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        return template_draft(lead)
    try:
        return claude_draft(lead, client)
    except Exception as exc:  # keep the demo usable if the API is unreachable
        draft = template_draft(lead)
        draft.body += f"\n\n(Claude draft unavailable: {type(exc).__name__}. Showing the template.)"
        return draft
