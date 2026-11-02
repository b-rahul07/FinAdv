"""Financial profile card, risk questionnaire, health check, what-if, advice records and recommendations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from finadvisor.advisor import cards
from finadvisor.advisor.capacity import assess
from finadvisor.advisor.health import health_card
from finadvisor.advisor.profile import Profile, missing_fields
from finadvisor.advisor.willingness import assess as assess_will
from finadvisor.api import store
from finadvisor.api.deps import Current, current, db, rt
from finadvisor.db.models import AdviceRun, HealthSnapshot, Recommendation, RecommendationEvent

router = APIRouter(prefix="/api", tags=["profile"])


class ProfileIn(BaseModel):
    data: dict
    sources: dict = {}


def _profile_view(profile: Profile | None, version: int | None, sources: dict | None) -> dict:
    b = rt().bundle
    if profile is None:
        return {"version": None, "data": Profile().model_dump(mode="json"), "sources": {}, "missing": missing_fields(Profile()),
                "health": None, "willingness": None}
    cap = assess(profile, b.rules)
    return {"version": version, "data": profile.model_dump(mode="json"), "sources": sources or {},
            "missing": missing_fields(profile), "health": health_card(profile, cap, b.rules),
            "willingness": assess_will(profile, b.willingness).to_dict(), "capacity": cap.to_dict()}


@router.get("/profile")
def get_profile(me: Current = Depends(current), s: Session = Depends(db)):
    p, v, row = store.latest_profile(s, me.id)
    return _profile_view(p, v, row.sources if row else None)


@router.put("/profile")
def confirm_profile(body: ProfileIn, me: Current = Depends(current), s: Session = Depends(db)):
    """Confirming the card writes a new profile version. Only confirmed versions reach the engines."""
    try:
        p = Profile(**body.data)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False))
    old, _, _ = store.latest_profile(s, me.id)
    v = store.save_profile(s, me.id, p, body.sources)
    store.track(s, me.id, "profile_confirmed", version=v, first=old is None)
    s.commit()
    return _profile_view(p, v, body.sources)


@router.get("/questionnaire")
def questionnaire():
    w = rt().bundle.willingness
    return {
        "version": w["version"],
        "attribution": "Adapted from the Grable & Lytton (1999) risk-tolerance scale as printed in Kuzniak et al. (2015), "
                       "Financial Services Review 24(2), Appendix A. CC BY-NC 4.0. Amounts converted to rupees.",
        "items": [{"n": i["n"], "text": i["text"], "options": [{"key": o["key"], "text": o["text"]} for o in i["options"]]}
                  for i in w["items"]],
    }


@router.post("/what-if")
def what_if(changes: dict, me: Current = Depends(current), s: Session = Depends(db)):
    p, _, _ = store.latest_profile(s, me.id)
    if p is None:
        raise HTTPException(400, "Confirm your profile first")
    store.track(s, me.id, "what_if", fields=sorted(changes))
    s.commit()
    return cards.what_if(p, changes, rt().bundle)


@router.get("/advice/{run_id}")
def advice(run_id: str, me: Current = Depends(current), s: Session = Depends(db)):
    r = s.get(AdviceRun, run_id)
    if r is None or r.user_id != me.id:
        raise HTTPException(404, "Not found")
    return {"id": r.id, "created_at": r.created_at.isoformat(), "route": r.route, "audit_status": r.audit_status,
            "latency_s": r.latency_s, "why": r.record.get("why"), "model": r.record.get("model"),
            "versions": r.record.get("versions"), "flags": r.record.get("flags"), "audit": r.record.get("audit"),
            "profile_version": r.profile_version}


@router.get("/recommendations")
def recommendations(me: Current = Depends(current), s: Session = Depends(db)):
    rows = s.scalars(select(Recommendation).where(Recommendation.user_id == me.id)
                     .order_by(desc(Recommendation.last_suggested_at)).limit(50)).all()
    return [{"id": r.id, "key": r.key, "action": r.action, "rule": r.rule, "title": r.title, "monthly": r.monthly,
             "months": r.months, "status": r.status, "advice_run_id": r.advice_run_id,
             "suggested_at": r.created_at.isoformat(), "updated_at": r.last_suggested_at.isoformat()} for r in rows]


class RecStatus(BaseModel):
    status: str


@router.patch("/recommendations/{rec_id}")
def set_rec_status(rec_id: str, body: RecStatus, me: Current = Depends(current), s: Session = Depends(db)):
    if body.status not in ("suggested", "pending", "done", "skipped"):
        raise HTTPException(422, "Unknown status")
    r = s.get(Recommendation, rec_id)
    if r is None or r.user_id != me.id:
        raise HTTPException(404, "Not found")
    r.status = body.status
    s.add(RecommendationEvent(recommendation_id=r.id, status=body.status, how="user_tap"))
    store.track(s, me.id, "recommendation_status", status=body.status, action=r.action)
    s.commit()
    return {"ok": True}


@router.get("/health-check")
def health(me: Current = Depends(current), s: Session = Depends(db)):
    p, v, _ = store.latest_profile(s, me.id)
    last = s.scalar(select(HealthSnapshot).where(HealthSnapshot.user_id == me.id).order_by(desc(HealthSnapshot.created_at)).limit(1))
    live = health_card(p, assess(p, rt().bundle.rules), rt().bundle.rules) if p else None
    return {"current": live, "profile_version": v,
            "last_snapshot": {"score": last.score, "out_of": last.out_of, "at": last.created_at.isoformat()} if last else None}
