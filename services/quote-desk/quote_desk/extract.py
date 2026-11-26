"""Pull structured needs out of a rep's discovery-call notes.

With ANTHROPIC_API_KEY set, Claude reads the notes and fills a fixed schema (via a forced tool
call, so the output is always the same shape). Without a key, a simple keyword parser does a
rougher job, so the demo still runs. The rep always confirms the result before anything is priced.
"""

from __future__ import annotations

import os
import re

from .quote import Needs

MODEL = "claude-opus-5-5"

NEEDS_TOOL = {
    "name": "record_needs",
    "description": "Record what the small business needs, as stated in the rep's call notes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company": {"type": "string", "description": "Business name, empty if not stated"},
            "contact_name": {"type": "string", "description": "Person the rep spoke to, empty if not stated"},
            "contact_email": {"type": "string", "description": "Email if stated, else empty"},
            "staff": {"type": "integer", "description": "Number of staff, 0 if not stated"},
            "locations": {"type": "integer", "description": "Number of sites, 1 if not stated"},
            "internet_speed": {
                "type": ["integer", "null"],
                "enum": [300, 1000, 3000, None],
                "description": "Mbps tier: 300, 1000 or 3000. Pick the closest tier if they gave a speed. "
                               "1000 if they need internet but gave no speed. null if they do not need internet.",
            },
            "phone_lines": {"type": "integer", "description": "Desk/office phone lines, 0 if none"},
            "mobile_lines": {"type": "integer", "description": "Mobile plans, 0 if none"},
            "mobile_plan": {"type": "string", "enum": ["essential", "unlimited"],
                            "description": "unlimited only if they ask for unlimited or heavy data, else essential"},
            "static_ip": {"type": "boolean"},
            "managed_wifi": {"type": "boolean"},
            "backup_internet": {"type": "boolean", "description": "Backup or failover internet"},
            "term_months": {"type": "integer", "enum": [12, 24, 36],
                            "description": "Contract length they prefer; 36 if not stated"},
            "notes": {"type": "string",
                      "description": "One short line on anything that matters but does not fit the fields"},
        },
        "required": ["company", "contact_name", "contact_email", "staff", "locations", "internet_speed",
                     "phone_lines", "mobile_lines", "mobile_plan", "static_ip", "managed_wifi",
                     "backup_internet", "term_months", "notes"],
    },
}

SYSTEM_PROMPT = """You turn a sales rep's rough discovery-call notes into structured needs for a quote.
Only record what the notes say or clearly imply. Do not invent numbers: use the defaults given in the
schema when something is missing. Call the record_needs tool exactly once."""


def _num(pattern: str, text: str, default: int = 0) -> int:
    match = re.search(pattern, text, re.I)
    return int(match.group(1)) if match else default


def parse_notes_simple(notes: str) -> Needs:
    """Keyword parser used in demo mode. Rough on purpose; the rep fixes it in the form."""
    text = notes.replace(",", " ")
    needs = Needs(notes="Read by the simple parser (no Claude key). Check every field.")
    needs.staff = _num(r"(\d+)\s*(?:staff|employees|people)", text)
    needs.locations = max(1, _num(r"(\d+)\s*(?:locations?|sites?|offices?|stores?|branches|clinics?|shops?|restaurants?)", text, 1))
    needs.phone_lines = _num(r"(\d+)\s*(?:desk\s*)?(?:phone|voip|landline)s?\s*(?:lines?)?", text)
    needs.mobile_lines = _num(r"(\d+)\s*(?:unlimited\s*|basic\s*|essential\s*)?(?:mobile|cell|wireless)(?:\s*(?:plans?|lines?|phones?))?", text)
    if re.search(r"unlimited", text, re.I):
        needs.mobile_plan = "unlimited"
    if re.search(r"\b(3\s*gig|3\s*gbps|3000)\b", text, re.I):
        needs.internet_speed = 3000
    elif re.search(r"\b(300\s*(mbps|meg)?)\b", text, re.I) and not re.search(r"3000", text):
        needs.internet_speed = 300
    elif re.search(r"internet|fibre|fiber|wifi|wi-fi", text, re.I):
        needs.internet_speed = 1000
    else:
        needs.internet_speed = None
    needs.static_ip = bool(re.search(r"static\s*ip", text, re.I))
    needs.managed_wifi = bool(re.search(r"wi-?fi", text, re.I))
    needs.backup_internet = bool(re.search(r"backup|failover", text, re.I))
    if re.search(r"\b(12\s*months?|1\s*year|one year)\b", text, re.I):
        needs.term_months = 12
    elif re.search(r"\b(24\s*months?|2\s*years?|two years?)\b", text, re.I):
        needs.term_months = 24
    company = re.search(r"\bat ((?:[A-Z][\w&'-]*\s?){1,5})", notes)
    needs.company = company.group(1).strip() if company else ""
    contact = re.search(r"\bwith ([A-Z][a-z]+(?: [A-Z][a-z]+)?)", notes)
    needs.contact_name = contact.group(1) if contact else ""
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    needs.contact_email = email.group(0) if email else ""
    return needs


def claude_parse(notes: str, client=None) -> Needs:
    import anthropic

    client = client or anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        tools=[NEEDS_TOOL],
        tool_choice={"type": "tool", "name": "record_needs"},
        messages=[{"role": "user", "content": f"Call notes:\n\n{notes}"}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "record_needs":
            needs = Needs.from_dict(block.input)
            if needs.internet_speed not in (300, 1000, 3000, None):
                needs.internet_speed = 1000
            if needs.term_months not in (12, 24, 36):
                needs.term_months = 36
            if needs.mobile_plan not in ("essential", "unlimited"):
                needs.mobile_plan = "essential"
            needs.locations = max(1, int(needs.locations or 1))
            return needs
    raise ValueError(f"Claude did not return the needs (stop reason: {response.stop_reason})")


def extract_needs(notes: str, client=None) -> tuple[Needs, str]:
    """Return (needs, source) where source is "claude" or "simple"."""
    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        return parse_notes_simple(notes), "simple"
    try:
        return claude_parse(notes, client), "claude"
    except Exception as exc:  # keep the demo usable if the API is unreachable
        needs = parse_notes_simple(notes)
        needs.notes = f"Claude unavailable ({type(exc).__name__}); read by the simple parser. Check every field."
        return needs, "simple"
