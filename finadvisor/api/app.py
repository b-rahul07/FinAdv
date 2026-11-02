"""Run: uvicorn finadvisor.api.app:app --port 8000"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finadvisor import __version__
from finadvisor.api.routes import account, cas, chats, holdings, library, profile
from finadvisor.settings import get_settings


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="FinAdvisor API", version=__version__)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
                       allow_credentials=False, allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    for r in (account.router, cas.router, chats.router, holdings.router, library.router, profile.router):
        app.include_router(r)
    return app


app = create_app()
