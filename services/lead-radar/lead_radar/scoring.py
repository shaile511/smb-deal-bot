"""Score leads on fit (who they are) and timing (when they can switch).

Every point comes with a plain-English reason, so a rep can see why a lead ranks where it does.
Weights are a starting guess based on selling to small businesses, not a trained model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .generate import NO_BUSINESS_PLAN, OUR_COMPANY

# How well each industry tends to fit a bundled internet + phone + mobile offer (out of 20).
INDUSTRY_FIT = {
    "Dental clinic": 20,
    "Law office": 18,
    "Real estate agency": 18,
    "Accounting firm": 16,
    "Retail store": 15,
    "Restaurant": 12,
    "Auto repair": 10,
    "Fitness studio": 10,
    "Construction": 8,
    "Salon": 6,
}


@dataclass
class Score:
    total: int = 0
    reasons: list[str] = field(default_factory=list)
    skip: bool = False

    def add(self, points: int, reason: str) -> None:
        self.total += points
        self.reasons.append(f"+{points} {reason}" if points >= 0 else f"{points} {reason}")


REQUIRED_COLUMNS = ["company", "contact_name", "city", "industry", "employees", "locations",
                    "current_provider", "contract_end"]

# Contract end dates people actually type: 2027-02, 2027-02-15, 2027/02, 02/2027.
_YEAR_FIRST = re.compile(r"^(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?$")
_MONTH_FIRST = re.compile(r"^(\d{1,2})/(\d{4})$")


def parse_contract_end(value) -> tuple[int, int] | None:
    """(year, month) from a contract end, or None when it is blank. ValueError if unreadable."""
    text = "" if value is None else str(value).strip()
    if not text or text.lower() == "nan":
        return None
    match = _YEAR_FIRST.match(text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
    else:
        match = _MONTH_FIRST.match(text)
        if not match:
            raise ValueError(f"contract end {text!r} is not a date like 2027-02 or 02/2027")
        month, year = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"contract end {text!r} has no month {month}")
    return year, month


def months_until(contract_end: str, today: date) -> int | None:
    """Whole months from today to a contract end. None means the field is blank."""
    parsed = parse_contract_end(contract_end)
    if parsed is None:
        return None
    year, month = parsed
    return (year - today.year) * 12 + (month - today.month)


def check_leads(leads: pd.DataFrame) -> list[str]:
    """Plain-English problems with an uploaded lead list. Empty means it can be scored."""
    missing = [c for c in REQUIRED_COLUMNS if c not in leads.columns]
    if missing:
        return [f"Missing column(s): {', '.join(missing)}. Expected: {', '.join(REQUIRED_COLUMNS)}."]
    problems = []
    for i, row in leads.fillna("").iterrows():
        line = i + 2  # header is line 1
        for col in ("employees", "locations"):
            try:
                int(float(row[col]))
            except (TypeError, ValueError):
                problems.append(f"Line {line}: {col} {row[col]!r} is not a number.")
        try:
            parse_contract_end(row["contract_end"])
        except ValueError as exc:
            problems.append(f"Line {line}: {exc}.")
    return problems


def score_lead(lead: dict, today: date | None = None) -> Score:
    today = today or date.today()
    s = Score()

    if lead["current_provider"] == OUR_COMPANY:
        s.skip = True
        s.reasons.append("Already a customer: route to account management, not prospecting")
        return s

    # Fit: size (max 20). Very small shops buy little; 20-49 staff is the sweet spot.
    employees = int(float(lead["employees"]))
    if employees < 5:
        s.add(5, f"{employees} staff: small deal size")
    elif employees < 20:
        s.add(12, f"{employees} staff")
    elif employees < 50:
        s.add(20, f"{employees} staff: ideal size")
    else:
        s.add(14, f"{employees} staff: larger, longer sales cycle")

    # Fit: locations (max 20). Each extra site means more lines and a stronger bundle case.
    locations = int(float(lead["locations"]))
    if locations == 1:
        s.add(5, "1 location")
    elif locations <= 3:
        s.add(15, f"{locations} locations: multi-site bundle")
    else:
        s.add(20, f"{locations} locations: strong multi-site bundle")

    # Fit: industry (max 20).
    fit = INDUSTRY_FIT.get(lead["industry"], 8)
    s.add(fit, f"{lead['industry']} fits the bundle offer")

    # Timing (max 40).
    months = months_until(lead["contract_end"], today)
    if months is None and lead["current_provider"] == NO_BUSINESS_PLAN:
        s.add(30, f"On a {NO_BUSINESS_PLAN.lower()}, can switch any time")
    elif months is None:
        # A blank end date on a business provider usually means nobody knows it yet, not "no contract".
        s.add(15, "Contract end unknown: ask on the first call")
    elif months < 0:
        s.add(20, "Contract already ended: likely month-to-month now")
    elif months <= 1:
        s.add(25, "Contract ends within a month: may already be renewing")
    elif months <= 4:
        s.add(40, f"Contract ends in {months} months: best time to reach out")
    elif months <= 6:
        s.add(25, f"Contract ends in {months} months")
    elif months <= 12:
        s.add(10, f"Contract ends in {months} months: plant a seed")
    else:
        s.add(0, f"Contract ends in {months} months: too early")

    return s


def rank_leads(leads: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    """Return prospects sorted best first, with score and reasons. Existing customers are dropped."""
    today = today or date.today()
    scored = []
    for lead in leads.fillna("").to_dict(orient="records"):
        s = score_lead(lead, today)
        if s.skip:
            continue
        scored.append({**lead, "score": s.total, "reasons": s.reasons})
    ranked = pd.DataFrame(scored)
    if ranked.empty:
        return ranked
    return ranked.sort_values(["score", "employees"], ascending=[False, False]).reset_index(drop=True)
