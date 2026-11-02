"""Account, settings, sessions, consent, export and deletion."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from finadvisor import __version__
from finadvisor.api.auth import DevAuth, SupabaseAuth
from finadvisor.api.deps import Current, current, db, rt
from finadvisor.db.base import Base, utcnow
from finadvisor.db.models import AuthSession, ConsentEvent, User, UserSettings

router = APIRouter(prefix="/api", tags=["account"])

CONSENT_TEXT_VERSION = "research-consent-v1"


def _settings(s: Session, uid: str) -> UserSettings:
    st = s.get(UserSettings, uid)
    if st is None:
        st = UserSettings(user_id=uid)
        s.add(st)
        s.flush()
    return st


def _me(u: User, st: UserSettings) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "avatar_url": u.avatar_url, "provider": u.auth_provider,
            "is_demo": u.is_demo, "created_at": u.created_at.isoformat(),
            "settings": {"theme": st.theme, "indian_grouping": st.indian_grouping, "research_opt_in": st.research_opt_in,
                         "notifications": st.notifications}}


@router.get("/me")
def me(me: Current = Depends(current), s: Session = Depends(db)):
    return _me(me.user, _settings(s, me.id))


class MePatch(BaseModel):
    name: str | None = Field(None, max_length=200)
    avatar_url: str | None = Field(None, max_length=1000)


@router.patch("/me")
def patch_me(body: MePatch, me: Current = Depends(current), s: Session = Depends(db)):
    u = s.get(User, me.id)
    if body.name is not None:
        u.name = body.name.strip() or None
    if body.avatar_url is not None:
        u.avatar_url = body.avatar_url or None
    s.commit()
    return _me(u, _settings(s, me.id))


class SettingsIn(BaseModel):
    theme: str | None = Field(None, pattern="^(system|light|dark)$")
    indian_grouping: bool | None = None
    notifications: dict | None = None


@router.put("/settings")
def put_settings(body: SettingsIn, me: Current = Depends(current), s: Session = Depends(db)):
    st = _settings(s, me.id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(st, k, v)
    s.commit()
    return _me(s.get(User, me.id), st)


class ResearchIn(BaseModel):
    opt_in: bool


@router.put("/settings/research")
def research(body: ResearchIn, me: Current = Depends(current), s: Session = Depends(db)):
    st = _settings(s, me.id)
    st.research_opt_in = body.opt_in
    s.add(ConsentEvent(user_id=me.id, kind="research", granted=body.opt_in, text_version=CONSENT_TEXT_VERSION))
    s.commit()
    return _me(s.get(User, me.id), st)


@router.get("/me/sessions")
def sessions(me: Current = Depends(current), s: Session = Depends(db)):
    rows = s.scalars(select(AuthSession).where(AuthSession.user_id == me.id, AuthSession.revoked_at.is_(None))
                     .order_by(AuthSession.last_seen_at.desc())).all()
    return [{"id": r.id, "user_agent": r.user_agent, "created_at": r.created_at.isoformat(),
             "last_seen_at": r.last_seen_at.isoformat(), "current": r.external_id == me.ident.session_id} for r in rows]


@router.post("/me/sessions/revoke-all", status_code=204)
def revoke_all(me: Current = Depends(current), s: Session = Depends(db)):
    for r in s.scalars(select(AuthSession).where(AuthSession.user_id == me.id, AuthSession.revoked_at.is_(None))):
        r.revoked_at = utcnow()
    s.commit()
    if isinstance(rt().auth, SupabaseAuth):
        rt().auth.sign_out_everywhere(me.token)


@router.delete("/me/sessions/{sid}", status_code=204)
def revoke(sid: str, me: Current = Depends(current), s: Session = Depends(db)):
    r = s.get(AuthSession, sid)
    if r is None or r.user_id != me.id:
        raise HTTPException(404, "Not found")
    r.revoked_at = utcnow()
    s.commit()


def _user_tables():
    return [t for t in Base.metadata.sorted_tables if "user_id" in t.c and t.name != "users"]


@router.get("/me/export")
def export(me: Current = Depends(current), s: Session = Depends(db)):
    """Everything FinAdvisor stores about this user, as JSON."""
    out = {"format": "finadvisor-export-v1", "exported_at": utcnow().isoformat(),
           "user": {c.key: getattr(me.user, c.key) for c in inspect(User).mapper.column_attrs}}
    for t in _user_tables():
        out[t.name] = [dict(r._mapping) for r in s.execute(select(t).where(t.c.user_id == me.id))]
    body = json.dumps(out, ensure_ascii=False, default=str, indent=1)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="finadvisor-export.json"'})


@router.delete("/me", status_code=204)
def delete_account(me: Current = Depends(current), s: Session = Depends(db)):
    """Deletes the user and every row that belongs to them (FK cascades), then the Supabase auth user."""
    for t in reversed(_user_tables()):
        s.execute(t.delete().where(t.c.user_id == me.id))
    s.delete(s.get(User, me.id))
    s.commit()
    if isinstance(rt().auth, SupabaseAuth) and not rt().auth.delete_user(me.id):
        delete_auth_user_sql(s, me.id)


def delete_auth_user_sql(s: Session, user_id: str) -> bool:
    """Without a service-role key, remove the Supabase sign-in directly: the API's Postgres role may delete from
    auth.users, which cascades to the user's sessions, refresh tokens and identities. No-op off Postgres."""
    if s.get_bind().dialect.name != "postgresql":
        return False
    s.execute(text("DELETE FROM auth.users WHERE id = CAST(:uid AS uuid)"), {"uid": user_id})
    s.commit()
    return True


STORED = [
    ("Account", "Email, name and optional photo, to sign you in and show your name."),
    ("Financial profile", "The facts you confirm on your profile card, kept as versions so each plan can show what it used."),
    ("Chats", "Your messages and FinAdvisor's answers, so you can come back to them on any device."),
    ("Advice records", "For each plan: the scores, rules, checks and model used. They power 'Why this plan'."),
    ("Recommendations", "Each suggested step and whether you marked it done or skipped."),
    ("Feedback", "Thumbs up/down and comments you give on answers."),
    ("Usage events", "Only if you join the research study: which features you use and how long tasks take."),
]


@router.get("/about")
def about():
    r = rt()
    return {
        "version": __version__,
        "notice": "FinAdvisor is not a SEBI-registered investment adviser. It provides education and planning tools only, "
                  "does not recommend individual securities and does not carry out transactions.",
        "model": r.llm.identity.to_dict(),
        "configs": r.bundle.versions,
        "stored": [{"what": a, "why": b} for a, b in STORED],
        "never_stored": ["CAS statement passwords", "Full account, folio, demat or loan numbers (only the last 4 digits)"],
    }


class DevLogin(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    name: str | None = None


@router.post("/dev/login")
def dev_login(body: DevLogin):
    auth = rt().auth
    if not isinstance(auth, DevAuth):
        raise HTTPException(404, "Not found")
    token, ident = auth.issue(body.email, body.name)
    return {"access_token": token, "user_id": ident.user_id}


@router.get("/status")
def status():
    r = rt()
    llm_ok = getattr(r.llm, "available", lambda: True)()
    return {"ok": True, "llm": {"available": llm_ok, **r.llm.identity.to_dict()}, "auth_mode": r.settings.auth_mode}
