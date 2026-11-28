"""Read a CSV of closed deals or existing accounts, with plain messages for every problem.

Nothing is imported if any row has a problem, so a half-loaded book never happens.
"""

from __future__ import annotations

import csv
import io
from datetime import date

REQUIRED = ("company", "contact_email", "closed_on", "contract_end")
OPTIONAL = ("contact_name", "industry", "monthly_value", "internet", "phone", "mobile",
            "tickets_90d", "usage_change_pct", "last_contact_on")
MAX_ROWS = 500
MAX_BYTES = 1_000_000
YES = {"yes", "y", "true", "1", "x"}
NO = {"no", "n", "false", "0", ""}
LIMITS = {"monthly_value": (0, 100_000), "tickets_90d": (0, 999), "usage_change_pct": (-100, 1000)}

TEMPLATE = ",".join(REQUIRED + OPTIONAL) + "\n" + \
    "Juniper Florist,ava@juniper-florist.example.com,2026-11-20,2028-11-20,Ava Chen,Florist,310,yes,yes,no,0,0,2026-11-25\n"


class ImportProblem(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def _date(value: str, field: str, where: str, problems: list[str]) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        problems.append(f"{where}: {field} {value!r} is not a date. Use YYYY-MM-DD, like 2027-03-31.")
        return None


def parse(data: bytes | str) -> list[dict]:
    """Return account rows ready for store.add_accounts, or raise ImportProblem listing every issue."""
    if isinstance(data, bytes):
        if len(data) > MAX_BYTES:
            raise ImportProblem([f"The file is over {MAX_BYTES // 1_000_000} MB. Split it into smaller files."])
        try:
            data = data.decode("utf-8-sig")  # Excel on Windows adds a byte-order mark
        except UnicodeDecodeError:
            raise ImportProblem(["The file is not UTF-8 text. In Excel, save it as 'CSV UTF-8'."]) from None
    reader = csv.DictReader(io.StringIO(data))
    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        raise ImportProblem([f"Missing column{'s' if len(missing) > 1 else ''}: {', '.join(missing)}. "
                             f"The first row must name the columns: {', '.join(REQUIRED)} (and optionally "
                             f"{', '.join(OPTIONAL)})."])
    rows, problems = [], []
    for n, raw in enumerate(reader, start=2):  # row 1 is the header
        if n - 1 > MAX_ROWS:
            problems.append(f"More than {MAX_ROWS} accounts. Split the file.")
            break
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k is not None}
        if not any(r.values()):
            continue
        where = f"Row {n}"
        row: dict = {}
        for field in ("company", "contact_email"):
            if not r.get(field):
                problems.append(f"{where}: {field} is empty.")
        if r.get("contact_email") and "@" not in r["contact_email"]:
            problems.append(f"{where}: contact_email {r['contact_email']!r} is not an email address.")
        row.update(company=r.get("company", ""), contact_email=r.get("contact_email", ""),
                   contact_name=r.get("contact_name", ""), industry=r.get("industry", ""))
        row["closed_on"] = _date(r.get("closed_on", ""), "closed_on", where, problems)
        row["contract_end"] = _date(r.get("contract_end", ""), "contract_end", where, problems)
        if row["closed_on"] and row["contract_end"] and row["contract_end"] <= row["closed_on"]:
            problems.append(f"{where}: contract_end {row['contract_end']} must be after closed_on {row['closed_on']}.")
        last = r.get("last_contact_on", "")
        row["last_contact_on"] = _date(last, "last_contact_on", where, problems) if last else None
        for field in ("internet", "phone", "mobile"):
            value = r.get(field, "").lower()
            if value not in YES | NO:
                problems.append(f"{where}: {field} {r[field]!r} should be yes or no.")
            row[field] = value in YES
        for field, (low, high) in LIMITS.items():
            value = r.get(field, "") or "0"
            try:
                number = float(value.replace("$", "").replace(",", "")) if field == "monthly_value" else int(value)
            except ValueError:
                problems.append(f"{where}: {field} {value!r} is not a {'number' if field == 'monthly_value' else 'whole number'}.")
                continue
            if not low <= number <= high:
                problems.append(f"{where}: {field} {value} is outside {low} to {high}.")
            row[field] = number
        rows.append(row)
    if problems:
        raise ImportProblem(problems)
    if not rows:
        raise ImportProblem(["The file has a header but no accounts."])
    return rows
