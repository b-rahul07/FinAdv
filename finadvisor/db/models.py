"""Tables. Every per-user table carries user_id and is deleted with the user (export/delete, brief §3.6).

Privacy rules enforced here and in the API:
- no CAS passwords are ever stored; account/folio/loan numbers are stored masked only (last 4 digits);
- analytics events are written only for users who opted in to research (see api/analytics.py).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finadvisor.db.base import Base, CreatedMixin, IdMixin, utcnow

FK_USER = dict(ondelete="CASCADE")


# --------------------------------------------------------------------------- account

class User(IdMixin, CreatedMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    auth_provider: Mapped[str] = mapped_column(String(30), default="email")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), primary_key=True)
    theme: Mapped[str] = mapped_column(String(10), default="system")          # system | light | dark
    indian_grouping: Mapped[bool] = mapped_column(Boolean, default=True)
    research_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    notifications: Mapped[dict] = mapped_column(default=lambda: {"data_refresh": True, "plan_reminders": True})
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ConsentEvent(IdMixin, CreatedMixin, Base):
    __tablename__ = "consent_events"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    kind: Mapped[str] = mapped_column(String(30))            # research
    granted: Mapped[bool] = mapped_column(Boolean)
    text_version: Mapped[str] = mapped_column(String(30))


class AuthSession(IdMixin, CreatedMixin, Base):
    """Sessions we have seen (Supabase session_id claim, or dev tokens). Revoked ones are rejected."""
    __tablename__ = "auth_sessions"
    __table_args__ = (UniqueConstraint("user_id", "external_id"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    external_id: Mapped[str] = mapped_column(String(100), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(IdMixin, CreatedMixin, Base):
    __tablename__ = "notifications"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    kind: Mapped[str] = mapped_column(String(30))            # data_refresh | plan_reminder
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)


# --------------------------------------------------------------------------- advisor

class FinancialProfile(IdMixin, CreatedMixin, Base):
    """Versioned, confirmed profiles. A new version is written on every confirmation; old ones are kept so
    every advice run points at the exact profile it used (brief §7.4)."""
    __tablename__ = "financial_profiles"
    __table_args__ = (UniqueConstraint("user_id", "version"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column()
    sources: Mapped[dict] = mapped_column(default=dict)      # field -> user | llm_confirmed | holdings_confirmed


class Chat(IdMixin, CreatedMixin, Base):
    __tablename__ = "chats"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    messages: Mapped[list["Message"]] = relationship(back_populates="chat", cascade="all, delete-orphan",
                                                     order_by="Message.created_at")


class Message(IdMixin, CreatedMixin, Base):
    __tablename__ = "messages"
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    role: Mapped[str] = mapped_column(String(12))            # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    route: Mapped[str | None] = mapped_column(String(10))    # learn | plan | check | chat
    cards: Mapped[list] = mapped_column(default=list)
    sources: Mapped[list] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(String(12), default="complete")   # complete | stopped | error
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)      # replaced by a regeneration
    advice_run_id: Mapped[str | None] = mapped_column(ForeignKey("advice_runs.id", ondelete="SET NULL"))
    model: Mapped[dict | None] = mapped_column()
    latency_s: Mapped[float | None] = mapped_column(Float)
    chat: Mapped[Chat] = relationship(back_populates="messages")


class Feedback(IdMixin, CreatedMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("message_id", "user_id"),)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    rating: Mapped[int] = mapped_column(Integer)             # +1 / -1
    comment: Mapped[str] = mapped_column(Text, default="")


class AdviceRun(IdMixin, CreatedMixin, Base):
    """Audit log for every advice answer (brief §7.4). `record` holds the full structured trace."""
    __tablename__ = "advice_runs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"))
    route: Mapped[str] = mapped_column(String(10))
    profile_version: Mapped[int | None] = mapped_column(Integer)
    capacity_level: Mapped[str | None] = mapped_column(String(10))
    suitability: Mapped[str | None] = mapped_column(String(10))
    audit_status: Mapped[str | None] = mapped_column(String(12))
    latency_s: Mapped[float | None] = mapped_column(Float)
    record: Mapped[dict] = mapped_column()


class Recommendation(IdMixin, CreatedMixin, Base):
    """One suggested action. Status history lives in RecommendationEvent (brief §7.5)."""
    __tablename__ = "recommendations"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    advice_run_id: Mapped[str | None] = mapped_column(ForeignKey("advice_runs.id", ondelete="SET NULL"))
    key: Mapped[str] = mapped_column(String(120), index=True)   # stable id, e.g. build_emergency_fund
    action: Mapped[str] = mapped_column(String(40))
    rule: Mapped[str | None] = mapped_column(String(4))
    title: Mapped[str] = mapped_column(Text)
    monthly: Mapped[float | None] = mapped_column(Float)
    months: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="suggested")   # suggested | pending | done | skipped
    last_suggested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecommendationEvent(IdMixin, CreatedMixin, Base):
    __tablename__ = "recommendation_events"
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12))
    how: Mapped[str] = mapped_column(String(20))             # suggested | user_tap | holdings_change | cas
    note: Mapped[str] = mapped_column(Text, default="")


class HealthSnapshot(IdMixin, CreatedMixin, Base):
    __tablename__ = "health_snapshots"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    advice_run_id: Mapped[str | None] = mapped_column(ForeignKey("advice_runs.id", ondelete="SET NULL"))
    profile_version: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)
    out_of: Mapped[int] = mapped_column(Integer)
    capacity_level: Mapped[str] = mapped_column(String(10))
    checks: Mapped[list] = mapped_column()


class GoalSnapshot(IdMixin, CreatedMixin, Base):
    __tablename__ = "goal_snapshots"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    advice_run_id: Mapped[str | None] = mapped_column(ForeignKey("advice_runs.id", ondelete="SET NULL"))
    goal_id: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    target_future: Mapped[float | None] = mapped_column(Float)
    saved_so_far: Mapped[float] = mapped_column(Float, default=0)
    sip_needed: Mapped[float | None] = mapped_column(Float)
    monthly_assigned: Mapped[float | None] = mapped_column(Float)


class AnalyticsEvent(IdMixin, CreatedMixin, Base):
    """Own-database product analytics for the usability study. Written only for opted-in users."""
    __tablename__ = "analytics_events"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    props: Mapped[dict] = mapped_column(default=dict)


Index("ix_messages_chat_created", Message.chat_id, Message.created_at)



# --------------------------------------------------------------------------- market data (shared, not per user)

class Instrument(IdMixin, CreatedMixin, Base):
    """Stocks/ETFs/SGBs (by ISIN) and mutual fund schemes (by AMFI code). Master lists refreshed from official files."""
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("kind", "key"),)
    kind: Mapped[str] = mapped_column(String(10))            # stock | etf | sgb | mf | index
    key: Mapped[str] = mapped_column(String(40))             # ISIN for listed, AMFI code for MF, name for index
    symbol: Mapped[str | None] = mapped_column(String(40), index=True)
    exchange: Mapped[str | None] = mapped_column(String(4))  # NSE | BSE
    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    sector: Mapped[str | None] = mapped_column(String(100))
    amc: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(200))
    plan: Mapped[str | None] = mapped_column(String(20))     # Direct | Regular
    option: Mapped[str | None] = mapped_column(String(120))  # Growth | IDCW | long AMFI labels (up to 83 chars seen)
    expense_ratio: Mapped[float | None] = mapped_column(Float)
    tracked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)   # someone holds or watches it


class PriceDaily(Base):
    """One close (or NAV) per instrument per trading day, exactly as published; adjustments live in CorporateAction."""
    __tablename__ = "prices_daily"
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    close: Mapped[float] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    prev_close: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(200))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CorporateAction(IdMixin, CreatedMixin, Base):
    """Price-adjustment events. `factor` multiplies prices before ex_date (and divides quantities)."""
    __tablename__ = "corporate_actions"
    __table_args__ = (UniqueConstraint("instrument_id", "ex_date"),)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    ex_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))            # split_or_bonus | other_adjustment
    factor: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(80))          # e.g. "derived: NSE bhavcopy previous close"
    note: Mapped[str] = mapped_column(Text, default="")


class MarketDay(Base):
    """Which dates each source published (or did not). Builds the trading calendar from the data itself."""
    __tablename__ = "market_days"
    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    published: Mapped[bool] = mapped_column(Boolean)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataJobRun(IdMixin, CreatedMixin, Base):
    __tablename__ = "data_job_runs"
    job: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12))          # ok | partial | failed
    detail: Mapped[dict] = mapped_column(default=dict)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- holdings (per user)

class Transaction(IdMixin, CreatedMixin, Base):
    __tablename__ = "transactions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))              # buy | sell
    trade_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[float] = mapped_column(Float)            # shares or units, as traded (unadjusted)
    price: Mapped[float] = mapped_column(Float)               # per share/unit, as traded
    charges: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(12), default="manual")   # manual | cas
    cas_upload_id: Mapped[str | None] = mapped_column(ForeignKey("cas_uploads.id", ondelete="CASCADE"), index=True)
    folio_last4: Mapped[str | None] = mapped_column(String(4))          # never the full folio/account number
    note: Mapped[str] = mapped_column(Text, default="")


class WatchItem(IdMixin, CreatedMixin, Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "instrument_id"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), index=True)
    added_on: Mapped[date] = mapped_column(Date)


class Sip(IdMixin, CreatedMixin, Base):
    __tablename__ = "sips"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    day_of_month: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[str] = mapped_column(String(10), default="monthly")
    start_date: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class InstrumentNote(IdMixin, CreatedMixin, Base):
    __tablename__ = "instrument_notes"
    __table_args__ = (UniqueConstraint("user_id", "instrument_id"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), index=True)
    text: Mapped[str] = mapped_column(Text, default="")


class CasUpload(IdMixin, CreatedMixin, Base):
    """One uploaded statement. The PDF and its password are never stored; only what the user imports."""
    __tablename__ = "cas_uploads"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    file_type: Mapped[str] = mapped_column(String(12))        # CAMS | KFINTECH | NSDL | CDSL | UNKNOWN
    cas_type: Mapped[str] = mapped_column(String(12))         # DETAILED | SUMMARY | DEMAT
    period_from: Mapped[str | None] = mapped_column(String(20))
    period_to: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12), default="previewed")   # previewed | imported | failed
    preview: Mapped[dict | None] = mapped_column()            # PII-free; cleared after import
    counts: Mapped[dict] = mapped_column(default=dict)
    warnings: Mapped[list] = mapped_column(default=list)


# --------------------------------------------------------------------------- other assets, cover and loans (per user)

class OtherAsset(IdMixin, CreatedMixin, Base):
    """Deposits, retirement and small savings, cash, physical/digital gold and silver, property, vehicles, other.
    `data` holds kind-specific fields (see finadvisor/portfolio/others.py)."""
    __tablename__ = "other_assets"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(default=dict)
    account_last4: Mapped[str | None] = mapped_column(String(4))


class InsurancePolicy(IdMixin, CreatedMixin, Base):
    """Cover for the advisor's checks. Not counted in net worth."""
    __tablename__ = "insurance_policies"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    kind: Mapped[str] = mapped_column(String(10))            # term | health
    insurer: Mapped[str] = mapped_column(String(200), default="")
    sum_assured: Mapped[float] = mapped_column(Float)
    premium_yearly: Mapped[float | None] = mapped_column(Float)
    renewal_date: Mapped[date | None] = mapped_column(Date)
    employer_provided: Mapped[bool] = mapped_column(Boolean, default=False)


class Liability(IdMixin, CreatedMixin, Base):
    __tablename__ = "liabilities"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", **FK_USER), index=True)
    kind: Mapped[str] = mapped_column(String(20))            # home | car | personal | education | bnpl | credit_card | gold | two_wheeler | other
    lender: Mapped[str] = mapped_column(String(200), default="")
    outstanding: Mapped[float] = mapped_column(Float)
    rate_pa: Mapped[float | None] = mapped_column(Float)
    emi_monthly: Mapped[float] = mapped_column(Float, default=0)
    end_date: Mapped[date | None] = mapped_column(Date)
    as_of: Mapped[date] = mapped_column(Date)
    account_last4: Mapped[str | None] = mapped_column(String(4))
