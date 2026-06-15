"""
RAG System Backend — Central Configuration

Reads all settings from environment variables.
Copy .env.example to .env and fill in your values.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the backend directory
load_dotenv(Path(__file__).parent / ".env")

# ─── Neo4j ───────────────────────────────────────────────────────────────────
NEO4J_URI      = os.environ.get("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.environ.get("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4jpassword")

# ─── ChromaDB ────────────────────────────────────────────────────────────────
# Points to the existing knowledge_builder chroma_store by default
_default_chroma = str(
    Path(__file__).resolve().parent.parent.parent
    / "knowledge_builder" / "chroma_store"
)
CHROMA_PATH       = os.environ.get("CHROMA_PATH", _default_chroma)
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "redmine_issues")

# ─── Redmine ─────────────────────────────────────────────────────────────────
REDMINE_BASE_URL      = os.environ.get("REDMINE_BASE_URL", "https://www.redmine.org")
REDMINE_SESSION_COOKIE = os.environ.get("REDMINE_SESSION_COOKIE", "")

# ─── Ollama ──────────────────────────────────────────────────────────────────
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# ─── Model Names ─────────────────────────────────────────────────────────────
PRIMARY_MODEL    = os.environ.get("PRIMARY_MODEL",    "qwen3:8b")
CYPHER_MODEL     = os.environ.get("CYPHER_MODEL",     "qwen2.5-coder:7b")
EMBEDDING_MODEL  = os.environ.get("EMBEDDING_MODEL",  "BAAI/bge-small-en-v1.5")

# ─── Attachment download ──────────────────────────────────────────────────────
# Local directory where downloaded attachments are cached
_default_att = str(Path(__file__).resolve().parent / "attachments_cache")
ATTACHMENTS_CACHE_DIR = os.environ.get("ATTACHMENTS_CACHE_DIR", _default_att)
