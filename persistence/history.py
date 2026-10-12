"""
Session & Chat History Persistence (Supabase with Local SQLite Fallback)
==========================================================================
This module manages database storage for user chat sessions and messages.

Dual-Storage Architecture:
  1. Primary Cloud Storage: Supabase (PostgreSQL)
     When SUPABASE_URL and SUPABASE_SERVICE_KEY are provided in .env, messages
     and sessions are synced to the cloud.
  2. Automatic Local Fallback: SQLite (data/advisor_history.db)
     If Supabase is offline, unreachable, or credentials are not provided,
     the system seamlessly switches to a local SQLite database so the application
     functions 100% offline without crashing.

Public Operations:
  - create_session()        -> Allocates a new session UUID
  - write_message()         -> Records a question, user answer, or recommendation
  - update_session_stage()  -> Advances session state ('elicitation' -> 'confirm' -> 'recommendation')
  - update_session_label()  -> Sets title shown in frontend sidebar
  - get_history()           -> Retrieves all messages in chronological order
  - list_sessions()         -> Lists past sessions for chat history navigation
  - delete_session()        -> Removes a session and all its messages
"""

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from persistence.supabase_client import get_client

# Setup logger
logger = logging.getLogger(__name__)

# Flag to disable Supabase if network or credentials fail, avoiding repetitive timeout delays
_supabase_disabled = False

# Location of local fallback SQLite database
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_DB_PATH = os.path.join(_DATA_DIR, "advisor_history.db")


# ==============================================================================
# Local SQLite Database Helper Functions
# ==============================================================================

def _get_sqlite_conn() -> sqlite3.Connection:
    """
    Connects to the local SQLite database file and creates required tables
    if they do not already exist.
    """
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row  # Enables dictionary-like row access
    with conn:
        conn.execute("PRAGMA foreign_keys = ON")
        # Table 1: Sessions
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT 'New session',
                stage TEXT NOT NULL DEFAULT 'elicitation'
            )
            """
        )
        # Table 2: Messages
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at)"
        )
    return conn


def _sqlite_create_session(label: str = "New session") -> str:
    """Inserts a new session record into SQLite."""
    session_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = _get_sqlite_conn()
    with conn:
        conn.execute(
            "INSERT INTO sessions (id, created_at, label, stage) VALUES (?, ?, ?, ?)",
            (session_id, now_iso, label, "elicitation"),
        )
    conn.close()
    logger.info("Created session %s (SQLite)", session_id)
    return session_id


def _sqlite_write_message(session_id: str, role: str, kind: str, content: Any) -> str:
    """Inserts a new message row into SQLite."""
    msg_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    content_str = json.dumps(content) if not isinstance(content, str) else content
    conn = _get_sqlite_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO messages (id, session_id, role, kind, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (msg_id, session_id, role, kind, content_str, now_iso),
        )
    conn.close()
    logger.debug("Wrote message %s to session %s (kind=%s, SQLite)", msg_id, session_id, kind)
    return msg_id


def _sqlite_update_session_stage(session_id: str, stage: str) -> None:
    """Updates session progression stage in SQLite."""
    conn = _get_sqlite_conn()
    with conn:
        conn.execute("UPDATE sessions SET stage = ? WHERE id = ?", (stage, session_id))
    conn.close()
    logger.debug("Session %s stage → %s (SQLite)", session_id, stage)


def _sqlite_update_session_label(session_id: str, label: str) -> None:
    """Updates display label for a session in SQLite."""
    conn = _get_sqlite_conn()
    with conn:
        conn.execute("UPDATE sessions SET label = ? WHERE id = ?", (label, session_id))
    conn.close()
    logger.debug("Session %s label → %s (SQLite)", session_id, label)


def _sqlite_get_history(session_id: str) -> list[dict]:
    """Retrieves all messages for a session from SQLite ordered by creation time."""
    conn = _get_sqlite_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, session_id, role, kind, content, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY created_at ASC
        """,
        (session_id,),
    )
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        c = row["content"]
        try:
            parsed_content = json.loads(c)
        except Exception:
            parsed_content = c
        result.append(
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "role": row["role"],
                "kind": row["kind"],
                "content": parsed_content,
                "created_at": row["created_at"],
            }
        )
    return result


def _sqlite_list_sessions() -> list[dict]:
    """Retrieves all sessions from SQLite ordered by most recent first."""
    conn = _get_sqlite_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, label, stage
        FROM sessions
        ORDER BY created_at DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _sqlite_delete_session(session_id: str) -> None:
    """Deletes a session and cascades deletion to all messages in SQLite."""
    conn = _get_sqlite_conn()
    with conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.close()
    logger.info("Deleted session %s (SQLite)", session_id)


# ==============================================================================
# Public API (Supabase with Automatic SQLite Fallback)
# ==============================================================================

def create_session(label: str = "New session") -> str:
    """
    Creates a new conversation session.
    Attempts cloud insertion in Supabase; falls back to SQLite on error.
    """
    global _supabase_disabled
    if not _supabase_disabled:
        try:
            client = get_client()
            result = (
                client.table("sessions")
                .insert({"label": label, "stage": "elicitation"})
                .execute()
            )
            session_id = result.data[0]["id"]
            logger.info("Created session %s (Supabase)", session_id)
            return session_id
        except Exception as e:
            logger.warning("Supabase unavailable (%s); switching to SQLite", e)
            _supabase_disabled = True

    return _sqlite_create_session(label)


def write_message(
    session_id: str,
    role: str,
    kind: str,
    content: Any,
) -> str:
    """
    Inserts a message record linked to the specified session.

    Parameters:
      session_id: ID of the parent conversation.
      role: 'user' or 'assistant'.
      kind: Message classification ('question', 'answer', 'profile_edit', 'recommendation').
      content: Payload object (string or JSON-serializable dictionary).

    Returns:
      Created message UUID string.
    """
    global _supabase_disabled
    if not _supabase_disabled:
        try:
            client = get_client()
            result = (
                client.table("messages")
                .insert({
                    "session_id": session_id,
                    "role": role,
                    "kind": kind,
                    "content": content,
                })
                .execute()
            )
            msg_id = result.data[0]["id"]
            logger.debug("Wrote message %s to session %s (kind=%s, Supabase)", msg_id, session_id, kind)
            return msg_id
        except Exception as e:
            logger.warning("Supabase unavailable (%s); switching to SQLite", e)
            _supabase_disabled = True

    return _sqlite_write_message(session_id, role, kind, content)


def update_session_stage(session_id: str, stage: str) -> None:
    """
    Updates the active progression stage of the chat session
    ('elicitation', 'confirm', or 'recommendation').
    """
    global _supabase_disabled
    if not _supabase_disabled:
        try:
            client = get_client()
            client.table("sessions").update({"stage": stage}).eq("id", session_id).execute()
            logger.debug("Session %s stage → %s (Supabase)", session_id, stage)
            return
        except Exception as e:
            logger.warning("Supabase unavailable (%s); switching to SQLite", e)
            _supabase_disabled = True

    _sqlite_update_session_stage(session_id, stage)


def update_session_label(session_id: str, label: str) -> None:
    """
    Updates the human-readable conversation title shown in the frontend sidebar.
    """
    global _supabase_disabled
    if not _supabase_disabled:
        try:
            client = get_client()
            client.table("sessions").update({"label": label}).eq("id", session_id).execute()
            logger.debug("Session %s label → %s (Supabase)", session_id, label)
            return
        except Exception as e:
            logger.warning("Supabase unavailable (%s); switching to SQLite", e)
            _supabase_disabled = True

    _sqlite_update_session_label(session_id, label)


def get_history(session_id: str) -> list[dict]:
    """
    Retrieves all messages for a session ordered by creation time ascending.
    """
    global _supabase_disabled
    if not _supabase_disabled:
        try:
            client = get_client()
            result = (
                client.table("messages")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at", desc=False)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.warning("Supabase unavailable (%s); switching to SQLite", e)
            _supabase_disabled = True

    return _sqlite_get_history(session_id)


def list_sessions() -> list[dict]:
    """
    Retrieves all previous sessions, sorted from newest to oldest.
    """
    global _supabase_disabled
    if not _supabase_disabled:
        try:
            client = get_client()
            result = (
                client.table("sessions")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.warning("Supabase unavailable (%s); switching to SQLite", e)
            _supabase_disabled = True

    return _sqlite_list_sessions()


def delete_session(session_id: str) -> None:
    """
    Deletes a session and all its associated messages.
    """
    global _supabase_disabled
    if not _supabase_disabled:
        try:
            client = get_client()
            client.table("sessions").delete().eq("id", session_id).execute()
            logger.info("Deleted session %s (Supabase)", session_id)
            return
        except Exception as e:
            logger.warning("Supabase unavailable (%s); switching to SQLite", e)
            _supabase_disabled = True

    _sqlite_delete_session(session_id)

