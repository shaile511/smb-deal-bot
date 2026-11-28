"""Command line entry points. The CronJobs run `run-daily` and `digest`.

    python -m account_watch.cli seed                      # load the sample book if the database is empty
    python -m account_watch.cli import accounts.csv       # add accounts from a CSV
    python -m account_watch.cli run-daily [--today D] [--dry-run]
    python -m account_watch.cli digest [--today D] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from . import digest, importer, sample, store, watch
from .linear import LinearError, client_from_env


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="account-watch")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed", help="Load the made-up sample book if there are no accounts yet")
    imp = sub.add_parser("import", help="Add accounts from a CSV file")
    imp.add_argument("file", type=Path)
    daily = sub.add_parser("run-daily", help="Flag overdue onboarding and renewals at 90, 60 and 30 days")
    weekly = sub.add_parser("digest", help="Post the weekly digest to Slack (or print it)")
    for p in (seed, imp, daily, weekly):
        p.add_argument("--today", type=date.fromisoformat, default=None, help="Pretend today is YYYY-MM-DD")
    for p in (daily, weekly):
        p.add_argument("--dry-run", action="store_true", help="Print what would happen; write and send nothing")
    args = parser.parse_args(argv)
    today = args.today or date.today()
    engine = store.get_engine()

    if args.command == "seed":
        if store.count_accounts(engine):
            print(f"{store.count_accounts(engine)} accounts already in the book; nothing loaded.")
            return
        saved, _ = store.add_accounts(engine, sample.book(today), today)
        print(f"Loaded {len(saved)} sample accounts.")

    elif args.command == "import":
        try:
            rows = importer.parse(args.file.read_bytes())
        except OSError as exc:
            sys.exit(f"[import error] Could not read {args.file}: {exc.strerror}")
        except importer.ImportProblem as exc:
            sys.exit("[import error] Nothing was imported:\n" + "\n".join(f"  {p}" for p in exc.problems))
        saved, skipped = store.add_accounts(engine, rows, today)
        print(f"Imported {len(saved)} accounts" + (f", skipped {skipped} already in the book." if skipped else "."))

    elif args.command == "run-daily":
        linear = None if args.dry_run else client_from_env()
        if linear is None and not args.dry_run:
            print("[note] LINEAR_API_KEY not set, so reminders are recorded in the app only.")
        try:
            done = watch.run_daily(engine, today, linear, dry_run=args.dry_run)
        except LinearError as exc:
            sys.exit(f"[linear error] {exc}")
        for item in done:
            print(f"[{'would raise' if args.dry_run else item['kind']}] {item['identifier'] or '-'} {item['title']}")
        print(f"{len(done)} reminder(s){' (dry run: nothing written or sent)' if args.dry_run else ''}.")

    elif args.command == "digest":
        text = digest.build(engine, today)
        url = digest.webhook_from_env()
        if args.dry_run or not url:
            if not args.dry_run:
                print("[note] SLACK_WEBHOOK_URL not set, so the digest is printed instead of posted.\n")
            print(text)
            return
        try:
            digest.send(url, text)
        except digest.SlackError as exc:
            sys.exit(f"[slack error] {exc}")
        print("Digest posted to Slack.")


if __name__ == "__main__":
    main()
