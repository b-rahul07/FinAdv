"""One-command anonymised export of research data (brief §7.6).

    RESEARCH_SALT=<long random secret> python scripts/export_research.py results/research_export

- Only users with research_opt_in = true at export time. Revoking consent removes a user from every later export.
- Users appear under a salted pseudonym (sha256(salt + user id)); the salt stays with the team, never in the export.
- Never exported: names, emails, avatar URLs, chat message text, free-text feedback comments, statement passwords
  (never stored anyway), account/folio numbers (only last 4 digits are stored; they are dropped too), demo accounts.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from finadvisor.db.base import Base, make_engine, make_sessionmaker
from finadvisor.db.models import (AdviceRun, AnalyticsEvent, ConsentEvent, Feedback, FinancialProfile, GoalSnapshot, HealthSnapshot,
                                  Message, Recommendation, RecommendationEvent, User, UserSettings)
from finadvisor.settings import get_settings

DROP_KEYS = {"email", "name", "avatar_url", "account_last4", "folio_last4", "label", "lender", "insurer", "comment", "content"}


def pseudonym(salt: str, user_id: str) -> str:
    return "u_" + hashlib.sha256((salt + user_id).encode()).hexdigest()[:16]


def scrub(obj):
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if k not in DROP_KEYS}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def row(model_obj, skip=()) -> dict:
    d = {c.key: getattr(model_obj, c.key) for c in model_obj.__table__.columns if c.key not in skip}
    return json.loads(json.dumps(d, default=str))


def export(session, out: Path, salt: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    users = [u for u, st in session.execute(select(User, UserSettings).join(UserSettings, UserSettings.user_id == User.id))
             if st.research_opt_in and not u.is_demo]
    ids = {u.id: pseudonym(salt, u.id) for u in users}
    counts = {}

    def dump(name: str, rows: list[dict]):
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        counts[name] = len(rows)

    def per_user(model, skip=()):
        out_rows = []
        for o in session.scalars(select(model).where(model.user_id.in_(ids))):
            r = scrub(row(o, skip))
            r["user"] = ids[r.pop("user_id")]
            out_rows.append(r)
        return out_rows

    dump("users", [{"user": ids[u.id], "created_at": str(u.created_at), "auth_provider": u.auth_provider} for u in users])
    dump("financial_profiles", per_user(FinancialProfile))
    dump("advice_runs", per_user(AdviceRun, skip=("chat_id",)))
    dump("recommendations", per_user(Recommendation))
    rec_ids = {r.id for r in session.scalars(select(Recommendation).where(Recommendation.user_id.in_(ids)))}
    dump("recommendation_events", [row(e) for e in session.scalars(select(RecommendationEvent)
                                                                    .where(RecommendationEvent.recommendation_id.in_(rec_ids)))])
    dump("health_snapshots", per_user(HealthSnapshot))
    dump("goal_snapshots", per_user(GoalSnapshot))
    dump("feedback", per_user(Feedback))                       # rating only; comments dropped
    dump("analytics_events", per_user(AnalyticsEvent))
    dump("consent_events", per_user(ConsentEvent))
    dump("message_meta", [{"user": ids[m.user_id], "role": m.role, "route": m.route, "status": m.status,
                           "created_at": str(m.created_at), "latency_s": m.latency_s, "advice_run_id": m.advice_run_id}
                          for m in session.scalars(select(Message).where(Message.user_id.in_(ids)))])
    meta = {"exported_at": datetime.now(timezone.utc).isoformat(), "users": len(users), "counts": counts,
            "excluded": sorted(DROP_KEYS) + ["chat text", "demo accounts", "users without opt-in"]}
    (out / "MANIFEST.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def main(argv: list[str]) -> None:
    salt = os.environ.get("RESEARCH_SALT", "")
    if len(salt) < 16:
        raise SystemExit("Set RESEARCH_SALT to a long random secret (kept by the team, never committed).")
    engine = make_engine(get_settings().database_url)
    Base.metadata.create_all(engine) if get_settings().database_url.startswith("sqlite") else None
    with make_sessionmaker(engine)() as s:
        print(json.dumps(export(s, Path(argv[0] if argv else "results/research_export"), salt), indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
