"""How well document search finds the right guide for everyday questions.

    python scripts/eval_retrieval.py                       # current index and keyword search
    python scripts/eval_retrieval.py --models all-MiniLM-L6-v2 bge-small-en-v1.5   # compare embedding models

Questions: experiments/data/retrieval_questions.jsonl (each lists the guides that answer it). Reports, per search
method, hit@1 and hit@3 (the right guide among the first 1 or 3 distinct guides returned) and MRR, overall and on the
questions whose guide exists in the library. Model comparisons build a throwaway index per model under data/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from finadvisor.retrieval import DOCS_DIR  # noqa: E402

QUESTIONS = ROOT / "experiments" / "data" / "retrieval_questions.jsonl"


def ranked_docs(hits: list[str]) -> list[str]:
    return list(dict.fromkeys(hits))


def score(questions: list[dict], search) -> dict:
    present = {f.name for f in DOCS_DIR.glob("*.txt")}
    rows = []
    for q in questions:
        docs = ranked_docs(search(q["q"]))[:3]
        rank = next((i + 1 for i, d in enumerate(docs) if d in q["docs"]), None)
        rows.append({"covered": any(d in present for d in q["docs"]), "rank": rank, "q": q["q"], "got": docs})

    def stats(rs):
        n = len(rs) or 1
        return {"n": len(rs), "hit@1": sum(r["rank"] == 1 for r in rs) / n,
                "hit@3": sum(r["rank"] is not None for r in rs) / n,
                "mrr": sum(1 / r["rank"] for r in rs if r["rank"]) / n}
    return {"all": stats(rows), "covered": stats([r for r in rows if r["covered"]]),
            "misses": [(r["q"], r["got"]) for r in rows if r["covered"] and r["rank"] is None]}


def chroma_search(k: int = 3):
    from finadvisor.retrieval.chroma import retrieve
    return lambda q: [c.document_name for c in retrieve(q, k * 3)]


def keyword_search(k: int = 3):
    from finadvisor.api.runtime import keyword
    return lambda q: [d["source"] for d in keyword(q, k * 6)]


def with_model(model: str):
    """Build a temporary index with another embedding model and search it."""
    from finadvisor.retrieval import chroma
    chroma.EMBEDDING_MODEL = model if "/" in model else ("BAAI/" if model.startswith("bge") else
                                                         "sentence-transformers/") + model
    chroma.PERSIST_DIR = ROOT / "data" / f"chroma_eval_{model.replace('/', '_')}"
    chroma._collection = None
    chroma.build_index()
    return chroma_search()


def show(name: str, r: dict) -> None:
    a, c = r["all"], r["covered"]
    print(f"{name:34} all {a['n']:3}: hit@1 {a['hit@1']:.0%} hit@3 {a['hit@3']:.0%} MRR {a['mrr']:.2f} | "
          f"covered {c['n']:3}: hit@1 {c['hit@1']:.0%} hit@3 {c['hit@3']:.0%} MRR {c['mrr']:.2f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", help="embedding models to compare (each gets a temporary index)")
    ap.add_argument("--misses", action="store_true", help="list covered questions whose guide wasn't in the top 3")
    ap.add_argument("--file", type=Path, default=QUESTIONS, help="question set (retrieval_questions_hard.jsonl has "
                                                                  "casual, Hinglish and misspelled questions)")
    args = ap.parse_args()
    questions = [json.loads(line) for line in args.file.read_text(encoding="utf-8").splitlines() if line.strip()]
    runs = {"keyword": keyword_search()}
    if args.models:
        for m in args.models:
            runs[f"chroma + {m}"] = with_model(m)
    else:
        runs["chroma (current index)"] = chroma_search()
    for name, search in runs.items():
        r = score(questions, search)
        show(name, r)
        if args.misses:
            for q, got in r["misses"]:
                print(f"    miss: {q!r} -> {got}")
    if args.models:
        for m in args.models:
            shutil.rmtree(ROOT / "data" / f"chroma_eval_{m.replace('/', '_')}", ignore_errors=True)


if __name__ == "__main__":
    main()
