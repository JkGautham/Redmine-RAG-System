from __future__ import annotations
"""
Stage 2a: ChromaDB Retrieval

No model needed — pure vector + metadata operations.
Connects to the existing knowledge_builder chroma_store.

Metadata fields in the existing collection:
  issue_id, author, assignee, status, tracker, priority, category,
  created_on, updated_on, target_version, project, chunk_type
"""

import chromadb
import threading
from sentence_transformers import SentenceTransformer
from config import CHROMA_PATH, CHROMA_COLLECTION, EMBEDDING_MODEL

_embed_model = None
_embed_lock = threading.Lock()


def _get_embed() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        with _embed_lock:
            if _embed_model is None:
                print(f"=== [Embed] Loading embedding model: {EMBEDDING_MODEL} ===")
                _embed_model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _embed_model


_client = None
_collection = None
_chroma_lock = threading.Lock()


def _get_collection():
    global _client, _collection
    if _collection is None:
        with _chroma_lock:
            if _collection is None:
                _client = chromadb.PersistentClient(path=CHROMA_PATH)
                _collection = _client.get_collection(CHROMA_COLLECTION)
    return _collection


def _get_chroma_client():
    """Return the shared ChromaDB client (thread-safe)."""
    global _client
    if _client is None:
        with _chroma_lock:
            if _client is None:
                _client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _client


# ─── Vector search ───────────────────────────────────────────────────────────

def chroma_vector_search(query: str, n_results: int = 20) -> list[dict]:
    """
    Semantic search over issue descriptions + journal text.
    Returns all metadata fields + full document text.
    """
    embed = _get_embed()
    col   = _get_collection()

    embedding = embed.encode(query, normalize_embeddings=True).tolist()
    results = col.query(
        query_embeddings=[embedding],
        n_results=n_results,
        include=["metadatas", "distances", "documents"]
    )

    out = []
    for i, meta in enumerate(results["metadatas"][0]):
        issue_id = meta.get("issue_id")
        try:
            issue_id_int = int(issue_id) if issue_id else None
        except (ValueError, TypeError):
            issue_id_int = issue_id

        out.append({
            "issue_id":      issue_id,
            "subject":       meta.get("subject") or f"Issue #{issue_id}",
            "status":        meta.get("status", ""),
            "tracker":       meta.get("tracker", ""),
            "priority":      meta.get("priority", ""),
            "author":        meta.get("author", ""),
            "assignee":      meta.get("assignee", ""),
            "category":      meta.get("category", ""),
            "project":       meta.get("project", ""),
            "target_version": meta.get("target_version", ""),
            "created_on":    meta.get("created_on", ""),
            "updated_on":    meta.get("updated_on", ""),
            "chunk_type":    meta.get("chunk_type", ""),
            "vector_score":  round(1 - results["distances"][0][i], 4),
            # Full document text — no snippeting here; context builder will trim
            "text":          results["documents"][0][i],
        })
    return out


# ─── Filter by issue ID ──────────────────────────────────────────────────────

def chroma_filter_by_id(issue_ids: list[int]) -> list[dict]:
    """
    Direct metadata lookup by issue ID — for explicit #ID queries.
    Returns ALL chunks for the requested issue (summary + journal + description).
    """
    col = _get_collection()
    if not issue_ids:
        return []

    str_ids = [str(i) for i in issue_ids]
    results = col.get(
        where={"issue_id": {"$in": str_ids}},
        include=["metadatas", "documents"]
    )
    if not results or not results.get("metadatas"):
        return []

    out = []
    for i, meta in enumerate(results["metadatas"]):
        issue_id = meta.get("issue_id")
        out.append({
            "issue_id":      issue_id,
            "subject":       meta.get("subject") or f"Issue #{issue_id}",
            "status":        meta.get("status", ""),
            "tracker":       meta.get("tracker", ""),
            "priority":      meta.get("priority", ""),
            "author":        meta.get("author", ""),
            "assignee":      meta.get("assignee", ""),
            "category":      meta.get("category", ""),
            "project":       meta.get("project", ""),
            "target_version": meta.get("target_version", ""),
            "created_on":    meta.get("created_on", ""),
            "updated_on":    meta.get("updated_on", ""),
            "chunk_type":    meta.get("chunk_type", ""),
            "vector_score":  1.0,
            "text":          results["documents"][i],
        })
    return out


# ─── Journal retrieval ───────────────────────────────────────────────────────

def get_journals_for_issue(issue_id: int) -> list[dict]:
    """
    Pull all chunks for an issue from ChromaDB — these include the journal
    text embedded by the knowledge_builder scraper.
    """
    col = _get_collection()
    try:
        results = col.get(
            where={"issue_id": str(issue_id)},
            include=["metadatas", "documents"]
        )
        if not results["documents"]:
            return []
        return [
            {
                "author":     meta.get("author", "archive"),
                "created_on": meta.get("updated_on", meta.get("created_on", "")),
                "note":       doc,
                "chunk_type": meta.get("chunk_type", "")
            }
            for meta, doc in zip(results["metadatas"], results["documents"])
            if doc and doc.strip()
        ]
    except Exception:
        return []


# ─── Attachment index ────────────────────────────────────────────────────────

def get_attachment_index(issue_id: int) -> list[dict]:
    col = _get_collection()
    results = col.get(
        where={"issue_id": str(issue_id)},
        include=["metadatas"]
    )
    attachments = []
    for meta in results["metadatas"]:
        att_urls  = meta.get("attachment_urls", "")
        att_files = meta.get("attachment_filenames", "")
        if att_urls and att_files:
            for url, fname in zip(att_urls.split(","), att_files.split(",")):
                attachments.append({
                    "filename":     fname.strip(),
                    "content_type": _guess_content_type(fname.strip()),
                    "url":          url.strip(),
                    "file_size":    0
                })
    return attachments


def _guess_content_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "pdf": "application/pdf",
        "patch": "text/x-patch", "diff": "text/x-diff",
        "txt": "text/plain", "log": "text/plain",
        "rb": "text/x-ruby", "py": "text/x-python",
    }.get(ext, "application/octet-stream")
