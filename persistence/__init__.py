"""
Persistence module — Supabase-backed session and message storage.

Replaces localStorage-only session management with durable Supabase
persistence. Every session start creates a `sessions` row, and every
chat turn (user answer, confirmation edit, recommendation + evidence)
writes a `messages` row.

Components:
    supabase_client.py — singleton Supabase client initialisation
    history.py         — CRUD operations for sessions and messages
"""
