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

# Industry mix weighted roughly like Canada's small businesses (ISED, Key Small Business
# Statistics 2025, Table 3, Dec 2024): construction 14%, professional services 14%,
# health care 11%, other services 10%, retail 9%, food 7%, real estate 5%.
INDUSTRY_WEIGHTS = {
    "Construction": 14,
    "Law office": 7,
    "Accounting firm": 7,
    "Dental clinic": 11,
    "Auto repair": 5,
    "Salon": 5,
    "Retail store": 9,
    "Restaurant": 7,
    "Real estate agency": 5,
    "Fitness studio": 2,
}
INDUSTRIES = list(INDUSTRY_WEIGHTS)

# Staff-size bands weighted like Canada's employer businesses (same source, Table 2):
# 59% have 1-4 employees, 18% 5-9, 11% 10-19, 7% 20-49, 2.5% 50-99, about 1% 100-199.
SIZE_BANDS = [((1, 4), 59.1), ((5, 9), 18.2), ((10, 19), 11.1), ((20, 49), 7.2), ((50, 99), 2.5), ((100, 199), 1.0)]

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
        (low, high), = rng.choices([b for b, _ in SIZE_BANDS], weights=[w for _, w in SIZE_BANDS])
        employees = rng.randint(low, high)
        # Sites per business: no public Canadian figure found, so this is a guess.
        # Tiny shops have one site; only larger firms commonly spread out.
        if employees < 10:
            locations = 1
        elif employees < 20:
            locations = rng.choices([1, 2], weights=[90, 10])[0]
        elif employees < 50:
            locations = rng.choices([1, 2, 3], weights=[70, 20, 10])[0]
        else:
            locations = rng.choices([1, 2, 3, rng.randint(4, 8)], weights=[40, 25, 20, 15])[0]
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
                "industry": rng.choices(INDUSTRIES, weights=list(INDUSTRY_WEIGHTS.values()))[0],
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
