"""Two-stage search over the document library (from the earlier prototype's retrieval module).

Guides are split by section (finadvisor/retrieval/chunks.py), each piece labelled with its guide and heading.
Stage 1: dense vector search in ChromaDB returns 3x the wanted number of pieces.
Stage 2: a cross-encoder (ms-marco-MiniLM-L-6-v2) rescores each (query, chunk) pair and the best are kept.

The index lives in data/chroma_db and is rebuilt with `python scripts/build_index.py` after the documents change.
Needs the `rag` extra (chromadb, sentence-transformers); the API falls back to keyword search without it.
"""

from __future__ import annotations

from finadvisor.retrieval import DOCS_DIR
from finadvisor.retrieval.chunks import Chunk, chunk_file
from finadvisor.settings import ROOT

PERSIST_DIR = ROOT / "data" / "chroma_db"
COLLECTION = "finadvisor_docs"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANKER = "cross-encoder/ms-marco-MiniLM-L-6-v2"


_collection = None
_reranker = None


def _open(reset: bool = False):
    global _collection
    import chromadb
    from chromadb.utils import embedding_functions
    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    if reset:
        try:
            client.delete_collection(COLLECTION)
        except Exception:  # noqa: BLE001 - nothing to delete on a first build
            pass
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    _collection = client.get_or_create_collection(name=COLLECTION, embedding_function=ef)
    return _collection


def build_index() -> int:
    """Drop and rebuild the index from every .txt file in the library. Returns the number of chunks."""
    col = _open(reset=True)
    chunks = [c for f in sorted(DOCS_DIR.glob("*.txt")) for c in chunk_file(f)]
    if chunks:
        col.upsert(ids=[c.chunk_id for c in chunks], documents=[c.content for c in chunks],
                   metadatas=[{"source": c.document_name} for c in chunks])
    return len(chunks)


def retrieve(query: str, top_k: int = 3) -> list[Chunk]:
    global _reranker
    col = _collection or _open()
    res = col.query(query_texts=[query], n_results=top_k * 3)
    if not res["ids"] or not res["ids"][0]:
        return []
    chunks = [Chunk(cid, meta.get("source", "unknown"), doc)
              for cid, doc, meta in zip(res["ids"][0], res["documents"][0], res["metadatas"][0])]
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(RERANKER)
    for c, score in zip(chunks, _reranker.predict([[query, c.content] for c in chunks])):
        c.relevance_score = float(score)
    return sorted(chunks, key=lambda c: -c.relevance_score)[:top_k]
