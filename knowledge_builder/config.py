"""
knowledge_builder — Central Configuration

All settings are env-var overridable.
Set REDMINE_SCRAPER_OUTPUT to point at your scraper output root.
"""

import os
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────

KB_DIR = Path(__file__).resolve().parent

# Root of redmine_scraper_project output (scan all run subdirs)
SCRAPER_OUTPUT_DIR = Path(
    os.environ.get(
        "REDMINE_SCRAPER_OUTPUT",
        str(KB_DIR.parent / "redmine_scraper_project" / "output"),
    )
)

# ChromaDB persistence directory
CHROMA_PATH = Path(
    os.environ.get("CHROMA_PATH", str(KB_DIR / "chroma_store"))
)

# Entity registry (JSON file persisted between runs)
ENTITY_REGISTRY_PATH = KB_DIR / "entity_registry.json"

# Incremental indexer state
INDEXER_STATE_PATH = KB_DIR / "indexer_state.json"

# ─────────────────────────────────────────────────────────────
# NEO4J
# ─────────────────────────────────────────────────────────────

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4jpassword")

# ─────────────────────────────────────────────────────────────
# OLLAMA / LLM
# ─────────────────────────────────────────────────────────────

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Primary model for summarisation + LLM fallback (fits in 6 GB VRAM)
SUMMARIZER_MODEL = os.environ.get("SUMMARIZER_MODEL", "qwen2.5:1.5b")
RELATION_LLM_MODEL = os.environ.get("RELATION_LLM_MODEL", "qwen2.5:1.5b")
ENTITY_LLM_MODEL = os.environ.get("ENTITY_LLM_MODEL", "qwen2.5:1.5b")

# ─────────────────────────────────────────────────────────────
# EMBEDDING MODEL
# ─────────────────────────────────────────────────────────────

EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"
)
EMBEDDING_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "64"))

# ─────────────────────────────────────────────────────────────
# GLINER
# ─────────────────────────────────────────────────────────────

GLINER_MODEL = os.environ.get("GLINER_MODEL", "urchade/gliner_small-v2.1")
GLINER_THRESHOLD = float(os.environ.get("GLINER_THRESHOLD", "0.5"))

GLINER_ENTITY_LABELS = [
    "Technology",
    "Database",
    "Framework",
    "OperatingSystem",
    "ProgrammingLanguage",
    "Version",
    "API",
    "ConfigFile",
    "Library",
    "Tool",
]

# ─────────────────────────────────────────────────────────────
# CHROMA COLLECTION
# ─────────────────────────────────────────────────────────────

CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "redmine_issues")

# ─────────────────────────────────────────────────────────────
# PIPELINE BEHAVIOUR
# ─────────────────────────────────────────────────────────────

# --limit flag default (0 = process all)
DEFAULT_LIMIT = int(os.environ.get("KB_LIMIT", "0"))

# Number of parallel workers for CPU-bound tasks
CPU_WORKERS = int(os.environ.get("KB_CPU_WORKERS", "4"))

# Neo4j write batch size
NEO4J_BATCH_SIZE = int(os.environ.get("NEO4J_BATCH_SIZE", "100"))

# Skip issues that haven't changed since last run
ENABLE_INCREMENTAL = os.environ.get(
    "KB_INCREMENTAL", "true"
).strip().lower() in ("true", "1", "yes")

# Skip summarisation (useful for fast test runs)
ENABLE_SUMMARIZATION = os.environ.get(
    "KB_SUMMARIZATION", "true"
).strip().lower() in ("true", "1", "yes")

# Skip Neo4j writes (useful when Neo4j isn't running yet)
ENABLE_NEO4J = os.environ.get(
    "KB_NEO4J", "true"
).strip().lower() in ("true", "1", "yes")

# Skip ChromaDB writes
ENABLE_CHROMA = os.environ.get(
    "KB_CHROMA", "true"
).strip().lower() in ("true", "1", "yes")
