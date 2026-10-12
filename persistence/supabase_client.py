"""
Supabase Cloud Client (Singleton Connection)
==============================================
This module manages the connection to Supabase (our cloud PostgreSQL database).
It follows the Singleton design pattern so only one authenticated client instance
is instantiated and reused across the entire backend.
"""

import logging
from supabase import create_client, Client
import config

logger = logging.getLogger(__name__)

# Cached singleton client instance
_client: Client | None = None


def get_client() -> Client:
    """
    Returns the active Supabase client instance, instantiating it on the first call.

    Validates that SUPABASE_URL and SUPABASE_SERVICE_KEY exist in .env.
    If missing or invalid, raises a RuntimeError caught by the history module
    to gracefully fallback to local SQLite.
    """
    global _client
    if _client is None:
        url = config.SUPABASE_URL
        key = config.SUPABASE_SERVICE_KEY
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
            )
        _client = create_client(url, key)
        logger.info("Supabase client initialised for %s", url)
    return _client

