"""Process-wide singletons: database, auth verifier, advisor, retriever, live generations."""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from pathlib import Path

from finadvisor.advisor.pipeline import Advisor
from finadvisor.api.auth import DevAuth, SupabaseAuth
from finadvisor.configs import default_bundle
from finadvisor.db.base import Base, make_engine, make_sessionmaker
from finadvisor.llm import get_llm
from finadvisor.retrieval import DOCS_DIR
from finadvisor.settings import get_settings

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings=None, llm=None, retriever=None, news=None):
        self.settings = settings or get_settings()
        self.engine = make_engine(self.settings.database_url)
        if self.settings.database_url.startswith("sqlite"):
            Path(self.settings.database_url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(self.engine)   # Postgres uses Alembic migrations instead
        self.Session = make_sessionmaker(self.engine)
        self.auth = SupabaseAuth(self.settings) if self.settings.auth_mode == "supabase" else DevAuth(self.settings.dev_auth_secret)
        self.bundle = default_bundle()
        self.llm = llm or get_llm(self.settings.model_name, self.bundle.models, base_url=self.settings.ollama_base_url)
        if news is None and self.settings.news == "rss":
            from finadvisor.market.news import NewsDesk
            news = NewsDesk().get
        self.advisor = Advisor(self.bundle, self.llm, retriever if retriever is not None else make_retriever(self.settings.retrieval),
                               real_users=True, news=news)
        self.live: dict[str, threading.Event] = {}     # chat_id -> cancel flag of the running generation
        self.lock = threading.Lock()


def make_retriever(kind: str):
    """Chroma + cross-encoder over the curated documents, with a dependency-free keyword fallback."""
    if kind == "chroma":
        state: dict = {}

        def chroma(query: str, k: int) -> list[dict]:
            try:
                if "retrieve" not in state:
                    from finadvisor.retrieval.chroma import retrieve
                    state["retrieve"] = retrieve
                hits = state["retrieve"](query, k)
                return [{"id": h.chunk_id, "title": _title(h.document_name), "source": h.document_name, "text": h.content}
                        for h in hits]
            except Exception as e:  # noqa: BLE001
                log.warning("chroma retrieval unavailable (%s); using keyword retrieval", e)
                return keyword(query, k)
        return chroma
    return keyword


ACRONYMS = {"elss", "ppf", "nps", "sip", "sebi", "sgb", "bnpl", "fd", "fds", "scss", "ssy", "emi", "rbi", "80c", "80d", "80e"}


def _title(name: str) -> str:
    """'01_section_80c_tax_deductions.txt' -> 'Section 80C Tax Deductions'."""
    parts = Path(name).stem.split("_")
    if parts and parts[0].isdigit():
        parts = parts[1:]
    return " ".join(p.upper() if p in ACRONYMS else p.capitalize() for p in parts)


@lru_cache(maxsize=1)
def _keyword_index():
    docs = []
    for f in sorted(DOCS_DIR.glob("*.txt")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 80]
        for i, p in enumerate(paras):
            docs.append({"id": f"{f.stem}#{i}", "title": _title(f.name), "source": f.name, "text": p,
                         "terms": set(_terms(p + " " + f.stem)), "title_terms": set(_terms(f.stem))})
    return docs


STOP = {"what", "which", "how", "why", "when", "where", "who", "the", "and", "for", "are", "can", "should", "does",
         "this", "that", "with", "about", "into", "from", "your", "you", "have", "has", "will", "would", "could", "much",
         "many", "want", "need", "tell", "explain", "work", "works", "best", "good", "get", "any", "all", "its", "not"}


def _terms(s: str) -> list[str]:
    import re
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2 and w not in STOP]


@lru_cache(maxsize=1)
def _idf() -> dict[str, float]:
    import math
    docs = _keyword_index()
    df: dict[str, int] = {}
    for d in docs:
        for t in d["terms"]:
            df[t] = df.get(t, 0) + 1
    return {t: math.log(1 + len(docs) / n) for t, n in df.items()}


def keyword(query: str, k: int) -> list[dict]:
    """Passages sharing at least two content words with the query (one for one-word questions like "What is ELSS?"),
    ranked by the rarity of the shared words."""
    q = set(_terms(query))
    need = min(2, len(q))
    idf = _idf()
    # a shared word in the document's title counts double: "What is ELSS?" should find the ELSS guide first
    scored = sorted(((len(q & d["terms"]), sum(idf.get(t, 0) * (2 if t in d["title_terms"] else 1)
                                                for t in q & d["terms"]), d) for d in _keyword_index()),
                    key=lambda x: -x[1])
    return [{kk: v for kk, v in d.items() if kk not in ("terms", "title_terms")}
            for n, s, d in scored if need and n >= need][:k]


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime


def set_runtime(rt: Runtime) -> None:
    global _runtime
    _runtime = rt
