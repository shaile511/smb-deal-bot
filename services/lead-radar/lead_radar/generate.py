"""Generate a fictional SMB territory list. Every row is made up."""

from __future__ import annotations

import argparse
import random
from datetime import date

import pandas as pd
from faker import Faker

# Fictional providers. "Northwind Connect" is the demo company we sell for.
OUR_COMPANY = "Northwind Connect"
COMPETITORS = ["Bluepeak Telecom", "Harbor Networks", "Summit Fiber", "Lakeside Cable"]
NO_BUSINESS_PLAN = "Consumer plan"

INDUSTRIES = [
    "Dental clinic",
    "Law office",
    "Real estate agency",
    "Restaurant",
    "Retail store",
    "Accounting firm",
    "Auto repair",
    "Fitness studio",
    "Construction",
    "Salon",
]

COLUMNS = [
    "company",
    "contact_name",
    "contact_email",
    "city",
    "industry",
    "employees",
    "locations",
    "current_provider",
    "contract_end",
]


def _add_months(start: date, months: int) -> date:
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def generate_leads(count: int = 200, seed: int = 42, today: date | None = None) -> pd.DataFrame:
    """Return `count` fictional small businesses. Same seed gives the same list."""
    today = today or date.today()
    rng = random.Random(seed)
    fake = Faker("en_CA")
    fake.seed_instance(seed)

    rows = []
    for _ in range(count):
        employees = rng.choice([rng.randint(2, 9), rng.randint(10, 49), rng.randint(50, 199)])
        # Keep sites realistic for headcount: tiny shops have one, only larger firms spread out.
        if employees < 10:
            locations = 1
        elif employees < 50:
            locations = rng.choice([1, 1, 1, 2, 2, 3])
        else:
            locations = rng.choice([1, 2, 3, rng.randint(4, 8)])
        provider = rng.choices(
            [*COMPETITORS, NO_BUSINESS_PLAN, OUR_COMPANY], weights=[18, 18, 18, 18, 18, 10]
        )[0]
        if provider == NO_BUSINESS_PLAN:
            contract_end = ""  # month-to-month, no business contract
        else:
            contract_end = _add_months(today, rng.randint(-1, 30)).strftime("%Y-%m")
        first, last = fake.first_name(), fake.last_name()
        company = fake.company()
        rows.append(
            {
                "company": company,
                "contact_name": f"{first} {last}",
                # example.com is reserved for documentation, so no real inbox is ever hit.
                "contact_email": f"{first.lower()}.{last.lower()}@example.com",
                "city": fake.city(),
                "industry": rng.choice(INDUSTRIES),
                "employees": employees,
                "locations": locations,
                "current_provider": provider,
                "contract_end": contract_end,
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a fictional SMB lead list to CSV.")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="leads.csv")
    args = parser.parse_args()
    generate_leads(args.count, args.seed).to_csv(args.out, index=False)
    print(f"Wrote {args.count} fictional leads to {args.out}")


if __name__ == "__main__":
    main()
