"""The home page: where the money goes each month, the current plan as a timeline, goals, and the health history."""

from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from finadvisor.advisor import overview
from finadvisor.advisor.capacity import assess
from finadvisor.advisor.health import health_card
from finadvisor.advisor.profile import Profile
from finadvisor.api import store
from finadvisor.api.deps import Current, current, db, rt
from finadvisor.db.models import AdviceRun, HealthSnapshot, Recommendation
from finadvisor.market import jobs
from finadvisor.portfolio import sips as sip_finder

router = APIRouter(prefix="/api", tags=["home"])
IST = ZoneInfo("Asia/Kolkata")


def _ist(dt):
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(IST)


@router.get("/home")
def home(me: Current = Depends(current), s: Session = Depends(db)):
    out = build(s, me.id, rt().bundle)
    s.commit()                      # SIPs found for the first time are kept
    return out


def _facts_moved(run: AdviceRun, profile, version) -> bool:
    """Whether the facts a plan is built from differ from the facts it was made with. Tax facts are not among them
    (no engine reads them), so answering a tax question does not make a plan out of date."""
    made_with = run.record.get("profile")
    if profile is None or not made_with:
        return bool(version and run.profile_version and version > run.profile_version)
    try:
        return Profile(**made_with).model_dump(exclude={"tax"}) != profile.model_dump(exclude={"tax"})
    except ValueError:
        return True


def latest_plan_run(s: Session, user_id: str) -> AdviceRun | None:
    return s.scalar(select(AdviceRun).where(AdviceRun.user_id == user_id, AdviceRun.route == "plan")
                    .order_by(desc(AdviceRun.created_at)).limit(1))


def build(s: Session, user_id: str, b) -> dict:
    """The home-page overview. Also what the chat's conversation stage answers "am I on track?" from."""
    profile, version, row = store.latest_profile(s, user_id)
    run = s.scalar(select(AdviceRun).where(AdviceRun.user_id == user_id, AdviceRun.route == "plan")
                   .order_by(desc(AdviceRun.created_at)).limit(1))
    plan = None
    if run is not None and run.record.get("plan"):
        recs: dict[str, dict] = {}
        for r in s.scalars(select(Recommendation).where(Recommendation.user_id == user_id)
                           .order_by(Recommendation.last_suggested_at)):
            recs[r.key] = {"id": r.id, "status": r.status}          # the latest one per key wins
        made = _ist(run.created_at)
        plan = {
            **overview.plan_overview(run.record["plan"], made.date(), recs),
            "advice_run_id": run.id, "chat_id": run.chat_id, "made_at": made.isoformat(),
            "profile_version": run.profile_version, "audit_status": run.audit_status,
            "stale": _facts_moved(run, profile, version),
        }
    snaps = [{"at": _ist(h.created_at).isoformat(), "score": h.score, "out_of": h.out_of, "profile_version": h.profile_version}
             for h in s.scalars(select(HealthSnapshot).where(HealthSnapshot.user_id == user_id).order_by(HealthSnapshot.created_at))]
    health = health_card(profile, assess(profile, b.rules), b.rules) if profile else None
    now = ({"at": _ist(row.created_at).isoformat(), "score": health["score"], "out_of": health["out_of"],
            "profile_version": version} if health else None)
    found = sip_finder.sync(s, user_id, jobs.today_ist())
    cash = overview.cash_flow(profile) if profile else None
    if cash is not None:
        # SIPs come out of the left-over, which stays the planner's surplus; this says how much of it is already at work
        cash["sips"] = found["monthly_total"]
        cash["sips_count"] = sum(x["status"] in ("active", "missed") for x in found["items"])
    return {
        "profile_version": version,
        "cash_flow": cash,
        "health": health,
        "health_history": overview.health_history(snaps, now),
        "plan": plan,
        "goals": overview.goal_progress(profile, run.record["plan"].get("buckets") if plan and not plan["stale"] else None)
                 if profile else [],
    }
