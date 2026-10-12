"""
Knowledge Base Reindexing Utility
===================================
This administrative script rebuilds the entire ChromaDB vector database from scratch.

When to run this script:
  - Whenever you add new financial PDFs or TXT documents to `retrieval/documents/`.
  - Whenever you edit or delete existing knowledge files.
  - Whenever you change chunking parameters (CHUNK_SIZE or CHUNK_OVERLAP) in `config.py`.

Execution Steps:
  1. Drops the existing Chroma collection 'finadvisor_docs' to purge old embeddings.
  2. Reads all `.txt` documents from `retrieval/documents/`.
  3. Splits them into overlapping chunks with stable IDs.
  4. Embeds all chunks using SentenceTransformers and saves vectors into ChromaDB.
  5. Performs a sanity check query to verify the newly built index.
"""

import os
import chromadb
from retrieval.chunker import ingest_all_documents
from retrieval.vector_store import initialize_store, add_chunks
from config import CHROMA_PERSIST_DIR, EMBEDDING_MODEL, CHUNK_SIZE, CHUNK_OVERLAP

print("Resetting vector store (drop + recreate collection)...")

# Connect to ChromaDB client
_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
try:
    _client.delete_collection("finadvisor_docs")
    print("  Old collection deleted.")
except Exception as e:
    print(f"  No existing collection to delete ({e}).")

# Recreate fresh empty collection with specified embedding model
initialize_store(persist_dir=CHROMA_PERSIST_DIR, embedding_model=EMBEDDING_MODEL)

print("Ingesting all documents...")
# Locate documents directory
docs_dir = os.path.join(os.path.dirname(__file__), "retrieval", "documents")

# Generate text chunks with overlap
chunks = ingest_all_documents(documents_dir=docs_dir, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
print(f"  Generated {len(chunks)} chunks from {len(set(c.document_name for c in chunks))} documents.")

print("Adding chunks to vector store...")
# Embed and store in ChromaDB
add_chunks(chunks)
print("Done. Vector store rebuilt.")

# ------------------------------------------------------------------------------
# Sanity Check Query
# ------------------------------------------------------------------------------
from retrieval.agent import retrieve

print("\nRunning verification test query...")
results = retrieve("top 5 mutual funds India aggressive investor wealth growth", top_k=5)
print("Top 5 results:")
for r in results:
    preview = r.content[:80].encode("ascii", errors="backslashreplace").decode("ascii")
    print(f"  {r.document_name} | score: {r.relevance_score:.4f} | preview: {preview}...")

print("\nReindexing complete and operational.")


