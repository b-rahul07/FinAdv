"""
Document Ingestion & Text Chunker
===================================
This module handles breaking down raw financial text files (SEBI circulars,
RBI guidelines, AMFI mutual fund guides, income tax rules) into bite-sized,
overlapping text chunks.

Why chunking with overlap is essential:
  1. Embedding models (e.g., MiniLM) have maximum sequence length limits (e.g., 512 tokens).
  2. Overlapping windows (e.g., 64 characters) ensure that important context or
     sentences sitting on chunk boundaries are not chopped in half and lost.
  3. Assigning stable chunk IDs (e.g., 'sebi_rules.txt_chunk03') provides an exact
     traceable citation (provenance) for the UI evidence panel.
"""

import os
import glob
from dataclasses import dataclass


@dataclass
class Chunk:
    """
    Data model representing a chunk of text extracted from a larger document.
    """
    chunk_id: str           # Unique identifier: "{doc_name}_chunk{index}"
    document_name: str      # Original document filename
    content: str            # Raw text snippet within this chunk window
    char_start: int         # Starting character index in original source file
    char_end: int           # Ending character index in original source file
    metadata: dict          # Source attributes for filtering & citations


def chunk_document(
    document_path: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[Chunk]:
    """
    Reads a text file and splits it into overlapping windows.

    Algorithm:
      Uses a sliding window approach with a step size of (chunk_size - chunk_overlap).
      If a document is 1000 characters long with size=512 and overlap=64:
        Chunk 0: chars 0 to 512
        Chunk 1: chars 448 to 960 (starts 64 chars before Chunk 0 ended)
        Chunk 2: chars 896 to 1000

    Parameters:
      document_path: Path to the .txt file on disk.
      chunk_size: Target window size in characters (default: 512).
      chunk_overlap: Number of characters to overlap with previous chunk (default: 64).

    Returns:
      List of Chunk objects with stable chunk_ids.
    """
    with open(document_path, 'r', encoding='utf-8') as f:
        text = f.read()

    doc_name = os.path.basename(document_path)
    chunks = []

    start = 0
    text_len = len(text)
    index = 0

    # Calculate step size to advance the sliding window
    step = chunk_size - chunk_overlap
    if step <= 0:
        step = chunk_size

    # Slide across the entire document
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk_content = text[start:end].strip()
        
        # Only keep non-empty chunks
        if chunk_content:
            chunks.append(Chunk(
                chunk_id=f"{doc_name}_chunk{index}",
                document_name=doc_name,
                content=chunk_content,
                char_start=start,
                char_end=end,
                metadata={"source": doc_name}
            ))
            index += 1
        start += step

    return chunks


def ingest_all_documents(
    documents_dir: str = "retrieval/documents",
    chunk_size: int = 512,
    chunk_overlap: int = 64
) -> list[Chunk]:
    """
    Scans the documents directory for all '*.txt' files and processes them into chunks.

    Parameters:
      documents_dir: Directory containing knowledge base text files.
      chunk_size: Target chunk size in characters.
      chunk_overlap: Overlap length between consecutive chunks.

    Returns:
      Consolidated list of all Chunk objects across all knowledge documents.
    """
    all_chunks = []
    pattern = os.path.join(documents_dir, "*.txt")

    # Find every .txt file and chunk it
    for file_path in glob.glob(pattern):
        all_chunks.extend(chunk_document(file_path, chunk_size, chunk_overlap))

    return all_chunks

