"""A made-up book of accounts for Northwind Connect (a fictional provider), built relative to today
so the demo always has onboarding under way and renewals at each milestone.

Three companies carry on from the other tools: Maple Ridge Dental (Quote Desk's sample call),
and Maple & Ember Bistro Group and Corner Lantern Cafe (Lead Radar's fixed demo leads).
"""

from __future__ import annotations

from datetime import date, timedelta

PROVIDER = "Northwind Connect"

# company, contact, email, industry, monthly $, services (i=internet p=phone m=mobile),
# closed N days ago (new accounts) or renews in N days (older ones), term months, tickets in 90 days,
# usage change %, last contact N days ago (None = unknown), onboarding steps already done.
NEW = [
    ("Maple Ridge Dental", "Priya Raman", "priya@mapleridge-dental.example.com", "Dental clinic", 1187.10,
     "ipm", 16, 36, 1, 0, 3, ("welcome", "mobile")),
    ("Harbour Bakery", "Sam Okafor", "sam@harbour-bakery.example.com", "Bakery", 412.40,
     "ip", 5, 24, 0, 0, 2, ("welcome",)),
    ("Maple & Ember Bistro Group", "Priya Nair", "priya.nair@example.com", "Restaurant", 1630.00,
     "ipm", 25, 36, 4, 0, 6, ("welcome", "mobile", "internet", "porting")),
    ("Corner Lantern Cafe", "Marc Tremblay", "marc.tremblay@example.com", "Restaurant", 289.00,
     "im", 40, 12, 0, 25, 9, ("welcome", "mobile", "internet", "training", "checkin")),
]
RENEWING = [
    ("Bluewater Physio", "Hannah Cho", "hannah@bluewater-physio.example.com", "Physiotherapy clinic", 845.00,
     "ip", 20, 36, 7, -35, 120),
    ("Northgate Law", "Daniel Mensah", "daniel@northgate-law.example.com", "Law office", 1320.00,
     "ipm", 12, 36, 0, 4, 21),
    ("Cedar Lane Accounting", "Olivia Brooks", "olivia@cedarlane-cpa.example.com", "Accounting firm", 690.00,
     "ip", 45, 24, 0, -15, 30),
    ("Prairie Auto Repair", "Luis Moreno", "luis@prairie-auto.example.com", "Auto repair", 455.00,
     "ip", 52, 36, 3, 0, 100),
    ("Summit Realty Group", "Grace Liu", "grace@summit-realty.example.com", "Real estate agency", 1975.00,
     "ipm", 80, 36, 6, -12, 40),
    ("Lakeshore Fitness", "Noah Bergeron", "noah@lakeshore-fitness.example.com", "Fitness studio", 520.00,
     "i", -10, 24, 4, -40, 60),
    ("Riverbend Salon", "Amara Singh", "amara@riverbend-salon.example.com", "Salon", 240.00,
     "ip", 88, 24, 1, 30, 25),
]
MID_TERM = [
    ("Oakridge Construction", "Ben Kowalski", "ben@oakridge-build.example.com", "Construction", 1410.00,
     "im", 400, 36, 8, -32, 150),
    ("Granite Peak Retail", "Chloe Martin", "chloe@granitepeak.example.com", "Retail store", 760.00,
     "ip", 300, 36, 1, 3, 45),
    ("Willow Creek Vet", "Ethan Park", "ethan@willowcreek-vet.example.com", "Veterinary clinic", 980.00,
     "ipm", 500, 36, 2, 22, 35),
    ("Brightside Dental Group", "Fatima Haddad", "fatima@brightside-dental.example.com", "Dental clinic", 2240.00,
     "ipm", 200, 36, 3, 0, 15),
    ("Elm Street Law", "George Adeyemi", "george@elmstreet-law.example.com", "Law office", 610.00,
     "ip", 150, 24, 0, -5, 95),
]


def _term_days(months: int) -> int:
    return months * 365 // 12


def _row(company, contact, email, industry, value, services, closed_on, contract_end, tickets, usage,
         last_contact, today, steps_done=()):
    return {"company": company, "contact_name": contact, "contact_email": email, "industry": industry,
            "monthly_value": value, "internet": "i" in services, "phone": "p" in services,
            "mobile": "m" in services, "closed_on": closed_on, "contract_end": contract_end,
            "tickets_90d": tickets, "usage_change_pct": usage,
            "last_contact_on": None if last_contact is None else today - timedelta(days=last_contact),
            "steps_done": list(steps_done)}


def book(today: date | None = None) -> list[dict]:
    today = today or date.today()
    rows = []
    for company, contact, email, industry, value, services, ago, term, tickets, usage, last, done in NEW:
        closed = today - timedelta(days=ago)
        rows.append(_row(company, contact, email, industry, value, services, closed,
                         closed + timedelta(days=_term_days(term)), tickets, usage, last, today, done))
    for company, contact, email, industry, value, services, renews_in, term, tickets, usage, last in RENEWING + MID_TERM:
        end = today + timedelta(days=renews_in)
        rows.append(_row(company, contact, email, industry, value, services,
                         end - timedelta(days=_term_days(term)), end, tickets, usage, last, today))
    return rows
