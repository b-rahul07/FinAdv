"""Reads and writes shared by several routes."""

from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from finadvisor.advisor.pipeline import TurnOutput
from finadvisor.advisor.profile import Profile
from finadvisor.db.base import utcnow
from finadvisor.db.models import (AdviceRun, AnalyticsEvent, Chat, FinancialProfile, GoalSnapshot, HealthSnapshot, Message,
                                  Recommendation, RecommendationEvent, UserSettings)


def latest_profile(s: Session, user_id: str) -> tuple[Profile | None, int | None, FinancialProfile | None]:
    row = s.scalar(select(FinancialProfile).where(FinancialProfile.user_id == user_id)
                   .order_by(desc(FinancialProfile.version)).limit(1))
    if row is None:
        return None, None, None
    return Profile(**row.data), row.version, row


def save_profile(s: Session, user_id: str, profile: Profile, sources: dict) -> int:
    current = s.scalar(select(func.max(FinancialProfile.version)).where(FinancialProfile.user_id == user_id)) or 0
    row = FinancialProfile(user_id=user_id, version=current + 1, data=profile.model_dump(mode="json"), sources=sources)
    s.add(row)
    s.flush()
    return row.version


def opted_in(s: Session, user_id: str) -> bool:
    st = s.get(UserSettings, user_id)
    return bool(st and st.research_opt_in)


def track(s: Session, user_id: str, name: str, **props) -> None:
    """Product analytics for the usability study: written only for opted-in users (brief §3.6, §7.6)."""
    if opted_in(s, user_id):
        s.add(AnalyticsEvent(user_id=user_id, name=name, props=props))


def persist_turn(s: Session, user_id: str, chat_id: str, out: TurnOutput) -> tuple[str, str | None]:
    run_id = None
    if out.advice is not None:
        rec = out.advice
        cap = rec.get("capacity") or {}
        run = AdviceRun(user_id=user_id, chat_id=chat_id, route=rec["route"], profile_version=rec.get("profile_version"),
                        capacity_level=cap.get("level"), suitability=rec.get("suitability"),
                        audit_status=(rec.get("audit") or {}).get("status"), latency_s=out.latency_s, record=rec)
        s.add(run)
        s.flush()
        run_id = run.id
        _snapshots(s, user_id, run, out)
    msg = Message(chat_id=chat_id, user_id=user_id, role="assistant", content=out.text.strip(), route=out.route,
                  cards=out.cards, sources=out.sources, status=out.status, advice_run_id=run_id,
                  model=out.advice.get("model") if out.advice else None, latency_s=out.latency_s)
    s.add(msg)
    chat = s.get(Chat, chat_id)
    if chat:
        chat.updated_at = utcnow()
    s.flush()
    return msg.id, run_id


def _snapshots(s: Session, user_id: str, run: AdviceRun, out: TurnOutput) -> None:
    for c in out.cards:
        if c["type"] == "health_check":
            s.add(HealthSnapshot(user_id=user_id, advice_run_id=run.id, profile_version=run.profile_version,
                                 score=c["score"], out_of=c["out_of"], capacity_level=c["capacity_level"], checks=c["checks"]))
        elif c["type"] == "goal":
            s.add(GoalSnapshot(user_id=user_id, advice_run_id=run.id, goal_id=c["goal_id"], name=c["name"],
                               target_future=c["target_future"], saved_so_far=c["saved_so_far"], sip_needed=c["sip_needed"],
                               monthly_assigned=c["monthly_assigned"]))
        elif c["type"] == "plan":
            for step in c["steps"]:
                _recommend(s, user_id, run.id, step)


def _recommend(s: Session, user_id: str, run_id: str, step: dict) -> None:
    key = step["action"] + (f":{step['goal_id']}" if step.get("goal_id") else "")
    rec = s.scalar(select(Recommendation).where(Recommendation.user_id == user_id, Recommendation.key == key,
                                                Recommendation.status.in_(("suggested", "pending"))))
    if rec is None:
        rec = Recommendation(user_id=user_id, advice_run_id=run_id, key=key, action=step["action"], rule=step.get("rule"),
                             title=step["text"], monthly=step.get("monthly") or None, months=step.get("months") or None)
        s.add(rec)
        s.flush()
        s.add(RecommendationEvent(recommendation_id=rec.id, status="suggested", how="suggested"))
    else:
        rec.advice_run_id, rec.title, rec.last_suggested_at = run_id, step["text"], utcnow()
        rec.monthly, rec.months = step.get("monthly") or None, step.get("months") or None


def chat_title(text: str) -> str:
    t = " ".join(text.split())
    return t if len(t) <= 60 else t[:57].rsplit(" ", 1)[0] + "…"


def message_dict(m: Message, feedback: dict | None = None) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "route": m.route, "cards": m.cards, "sources": m.sources,
            "status": m.status, "advice_run_id": m.advice_run_id, "created_at": m.created_at.isoformat(),
            "superseded": m.superseded, "latency_s": m.latency_s, "feedback": feedback}
