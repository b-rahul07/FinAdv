"""
Retrieval Agent (Two-Stage RAG Pipeline)
==========================================
The Retrieval Agent powers the factual grounding of our AI Advisor.
To ensure the LLM receives the highest-accuracy regulatory excerpts and doesn't
hallucinate financial rules or tax rates, it uses a Two-Stage Search Architecture:

  Stage 1: Candidate Generation (Bi-Encoder / Dense Vector Search)
           Fast vector similarity in ChromaDB retrieves the top 3x candidates (e.g., 21 chunks).
  Stage 2: Precision Reranking (Cross-Encoder / ms-marco-MiniLM)
           A specialized transformer model reads the query and chunk together to
           accurately score semantic relevance, selecting the top-k highest quality chunks.
"""

from dataclasses import dataclass
from typing import Optional
from sentence_transformers import CrossEncoder
from retrieval.vector_store import search, initialize_store
from config import CHROMA_PERSIST_DIR, EMBEDDING_MODEL, TOP_K_CHUNKS


@dataclass
class RetrievedChunk:
    """
    Data model representing a single excerpt retrieved from our financial document library.
    
    Attributes:
      chunk_id: Stable identifier (e.g. 'doc02_chunk05') used for audit citations
      document_name: Source file name (e.g. 'SEBI_Mutual_Fund_Regulations.pdf')
      content: Exact text excerpt from the document
      relevance_score: Cross-encoder ranking score indicating semantic relevance
      metadata: Extra context such as page numbers and section headers
    """
    chunk_id: str
    document_name: str
    content: str
    relevance_score: float
    metadata: dict


# Global flags to ensure models and vector databases are loaded only once (singleton pattern)
_store_initialized = False
_cross_encoder = None


def _ensure_initialized():
    """Initializes the ChromaDB vector database connection if not already open."""
    global _store_initialized
    if not _store_initialized:
        initialize_store(persist_dir=CHROMA_PERSIST_DIR, embedding_model=EMBEDDING_MODEL)
        _store_initialized = True


def _get_cross_encoder():
    """Lazily loads the MS-MARCO Cross-Encoder model into memory."""
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    return _cross_encoder


def retrieve(
    query: str,
    top_k: int = TOP_K_CHUNKS,
    filters: Optional[dict] = None,
) -> list[RetrievedChunk]:
    """
    Retrieves the top-k most relevant financial document chunks for a given query.

    Algorithm:
      1. Vector Search: Queries ChromaDB for candidate_k = top_k * 3 chunks using dense embeddings.
      2. Cross-Encoder Reranking: Scores every (query, chunk) pair using a deep cross-encoder.
      3. Sort & Slice: Sorts candidates by cross-encoder score descending and returns the top-k.

    Parameters:
      query: The user's financial question, enriched with goal and risk parameters.
      top_k: Number of top document excerpts to return (default from config: 7).
      filters: Optional metadata filtering criteria.

    Returns:
      List of RetrievedChunk objects ordered by verified relevance.
    """
    _ensure_initialized()

    # --------------------------------------------------------------------------
    # Step 1: Broad Candidate Retrieval via Dense Vector Search
    # --------------------------------------------------------------------------
    candidate_k = top_k * 3
    raw_results = search(query=query, top_k=candidate_k, filters=filters)

    if not raw_results:
        return []

    # --------------------------------------------------------------------------
    # Step 2: Cross-Encoder Deep Semantic Reranking
    # --------------------------------------------------------------------------
    encoder = _get_cross_encoder()

    chunks = []
    pairs = []

    # Prepare input pairs for the cross-encoder: [query, chunk_text]
    for r in raw_results:
        chunk = RetrievedChunk(
            chunk_id=r["chunk_id"],
            document_name=r["metadata"].get("source", "unknown"),
            content=r["content"],
            relevance_score=r["relevance_score"],
            metadata=r["metadata"]
        )
        chunks.append(chunk)
        pairs.append([query, chunk.content])

    # Predict relevance scores for all pairs simultaneously
    scores = encoder.predict(pairs)

    # Overwrite initial vector distance with high-precision cross-encoder score
    for i, score in enumerate(scores):
        chunks[i].relevance_score = float(score)

    # --------------------------------------------------------------------------
    # Step 3: Sort by Cross-Encoder Score Descending
    # --------------------------------------------------------------------------
    chunks.sort(key=lambda x: x.relevance_score, reverse=True)

    # Return only the top-k highest quality excerpts
    return chunks[:top_k]


