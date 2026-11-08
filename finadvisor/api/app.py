"""Run: uvicorn finadvisor.api.app:app --port 8000"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from finadvisor import __version__
from finadvisor.api.routes import account, cas, chats, holdings, library, profile
from finadvisor.api.runtime import get_runtime
from finadvisor.settings import ROOT, get_settings

WEB_DIST = ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the search models and the language model in the background, so the first question doesn't wait for them.
    threading.Thread(target=lambda: get_runtime().warm(), daemon=True, name="warm-up").start()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="FinAdvisor API", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
                       allow_credentials=False, allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    for r in (account.router, cas.router, chats.router, holdings.router, library.router, profile.router):
        app.include_router(r)
    if s.serve_web:
        serve_web(app)
    return app


def serve_web(app: FastAPI) -> None:
    """The built website on the same address as the API (the public link: one tunnel, no CORS). Registered after the
    API routes, so /api/* never reaches it; any other unknown path gets index.html for client-side routing."""
    index = WEB_DIST / "index.html"
    if not index.is_file():
        raise RuntimeError("SERVE_WEB is on but web/dist is missing; build it with: cd web && npm run build")
    root = WEB_DIST.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (root / path).resolve()
        if path and f.is_file() and root in f.parents:
            return FileResponse(f)
        return FileResponse(index)


app = create_app()
