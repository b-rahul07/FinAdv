"""
AI Financial Advisor — Central System Configuration
=====================================================
This file stores all the global configuration options, environment variables,
model names, thresholds, and feature toggles used throughout the entire backend.

It reads secrets and custom settings from your '.env' file, but provides
sensible local defaults if no '.env' file is present.
"""

import os
from dotenv import load_dotenv

# Load key-value pairs from .env file into the system environment
load_dotenv()

# ==============================================================================
# 1. Feature Toggles (Ablation / Behavior Switches)
# ==============================================================================

# When TRUE, the system pauses after asking questionnaire questions so the user
# can review, edit, and confirm their risk profile before generating advice.
ENABLE_PREFERENCE_CONFIRMATION: bool = True

# When TRUE, the system verifies and generates full provenance audit logs
# (retrieved chunk IDs, sentiment scores, rule compliance IDs, and model metadata).
ENABLE_AUDIT_EVIDENCE: bool = True

# When TRUE, enables Chain-of-Verification (CoVe) / self-critique where the advisor
# runs extra LLM passes to audit its recommendation. Default is FALSE for responsive
# live demos (can be enabled via ENABLE_SELF_CRITIQUE=true).
ENABLE_SELF_CRITIQUE: bool = os.getenv("ENABLE_SELF_CRITIQUE", "False").lower() in ("true", "1")


# ==============================================================================
# 2. Artificial Intelligence Models
# ==============================================================================

# URL where the local Ollama server is listening (default: port 11434)
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Which Ollama model to use for chat generation (e.g., phi4-mini, llama3, etc.)
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "phi4-mini")

# Name of the Hugging Face embedding model used to turn text into vector numbers
# for semantic similarity search in our knowledge base.
EMBEDDING_MODEL: str = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

# FinBERT model used to analyze the financial sentiment (Positive/Negative/Neutral)
# of recent market news headlines.
FINBERT_MODEL: str = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")


# ==============================================================================
# 3. Document Retrieval & Knowledge Base Settings (RAG)
# ==============================================================================

# Directory folder where the ChromaDB vector database is saved on disk
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")

# How many characters each chunk of financial document text should contain
CHUNK_SIZE: int = 512

# How many characters overlap between consecutive chunks so context isn't cut off
CHUNK_OVERLAP: int = 64

# Maximum number of most-relevant document chunks retrieved per user question
# 3 chunks provide focused, high-precision context without prompt bloat.
TOP_K_CHUNKS: int = 3


# ==============================================================================
# 4. Market News Sentiment Settings
# ==============================================================================

# Maximum number of live financial news headlines to fetch for market context
MAX_HEADLINES: int = 10

# Minimum confidence score (0.0 to 1.0) needed to classify sentiment as positive/negative
SENTIMENT_THRESHOLD: float = 0.6


# ==============================================================================
# 5. User Risk & Preference Questionnaire
# ==============================================================================

# Number of structured profiling questions asked to understand the user's financial profile
NUM_ELICITATION_QUESTIONS: int = 7


# ==============================================================================
# 6. Database & Persistence (Supabase / SQLite)
# ==============================================================================

# Supabase cloud database credentials (optional: if blank, system falls back to local SQLite)
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")


# ==============================================================================
# 7. Logging & Diagnostics
# ==============================================================================

# Standard log output verbosity (e.g., INFO, DEBUG, WARNING, ERROR)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

