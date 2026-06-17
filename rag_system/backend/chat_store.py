"""
Chat Store — SQLite Persistence for Conversations

Tables:
  conversations: id (TEXT PK), title, created_at, updated_at
  messages:      id (INTEGER PK), conversation_id (FK), role, content, 
                 ocr_text, image_filename, metadata_json, created_at
"""

import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "chat_history.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL DEFAULT 'New Chat',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id   TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role              TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content           TEXT NOT NULL DEFAULT '',
            ocr_text          TEXT,
            image_filename    TEXT,
            metadata_json     TEXT,
            created_at        TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conv 
            ON messages(conversation_id, created_at);
    """)
    conn.commit()
    conn.close()


# Initialize on import
_init_db()


# ── Conversation CRUD ────────────────────────────────────────────────────────

def create_conversation(title: str = "New Chat") -> dict:
    """Create a new conversation and return it."""
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (conv_id, title, now, now)
    )
    conn.commit()
    conn.close()
    return {"id": conv_id, "title": title, "created_at": now, "updated_at": now, "message_count": 0}


def list_conversations() -> list[dict]:
    """List all conversations ordered by most recently updated."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT c.id, c.title, c.created_at, c.updated_at,
               COUNT(m.id) as message_count
        FROM conversations c
        LEFT JOIN messages m ON m.conversation_id = c.id
        GROUP BY c.id
        ORDER BY c.updated_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversation(conv_id: str) -> dict | None:
    """Get a single conversation by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
        (conv_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_conversation_title(conv_id: str, title: str) -> bool:
    """Update the title of a conversation."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, now, conv_id)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_conversation(conv_id: str) -> bool:
    """Delete a conversation and all its messages."""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ── Message CRUD ─────────────────────────────────────────────────────────────

def add_message(
    conversation_id: str,
    role: str,
    content: str,
    ocr_text: str | None = None,
    image_filename: str | None = None,
    metadata: dict | None = None
) -> dict:
    """Add a message to a conversation."""
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata else None
    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO messages 
           (conversation_id, role, content, ocr_text, image_filename, metadata_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (conversation_id, role, content, ocr_text, image_filename, meta_json, now)
    )
    msg_id = cur.lastrowid
    # Update conversation's updated_at timestamp
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id)
    )
    conn.commit()
    conn.close()
    return {
        "id": msg_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "ocr_text": ocr_text,
        "image_filename": image_filename,
        "metadata": metadata,
        "created_at": now
    }


def get_messages(conversation_id: str) -> list[dict]:
    """Get all messages for a conversation, ordered chronologically."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, conversation_id, role, content, ocr_text, 
                  image_filename, metadata_json, created_at
           FROM messages 
           WHERE conversation_id = ? 
           ORDER BY created_at ASC""",
        (conversation_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["metadata"] = json.loads(d.pop("metadata_json")) if d.get("metadata_json") else None
        result.append(d)
    return result


def get_conversation_context(conversation_id: str, max_pairs: int = 5) -> list[dict]:
    """
    Get recent conversation history formatted for LLM context.
    Returns the last N user-assistant message pairs.

    User messages are stored with the full augmented content (original text +
    any OCR/image content), so no extra combination is needed here.
    Very long messages are truncated to avoid blowing up the context window.
    """
    messages = get_messages(conversation_id)
    # Return last max_pairs * 2 messages (each pair = user + assistant)
    recent = messages[-(max_pairs * 2):]
    result = []
    for m in recent:
        content = m["content"]
        # Truncate very long messages (e.g. large OCR dumps or verbose answers)
        max_chars = 800 if m["role"] == "user" else 600
        if len(content) > max_chars:
            content = content[:max_chars] + "…"
        result.append({"role": m["role"], "content": content})
    return result


def auto_title_from_query(conv_id: str, first_query: str):
    """Auto-generate a conversation title from the first user query."""
    title = first_query[:80].strip()
    if len(first_query) > 80:
        title += "…"
    update_conversation_title(conv_id, title)
