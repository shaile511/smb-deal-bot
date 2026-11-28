"""Command line: rank leads, draft emails for the top ones and push them to Linear.

    python -m lead_radar.cli --top 10            # dry run unless LINEAR_API_KEY is set
    python -m lead_radar.cli --top 10 --dry-run  # never touches Linear
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

from dotenv import find_dotenv, load_dotenv

from .drafts import draft_email
from .generate import generate_leads
from .linear import LinearError, issue_title, push_leads
from .scoring import check_leads, rank_leads


def main() -> None:
    # Read API keys from the nearest .env (repo root), on any OS. Real env vars win.
    load_dotenv(find_dotenv(usecwd=True))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="lead CSV (default: generate fake leads)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--team", help="Linear team key or name (default: first team)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-drafts", action="store_true", help="skip email drafts")
    args = parser.parse_args()

    if args.csv:
        leads = pd.read_csv(args.csv, dtype={"contract_end": str})
        problems = check_leads(leads)
        if problems:
            sys.exit("[csv error]\n" + "\n".join(problems))
        if "contact_email" not in leads.columns:
            leads["contact_email"] = ""
    else:
        leads = generate_leads(200, args.seed)
    top = rank_leads(leads).head(args.top).to_dict(orient="records")

    # Drafts only go somewhere when issues are really created, so a dry run skips them
    # instead of paying for a Claude call per lead.
    pushing = not args.dry_run and bool(os.environ.get("LINEAR_API_KEY"))
    drafts = {}
    if not args.no_drafts and not pushing:
        print("[note] Dry run: skipping email drafts, so no Claude credits are spent.")
    elif not args.no_drafts:
        for lead in top:
            draft = draft_email(lead)
            drafts[issue_title(lead)] = f"Subject: {draft.subject}\n\n{draft.body}"
            print(f"[draft:{draft.source}] {lead['company']}")

    try:
        results = push_leads(top, drafts, team_key=args.team, dry_run=args.dry_run)
    except LinearError as err:
        sys.exit(f"[linear error] {err}")
    for result in results:
        where = f" {result.identifier} {result.url}" if result.identifier else ""
        print(f"[{result.status}] {result.title}{where}")


if __name__ == "__main__":
    main()
