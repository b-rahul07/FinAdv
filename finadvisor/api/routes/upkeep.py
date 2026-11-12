"""What keeps the app current without typing: SIPs found from transactions, the four nudges, and the capital-gains
statement for a financial year."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from finadvisor.advisor import nudges as nudge_rules
from finadvisor.api import store
from finadvisor.api.deps import Current, current, db, rt
from finadvisor.api.routes import home as home_route
from finadvisor.db.models import Notification, Sip, UserSettings
from finadvisor.market import jobs
from finadvisor.portfolio import gains
from finadvisor.portfolio import service as P
from finadvisor.portfolio import sips as sip_finder

router = APIRouter(prefix="/api", tags=["upkeep"])
DISMISSED = "nudge_dismissed"      # Notification.kind for a dismissed nudge; its title holds the nudge id


@router.get("/sips")
def list_sips(me: Current = Depends(current), s: Session = Depends(db)):
    out = sip_finder.sync(s, me.id, jobs.today_ist())
    s.commit()
    return out


class SipPatch(BaseModel):
    active: bool


@router.patch("/sips/{sip_id}")
def patch_sip(sip_id: str, body: SipPatch, me: Current = Depends(current), s: Session = Depends(db)):
    """The person's own word on a detected SIP: stopped, or running after all."""
    row = s.get(Sip, sip_id)
    if row is None or row.user_id != me.id:
        raise HTTPException(404, "Not found")
    row.active = body.active
    store.track(s, me.id, "sip_marked", active=body.active)
    s.commit()
    return {"ok": True}


def _dismissed(s: Session, user_id: str) -> set[str]:
    return set(s.scalars(select(Notification.title).where(Notification.user_id == user_id, Notification.kind == DISMISSED)))


@router.get("/nudges")
def list_nudges(me: Current = Depends(current), s: Session = Depends(db)):
    today = jobs.today_ist()
    b = rt().bundle
    st = s.get(UserSettings, me.id)
    _, _, row = store.latest_profile(s, me.id)
    overview = home_route.build(s, me.id, b)
    out = nudge_rules.build(
        today=today, prefs=(st.notifications if st else {}) or {},
        holdings=P.holdings(s, me.id, b.tax, today)["items"], plan=overview["plan"],
        profile_confirmed_on=home_route._ist(row.created_at).date() if row else None,
        sips=sip_finder.sync(s, me.id, today)["items"], dismissed=_dismissed(s, me.id))
    s.commit()
    return out


class Dismiss(BaseModel):
    id: str = Field(..., min_length=3, max_length=200)


@router.post("/nudges/dismiss")
def dismiss(body: Dismiss, me: Current = Depends(current), s: Session = Depends(db)):
    if body.id.split(":", 1)[0] not in nudge_rules.SWITCH:
        raise HTTPException(422, "Unknown nudge")
    if body.id not in _dismissed(s, me.id):
        s.add(Notification(user_id=me.id, kind=DISMISSED, title=body.id, read=True))
        store.track(s, me.id, "nudge_dismissed", kind=body.id.split(":", 1)[0])
        s.commit()
    return {"ok": True}


def _statement(s: Session, user_id: str, fy: str | None) -> dict:
    try:
        return gains.statement(s, user_id, fy or gains.fy_of(jobs.today_ist()), rt().bundle.tax)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/tax/capital-gains")
def capital_gains(fy: str | None = None, me: Current = Depends(current), s: Session = Depends(db)):
    return _statement(s, me.id, fy)


@router.get("/tax/capital-gains.csv")
def capital_gains_csv(fy: str | None = None, me: Current = Depends(current), s: Session = Depends(db)):
    st = _statement(s, me.id, fy)
    return Response(gains.to_csv(st), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="capital-gains-{st["financial_year"]}.csv"'})
