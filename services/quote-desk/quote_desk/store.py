"""Quotes and their follow-ups, stored in SQLite locally or Postgres in the cluster (DATABASE_URL)."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import (Column, Date, Float, ForeignKey, Integer, MetaData, String, Table, Text,
                        create_engine, func, insert, select, update)
from sqlalchemy.engine import URL, Engine

FOLLOWUP_DAYS = (2, 5, 10)

metadata = MetaData()

quotes = Table(
    "quotes", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("number", String(20), unique=True, nullable=False),
    Column("company", String(200), nullable=False),
    Column("contact_name", String(200), nullable=False, default=""),
    Column("contact_email", String(200), nullable=False, default=""),
    Column("needs_json", Text, nullable=False),
    Column("quote_json", Text, nullable=False),
    Column("monthly_total", Float, nullable=False),
    Column("status", String(20), nullable=False, default="sent"),  # sent | replied
    Column("sent_on", Date, nullable=False),
    Column("replied_on", Date, nullable=True),
)

followups = Table(
    "followups", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("quote_id", Integer, ForeignKey("quotes.id"), nullable=False),
    Column("step", Integer, nullable=False),
    Column("due_on", Date, nullable=False),
    Column("status", String(20), nullable=False, default="scheduled"),  # scheduled | due | stopped
    Column("linear_id", String(64), nullable=True),
    Column("linear_identifier", String(32), nullable=True),
    Column("linear_url", String(300), nullable=True),
)


def default_url() -> str | URL:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    if os.environ.get("POSTGRES_HOST"):
        # In the cluster: build the URL from parts so any character in the password is escaped.
        return URL.create("postgresql+psycopg", username=os.environ.get("POSTGRES_USER", "dealbot"),
                          password=os.environ.get("POSTGRES_PASSWORD"), host=os.environ["POSTGRES_HOST"],
                          port=int(os.environ.get("POSTGRES_PORT", "5432")),
                          database=os.environ.get("POSTGRES_DB", "dealbot"))
    folder = Path(os.environ.get("QUOTE_DESK_DATA") or Path(__file__).resolve().parent.parent)
    path = folder / "quote_desk.db"
    return f"sqlite:///{path}"


def get_engine(url: str | URL | None = None) -> Engine:
    engine = create_engine(url or default_url(), future=True, pool_pre_ping=True)
    metadata.create_all(engine)
    return engine


def save_quote(engine: Engine, needs: dict, quote: dict, monthly_total: float,
               sent_on: date | None = None) -> dict:
    """Record a sent quote and schedule its follow-ups. Returns the stored quote row."""
    sent_on = sent_on or date.today()
    with engine.begin() as conn:
        count = conn.execute(select(func.count()).select_from(quotes)).scalar_one()
        number = f"Q-{count + 1:04d}"
        quote_id = conn.execute(insert(quotes).values(
            number=number, company=needs.get("company") or "Customer",
            contact_name=needs.get("contact_name") or "", contact_email=needs.get("contact_email") or "",
            needs_json=json.dumps(needs), quote_json=json.dumps(quote), monthly_total=monthly_total,
            status="sent", sent_on=sent_on,
        )).inserted_primary_key[0]
        for step, days in enumerate(FOLLOWUP_DAYS, start=1):
            conn.execute(insert(followups).values(quote_id=quote_id, step=step,
                                                  due_on=sent_on + timedelta(days=days), status="scheduled"))
    return get_quote(engine, quote_id)


def get_quote(engine: Engine, quote_id: int) -> dict:
    with engine.connect() as conn:
        row = conn.execute(select(quotes).where(quotes.c.id == quote_id)).mappings().one()
    return dict(row)


def list_quotes(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(select(quotes).order_by(quotes.c.id.desc())).mappings().all()
    return [dict(r) for r in rows]


def list_followups(engine: Engine, quote_id: int | None = None) -> list[dict]:
    query = (select(followups, quotes.c.number, quotes.c.company, quotes.c.contact_name)
             .join(quotes, quotes.c.id == followups.c.quote_id)
             .order_by(followups.c.due_on, followups.c.id))
    if quote_id is not None:
        query = query.where(followups.c.quote_id == quote_id)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(query).mappings().all()]


def due_followups(engine: Engine, today: date) -> list[dict]:
    return [f for f in list_followups(engine) if f["status"] == "scheduled" and f["due_on"] <= today]


def mark_due(engine: Engine, followup_id: int, linear_id: str | None, identifier: str | None,
             url: str | None) -> None:
    with engine.begin() as conn:
        conn.execute(update(followups).where(followups.c.id == followup_id).values(
            status="due", linear_id=linear_id, linear_identifier=identifier, linear_url=url))


def mark_replied(engine: Engine, quote_id: int, replied_on: date | None = None) -> list[dict]:
    """Stop the quote's open follow-ups. Returns the ones that had Linear issues to close."""
    replied_on = replied_on or date.today()
    open_ones = [f for f in list_followups(engine, quote_id) if f["status"] in ("scheduled", "due")]
    with engine.begin() as conn:
        conn.execute(update(quotes).where(quotes.c.id == quote_id).values(status="replied", replied_on=replied_on))
        conn.execute(update(followups).where(followups.c.quote_id == quote_id,
                                             followups.c.status.in_(("scheduled", "due"))).values(status="stopped"))
    return [f for f in open_ones if f["linear_id"]]
