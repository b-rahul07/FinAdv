"""FinAdvisor's document library (the curated guides retrieval searches), readable from the evidence card."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from finadvisor.api.deps import Current, current
from finadvisor.api.runtime import _title
from finadvisor.retrieval import DOCS_DIR as DOCS
from finadvisor.retrieval.chunks import last_checked

router = APIRouter(prefix="/api/library", tags=["library"])


def _updated(f) -> str:
    """When the guide's facts were last checked (its "Last checked:" line, else the file time), shown so readers know
    how old its rates and limits may be."""
    return last_checked(f.name) or datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).date().isoformat()


@router.get("")
def list_documents(me: Current = Depends(current)):
    return {"documents": [{"source": f.name, "title": _title(f.name), "updated": _updated(f)}
                          for f in sorted(DOCS.glob("*.txt"))]}


@router.get("/{source}")
def read_document(source: str, me: Current = Depends(current)):
    # only names that exist in the library directory; no paths
    names = {f.name: f for f in DOCS.glob("*.txt")}
    f = names.get(source)
    if f is None:
        raise HTTPException(404, "Not in FinAdvisor's library")
    return {"source": f.name, "title": _title(f.name), "updated": _updated(f),
            "text": f.read_text(encoding="utf-8", errors="ignore")}
