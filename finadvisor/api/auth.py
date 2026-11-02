"""Token verification. Supabase tokens in production; locally issued tokens in dev mode only."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

import httpx
import jwt

from finadvisor.settings import Settings


@dataclass
class Identity:
    user_id: str
    email: str
    name: str | None
    avatar_url: str | None
    provider: str
    session_id: str


class AuthError(Exception):
    pass


class DevAuth:
    """Local HS256 tokens for development and tests. Never enabled when APP_ENV=prod (Settings.check)."""

    def __init__(self, secret: str):
        self.secret = secret

    def issue(self, email: str, name: str | None = None, ttl_s: int = 7 * 86400) -> tuple[str, Identity]:
        email = email.strip().lower()
        uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"finadvisor-dev:{email}"))
        sid = str(uuid.uuid4())
        now = int(time.time())
        token = jwt.encode({"sub": uid, "email": email, "name": name, "session_id": sid, "iat": now,
                            "exp": now + ttl_s, "aud": "finadvisor-dev"}, self.secret, algorithm="HS256")
        return token, Identity(uid, email, name, None, "dev", sid)

    def verify(self, token: str) -> Identity:
        try:
            c = jwt.decode(token, self.secret, algorithms=["HS256"], audience="finadvisor-dev")
        except jwt.PyJWTError as e:
            raise AuthError(str(e)) from e
        return Identity(c["sub"], c["email"], c.get("name"), None, "dev", c["session_id"])


class SupabaseAuth:
    """Verifies Supabase access tokens: JWKS for asymmetric keys, the JWT secret for legacy HS256 projects,
    and as a last resort asks Supabase Auth directly (cached briefly)."""

    def __init__(self, s: Settings):
        self.url = s.supabase_url.rstrip("/")
        self.secret = s.supabase_jwt_secret
        self.service_key = s.supabase_service_key
        self.api_key = s.supabase_service_key or s.supabase_anon_key
        self._jwks = jwt.PyJWKClient(f"{self.url}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=3600)
        self._cache: dict[str, tuple[float, Identity]] = {}

    def verify(self, token: str) -> Identity:
        try:
            alg = jwt.get_unverified_header(token).get("alg")
        except jwt.PyJWTError as e:
            raise AuthError("malformed token") from e
        try:
            if alg == "HS256" and self.secret:
                claims = jwt.decode(token, self.secret, algorithms=["HS256"], audience="authenticated")
            elif alg in ("ES256", "RS256", "EdDSA"):
                key = self._jwks.get_signing_key_from_jwt(token).key
                claims = jwt.decode(token, key, algorithms=[alg], audience="authenticated")
            else:
                return self._remote(token)
        except jwt.PyJWTError as e:
            raise AuthError(str(e)) from e
        return self._identity(claims)

    def _remote(self, token: str) -> Identity:
        h = hashlib.sha256(token.encode()).hexdigest()
        hit = self._cache.get(h)
        if hit and hit[0] > time.time():
            return hit[1]
        r = httpx.get(f"{self.url}/auth/v1/user", headers={"Authorization": f"Bearer {token}", "apikey": self.api_key},
                      timeout=10)
        if r.status_code != 200:
            raise AuthError("token rejected by Supabase")
        u = r.json()
        claims = jwt.decode(token, options={"verify_signature": False})
        ident = self._identity({**claims, "sub": u["id"], "email": u.get("email"), "user_metadata": u.get("user_metadata", {}),
                                "app_metadata": u.get("app_metadata", {})})
        self._cache[h] = (time.time() + 60, ident)
        return ident

    @staticmethod
    def _identity(c: dict) -> Identity:
        meta = c.get("user_metadata") or {}
        return Identity(c["sub"], c.get("email") or "", meta.get("full_name") or meta.get("name"),
                        meta.get("avatar_url"), (c.get("app_metadata") or {}).get("provider", "email"),
                        c.get("session_id") or hashlib.sha256(c["sub"].encode()).hexdigest()[:32])

    def sign_out_everywhere(self, token: str) -> None:
        httpx.post(f"{self.url}/auth/v1/logout", params={"scope": "global"},
                   headers={"Authorization": f"Bearer {token}", "apikey": self.api_key}, timeout=10)

    def delete_user(self, user_id: str) -> bool:
        """Remove the sign-in itself. Needs the service-role key; returns False when it is not configured."""
        if not self.service_key:
            return False
        httpx.delete(f"{self.url}/auth/v1/admin/users/{user_id}",
                     headers={"Authorization": f"Bearer {self.service_key}", "apikey": self.service_key}, timeout=10)
        return True
