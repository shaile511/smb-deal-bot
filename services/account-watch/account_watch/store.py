"""Accounts and their onboarding steps.

Where they live: DATABASE_URL if set; otherwise the chart's Postgres when POSTGRES_HOST is set
(the cluster); otherwise a SQLite file in ACCOUNT_WATCH_DATA. With none of these (the public demo),
the app gives each browser tab its own in-memory database.

Tables are prefixed with aw_ because the cluster's Postgres is shared with Quote Desk.
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import (Boolean, Column, Date, Float, ForeignKey, Integer, MetaData, String, Table,
                        create_engine, func, insert, select, update)
from sqlalchemy.engine import URL, Engine
from sqlalchemy.pool import StaticPool

from . import rules

metadata = MetaData()

accounts = Table(
    "aw_accounts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("code", String(20), unique=True, nullable=False),
    Column("company", String(200), nullable=False),
    Column("contact_name", String(200), nullable=False, default=""),
    Column("contact_email", String(200), nullable=False, default=""),
    Column("industry", String(100), nullable=False, default=""),
    Column("monthly_value", Float, nullable=False, default=0.0),
    Column("internet", Boolean, nullable=False, default=False),
    Column("phone", Boolean, nullable=False, default=False),
    Column("mobile", Boolean, nullable=False, default=False),
    Column("closed_on", Date, nullable=False),
    Column("contract_end", Date, nullable=False),
    Column("tickets_90d", Integer, nullable=False, default=0),
    Column("usage_change_pct", Integer, nullable=False, default=0),
    Column("last_contact_on", Date, nullable=True),
    # Renewal reminder: the milestone already raised (90, 60, 30) and its Linear issue, if any.
    Column("renewal_stage", Integer, nullable=True),
    Column("renewal_linear_id", String(64), nullable=True),
    Column("renewal_linear_identifier", String(32), nullable=True),
    Column("renewal_linear_url", String(300), nullable=True),
    sqlite_autoincrement=True,  # never reuse an id, so never reuse an account code
)

steps = Table(
    "aw_onboarding_steps", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_id", Integer, ForeignKey("aw_accounts.id"), nullable=False),
    Column("key", String(20), nullable=False),
    Column("name", String(100), nullable=False),
    Column("due_on", Date, nullable=False),
    Column("done_on", Date, nullable=True),
    Column("raised_on", Date, nullable=True),  # when the daily check flagged it overdue
    Column("linear_id", String(64), nullable=True),
    Column("linear_identifier", String(32), nullable=True),
    Column("linear_url", String(300), nullable=True),
)


def default_url() -> str | URL:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    if os.environ.get("POSTGRES_HOST"):
        # Built from parts so any character in the password is escaped.
        return URL.create("postgresql+psycopg", username=os.environ.get("POSTGRES_USER", "dealbot"),
                          password=os.environ.get("POSTGRES_PASSWORD"), host=os.environ["POSTGRES_HOST"],
                          port=int(os.environ.get("POSTGRES_PORT", "5432")),
                          database=os.environ.get("POSTGRES_DB", "dealbot"))
    folder = Path(os.environ.get("ACCOUNT_WATCH_DATA") or Path(__file__).resolve().parent.parent)
    return f"sqlite:///{folder / 'account_watch.db'}"


def has_configured_db() -> bool:
    """True when a database was chosen on purpose, rather than left to the per-tab demo default."""
    return any(os.environ.get(k) for k in ("DATABASE_URL", "POSTGRES_HOST", "ACCOUNT_WATCH_DATA"))


def memory_engine() -> Engine:
    """A private in-memory database, one per visitor of the public demo."""
    engine = create_engine("sqlite://", future=True, poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    return engine


def get_engine(url: str | URL | None = None) -> Engine:
    engine = create_engine(url or default_url(), future=True, pool_pre_ping=True)
    metadata.create_all(engine)
    return engine


def account_code(account_id: int) -> str:
    return f"A-{account_id:04d}"


def _same(a: dict, b: dict) -> bool:
    return (a["company"].strip().lower(), (a.get("contact_email") or "").strip().lower()) == \
           (b["company"].strip().lower(), (b.get("contact_email") or "").strip().lower())


def add_accounts(engine: Engine, rows: list[dict], today: date) -> tuple[list[dict], int]:
    """Save new accounts and their onboarding checklists. Returns (saved rows, how many skipped).

    A row whose company and contact email are already in the book is skipped, so importing the
    same file twice does not double the book. Each account's code (A-0001, ...) comes from its
    row id, assigned once here by the database. A row may carry `steps_done`, a list of step
    keys already finished (used by the sample book).
    """
    existing = list_accounts(engine)
    saved_ids, skipped = [], 0
    with engine.begin() as conn:
        for row in rows:
            if any(_same(row, e) for e in existing):
                skipped += 1
                continue
            values = {k: row[k] for k in (
                "company", "contact_name", "contact_email", "industry", "monthly_value", "internet", "phone",
                "mobile", "closed_on", "contract_end", "tickets_90d", "usage_change_pct", "last_contact_on")
                if k in row}
            account_id = conn.execute(insert(accounts).values(
                code=f"pending-{uuid.uuid4().hex[:12]}", **values)).inserted_primary_key[0]
            conn.execute(update(accounts).where(accounts.c.id == account_id).values(code=account_code(account_id)))
            done = set(row.get("steps_done") or ())
            for key, name, due in rules.onboarding_plan(row["closed_on"], row.get("internet", False),
                                                        row.get("phone", False), row.get("mobile", False), today):
                conn.execute(insert(steps).values(account_id=account_id, key=key, name=name, due_on=due,
                                                  done_on=due if key in done else None))
            existing.append(row)
            saved_ids.append(account_id)
    return [get_account(engine, i) for i in saved_ids], skipped


def count_accounts(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(accounts)).scalar_one()


def get_account(engine: Engine, account_id: int) -> dict:
    with engine.connect() as conn:
        return dict(conn.execute(select(accounts).where(accounts.c.id == account_id)).mappings().one())


def list_accounts(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(accounts).order_by(accounts.c.id)).mappings().all()]


def list_steps(engine: Engine, account_id: int | None = None) -> list[dict]:
    query = (select(steps, accounts.c.code, accounts.c.company)
             .join(accounts, accounts.c.id == steps.c.account_id)
             .order_by(steps.c.due_on, steps.c.id))
    if account_id is not None:
        query = query.where(steps.c.account_id == account_id)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(query).mappings().all()]


def get_step(engine: Engine, step_id: int) -> dict:
    return next(s for s in list_steps(engine) if s["id"] == step_id)


def mark_step_raised(engine: Engine, step_id: int, today: date, linear_id: str | None,
                     identifier: str | None, url: str | None) -> None:
    with engine.begin() as conn:
        conn.execute(update(steps).where(steps.c.id == step_id).values(
            raised_on=today, linear_id=linear_id, linear_identifier=identifier, linear_url=url))


def mark_step_done(engine: Engine, step_id: int, today: date) -> None:
    with engine.begin() as conn:
        conn.execute(update(steps).where(steps.c.id == step_id).values(done_on=today))


def set_renewal(engine: Engine, account_id: int, stage: int, linear_id: str | None = None,
                identifier: str | None = None, url: str | None = None) -> None:
    values = {"renewal_stage": stage}
    if linear_id:
        values.update(renewal_linear_id=linear_id, renewal_linear_identifier=identifier, renewal_linear_url=url)
    with engine.begin() as conn:
        conn.execute(update(accounts).where(accounts.c.id == account_id).values(**values))
