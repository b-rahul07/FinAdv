from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class IdMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LengthError(ValueError):
    pass


@event.listens_for(Session, "before_flush")
def _check_lengths(session, _ctx, _instances):
    """Enforce VARCHAR lengths everywhere. Postgres rejects over-long values; SQLite silently stores them,
    so without this check such bugs only appear in production."""
    for obj in list(session.new) + list(session.dirty):
        for col in inspect(obj).mapper.columns:
            n = getattr(col.type, "length", None)
            if n and isinstance(col.type, String):
                v = getattr(obj, col.key, None)
                if isinstance(v, str) and len(v) > n:
                    raise LengthError(f"{obj.__tablename__}.{col.key}: {len(v)} chars > {n}: {v[:60]!r}")


def make_engine(url: str):
    kw = {}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, pool_pre_ping=True, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return engine


def make_sessionmaker(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
