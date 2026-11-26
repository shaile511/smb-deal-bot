"""Command line: rank leads, draft emails for the top ones and push them to Linear.

    python -m lead_radar.cli --top 10            # dry run unless LINEAR_API_KEY is set
    python -m lead_radar.cli --top 10 --dry-run  # never touches Linear
"""

from __future__ import annotations

import argparse

import pandas as pd

from .drafts import draft_email
from .generate import generate_leads
from .linear import push_leads
from .scoring import rank_leads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="lead CSV (default: generate fake leads)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--team", help="Linear team key or name (default: first team)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-drafts", action="store_true", help="skip email drafts")
    args = parser.parse_args()

    leads = pd.read_csv(args.csv, dtype={"contract_end": str}) if args.csv else generate_leads(200, args.seed)
    top = rank_leads(leads).head(args.top).to_dict(orient="records")

    drafts = {}
    if not args.no_drafts:
        for lead in top:
            draft = draft_email(lead)
            drafts[lead["company"]] = f"Subject: {draft.subject}\n\n{draft.body}"
            print(f"[draft:{draft.source}] {lead['company']}")

    for result in push_leads(top, drafts, team_key=args.team, dry_run=args.dry_run):
        where = f" {result.identifier} {result.url}" if result.identifier else ""
        print(f"[{result.status}] {result.title}{where}")


if __name__ == "__main__":
    main()
