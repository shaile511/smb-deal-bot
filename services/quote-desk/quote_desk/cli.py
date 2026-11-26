"""Command line entry points. `python -m quote_desk.cli run-followups` is what the CronJob runs."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from dotenv import load_dotenv

from . import followups, store


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="quote-desk")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run-followups", help="Create Linear tasks for follow-ups that are due")
    run.add_argument("--today", type=date.fromisoformat, default=None, help="Pretend today is YYYY-MM-DD")
    args = parser.parse_args(argv)

    if args.command == "run-followups":
        engine = store.get_engine()
        linear = followups.client_from_env()
        if linear is None:
            print("[note] LINEAR_API_KEY not set, so follow-ups are marked due locally only.")
        try:
            done = followups.run_due(engine, args.today, linear)
        except followups.LinearError as exc:
            sys.exit(f"[linear error] {exc}")
        for item in done:
            print(f"[due] {item['identifier'] or '-'} {item['title']}")
        print(f"{len(done)} follow-up(s) due.")


if __name__ == "__main__":
    main()
