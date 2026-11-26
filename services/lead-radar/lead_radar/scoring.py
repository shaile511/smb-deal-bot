"""Score leads on fit (who they are) and timing (when they can switch).

Every point comes with a plain-English reason, so a rep can see why a lead ranks where it does.
Weights are a starting guess based on selling to small businesses, not a trained model.
"""

from __future__ import annotations

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


def months_until(contract_end: str, today: date) -> int | None:
    """Whole months from today to a 'YYYY-MM' contract end. None means no contract."""
    if not contract_end:
        return None
    year, month = (int(p) for p in contract_end.split("-"))
    return (year - today.year) * 12 + (month - today.month)


def score_lead(lead: dict, today: date | None = None) -> Score:
    today = today or date.today()
    s = Score()

    if lead["current_provider"] == OUR_COMPANY:
        s.skip = True
        s.reasons.append("Already a customer: route to account management, not prospecting")
        return s

    # Fit: size (max 20). Very small shops buy little; 20-49 staff is the sweet spot.
    employees = int(lead["employees"])
    if employees < 5:
        s.add(5, f"{employees} staff: small deal size")
    elif employees < 20:
        s.add(12, f"{employees} staff")
    elif employees < 50:
        s.add(20, f"{employees} staff: ideal size")
    else:
        s.add(14, f"{employees} staff: larger, longer sales cycle")

    # Fit: locations (max 20). Each extra site means more lines and a stronger bundle case.
    locations = int(lead["locations"])
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
    if months is None:
        s.add(30, f"On a {NO_BUSINESS_PLAN.lower()}, can switch any time")
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
