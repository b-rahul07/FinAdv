"""Rebuild the document search index (data/chroma_db) from finadvisor/retrieval/documents/*.txt.

    python scripts/build_index.py

Run after adding, editing or removing a library document. Needs the `rag` extra: pip install -e .[rag]
"""

from finadvisor.retrieval.chroma import build_index, retrieve

if __name__ == "__main__":
    n = build_index()
    print(f"indexed {n} chunks")
    for c in retrieve("What is ELSS and how is it taxed?"):
        print(f"  {c.relevance_score:7.3f}  {c.document_name}")
