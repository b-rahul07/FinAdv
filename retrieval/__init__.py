"""
Retrieval Agent module.

Provides RAG over 15–20 curated Indian financial documents
(AMFI/SEBI factsheets, ELSS/PPF/SIP rules, sample EMI/BNPL T&Cs).

Components:
    agent.py        — main callable: query → ranked chunks with stable chunk IDs
    chunker.py      — document ingestion and chunking logic
    vector_store.py — ChromaDB vector store interface
    documents/      — source documents (pre-converted to text)
"""
