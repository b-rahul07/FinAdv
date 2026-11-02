from __future__ import annotations

from typing import Iterator

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from finadvisor.api.auth import AuthError, Identity
from finadvisor.api.runtime import Runtime, get_runtime
from finadvisor.db.base import utcnow
from finadvisor.db.models import AuthSession, User, UserSettings


def rt() -> Runtime:
    return get_runtime()


def db(runtime: Runtime = Depends(rt)) -> Iterator[Session]:
    s = runtime.Session()
    try:
        yield s
    finally:
        s.close()


def _aware(dt):
    from datetime import timezone
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Current:
    def __init__(self, user: User, ident: Identity, token: str):
        self.user = user
        self.ident = ident
        self.token = token

    @property
    def id(self) -> str:
        return self.user.id


def current(request: Request, authorization: str | None = Header(None), runtime: Runtime = Depends(rt),
            s: Session = Depends(db)) -> Current:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required")
    token = authorization.split(" ", 1)[1]
    try:
        ident = runtime.auth.verify(token)
    except AuthError:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    user = s.get(User, ident.user_id)
    if user is None:
        # A new user's first page load sends several requests at once; only one insert wins.
        try:
            s.add(User(id=ident.user_id, email=ident.email, name=ident.name, avatar_url=ident.avatar_url,
                       auth_provider=ident.provider))
            s.add(UserSettings(user_id=ident.user_id))
            s.commit()
        except IntegrityError:
            s.rollback()
        user = s.get(User, ident.user_id)
        if user is None:
            raise HTTPException(409, "This email is already linked to another account.")
    sess = s.scalar(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.external_id == ident.session_id))
    if sess is not None and sess.revoked_at is not None:
        raise HTTPException(401, "This session was signed out. Please sign in again.")
    try:
        if sess is None:
            s.add(AuthSession(user_id=user.id, external_id=ident.session_id,
                              user_agent=(request.headers.get("user-agent") or "")[:300]))
        elif (utcnow() - _aware(sess.last_seen_at)).total_seconds() > 300:   # avoid a write on every request
            sess.last_seen_at = utcnow()
        s.commit()
    except IntegrityError:
        s.rollback()
    return Current(user, ident, token)
