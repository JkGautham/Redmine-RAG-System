"""
One-Time ChromaDB Indexing Script

Indexes all parsed JSON issues from the scraper output into ChromaDB.
Run this ONCE to populate the chroma_store before starting the API server.

Usage:
    cd rag_system/backend
    python setup/index_chroma.py --issues-dir ../../redmine_scraper_project/output/2026-06-08_11-18-40/parsed_json

This creates/updates three collections:
  - issues          → vector embeddings of issue text
  - journals        → vector embeddings of individual journal notes
  - attachments_index → metadata-only index (no embeddings)

NOTE: The existing knowledge_builder chroma_store uses "redmine_issues" collection
      with a different schema. This script creates the RAG pipeline's own collections
      alongside the existing ones.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from tqdm import tqdm

# Add backend dir to path so config is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHROMA_PATH, EMBEDDING_MODEL

import chromadb
from sentence_transformers import SentenceTransformer

EMBED = SentenceTransformer(EMBEDDING_MODEL)
client = chromadb.PersistentClient(path=CHROMA_PATH)


def index_issues(issues_dir: str):
    col = client.get_or_create_collection(
        name="issues",
        metadata={"hnsw:space": "cosine"}
    )
    files = sorted(os.listdir(issues_dir))
    batch_docs, batch_embeds, batch_meta, batch_ids = [], [], [], []

    for fname in tqdm(files, desc="Indexing issues"):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(issues_dir, fname)) as f:
            issue = json.load(f)

        # Combined text: subject + description + first 300 chars of each journal note
        journal_text = " ".join(
            j.get("content", "")[:300]
            for j in issue.get("journals", [])
            if j.get("content", "").strip()
        )
        combined = f"{issue.get('subject', '')} {issue.get('description','')[:800]} {journal_text}"
        combined = combined[:2000]

        embedding = EMBED.encode(combined, normalize_embeddings=True).tolist()

        batch_docs.append(combined)
        batch_embeds.append(embedding)
        batch_meta.append({
            "issue_id":   issue["issue_id"],
            "subject":    issue.get("subject", "")[:500],
            "status":     issue.get("status", ""),
            "tracker":    issue.get("tracker", ""),
            "priority":   issue.get("priority", ""),
            "created_on": issue.get("created_on", "")[:10],
            "updated_on": issue.get("updated_on", "")[:10],
        })
        batch_ids.append(str(issue["issue_id"]))

        if len(batch_docs) >= 500:
            col.upsert(documents=batch_docs, embeddings=batch_embeds,
                       metadatas=batch_meta, ids=batch_ids)
            batch_docs, batch_embeds, batch_meta, batch_ids = [], [], [], []

    if batch_docs:
        col.upsert(documents=batch_docs, embeddings=batch_embeds,
                   metadatas=batch_meta, ids=batch_ids)
    print(f"Issues indexed: {col.count()}")


def index_journals(issues_dir: str):
    col = client.get_or_create_collection(
        name="journals",
        metadata={"hnsw:space": "cosine"}
    )
    files = sorted(os.listdir(issues_dir))
    batch_docs, batch_embeds, batch_meta, batch_ids = [], [], [], []
    uid = 0

    for fname in tqdm(files, desc="Indexing journals"):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(issues_dir, fname)) as f:
            issue = json.load(f)

        for j in issue.get("journals", []):
            note = j.get("content", "").strip()
            if not note:
                continue

            embedding = EMBED.encode(note[:1000], normalize_embeddings=True).tolist()
            batch_docs.append(note[:1000])
            batch_embeds.append(embedding)
            batch_meta.append({
                "issue_id":   issue["issue_id"],
                "author":     j.get("author", ""),
                "created_on": j.get("timestamp", "")[:10]
            })
            batch_ids.append(f"j_{uid}")
            uid += 1

            if len(batch_docs) >= 500:
                col.upsert(documents=batch_docs, embeddings=batch_embeds,
                           metadatas=batch_meta, ids=batch_ids)
                batch_docs, batch_embeds, batch_meta, batch_ids = [], [], [], []

    if batch_docs:
        col.upsert(documents=batch_docs, embeddings=batch_embeds,
                   metadatas=batch_meta, ids=batch_ids)
    print(f"Journals indexed: {col.count()}")


def index_attachment_metadata(issues_dir: str):
    """
    Index attachment metadata from parsed JSONs.
    Attachment URLs are stored as-is (e.g. "/attachments/13").
    """
    col = client.get_or_create_collection(name="attachments_index")
    files = sorted(os.listdir(issues_dir))
    batch_meta, batch_ids, batch_docs = [], [], []
    uid = 0

    for fname in tqdm(files, desc="Indexing attachments"):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(issues_dir, fname)) as f:
            issue = json.load(f)

        for att in issue.get("attachments", []):
            att_id = str(att.get("attachment_id", ""))
            fname_att = att.get("filename", "")
            url = att.get("url", "")

            # Infer content type from filename extension
            ext = os.path.splitext(fname_att)[1].lower()
            ctype = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".pdf": "application/pdf",
                ".patch": "text/x-patch", ".diff": "text/x-diff",
                ".txt": "text/plain", ".log": "text/plain",
            }.get(ext, "application/octet-stream")

            batch_meta.append({
                "issue_id":      issue["issue_id"],
                "attachment_id": att_id,
                "filename":      fname_att,
                "content_type":  ctype,
                "url":           url,
                "file_size":     0   # not stored in JSON — checked at download time
            })
            batch_ids.append(f"a_{uid}")
            batch_docs.append("")   # no text needed for attachment index
            uid += 1

            if len(batch_docs) >= 500:
                col.upsert(documents=batch_docs, metadatas=batch_meta, ids=batch_ids)
                batch_docs, batch_meta, batch_ids = [], [], []

    if batch_docs:
        col.upsert(documents=batch_docs, metadatas=batch_meta, ids=batch_ids)
    print(f"Attachments indexed: {col.count()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index Redmine issues into ChromaDB")
    parser.add_argument(
        "--issues-dir",
        default="../../redmine_scraper_project/output/2026-06-08_11-18-40/parsed_json",
        help="Path to directory containing parsed JSON issue files"
    )
    args = parser.parse_args()

    issues_dir = str(Path(args.issues_dir).resolve())
    if not os.path.isdir(issues_dir):
        print(f"ERROR: Directory not found: {issues_dir}")
        sys.exit(1)

    print(f"ChromaDB path: {CHROMA_PATH}")
    print(f"Issues dir:    {issues_dir}")
    print()

    index_issues(issues_dir)
    index_journals(issues_dir)
    index_attachment_metadata(issues_dir)

    print("\nDone. All collections indexed.")
