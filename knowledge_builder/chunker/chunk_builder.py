"""
Task 2.7 — Chunk Builder

Produces hierarchical chunks for an issue following the chunking strategy:

  Parent:
    {issue_id}_summary          ← LLM or fallback summary

  Children:
    {issue_id}_title            ← subject line
    {issue_id}_description      ← full description text
    {issue_id}_j_{journal_id}   ← one per journal entry (if has content)
    {issue_id}_att_meta_{n}     ← attachment metadata (not OCR content)

Each chunk is a dict ready for embedding + ChromaDB upsert:
{
    "chunk_id":   str,
    "issue_id":   int,
    "chunk_type": str,
    "text":       str,
    "metadata":   dict,   ← stored as ChromaDB metadata
}
"""

import logging

logger = logging.getLogger("knowledge_builder.chunker")


class ChunkBuilder:
    """Build all chunks for a single issue."""

    def build(self, issue: dict, summary: str) -> list[dict]:
        """
        Args:
            issue:   Parsed issue dict.
            summary: Pre-generated summary string (Task 2.6).

        Returns:
            List of chunk dicts.
        """
        issue_id = issue["issue_id"]
        base_meta = self._base_metadata(issue)

        chunks = []

        # ── Parent: Summary ───────────────────────────────────────────
        if summary:
            chunks.append({
                "chunk_id":   f"{issue_id}_summary",
                "issue_id":   issue_id,
                "chunk_type": "summary",
                "text":       summary,
                "metadata":   {**base_meta, "chunk_type": "summary"},
            })

        # ── Child: Title ──────────────────────────────────────────────
        subject = (issue.get("subject") or "").strip()
        if subject:
            chunks.append({
                "chunk_id":   f"{issue_id}_title",
                "issue_id":   issue_id,
                "chunk_type": "title",
                "text":       subject,
                "metadata":   {**base_meta, "chunk_type": "title"},
            })

        # ── Child: Description ─────────────────────────────────────────
        description = (issue.get("description") or "").strip()
        if description:
            chunks.append({
                "chunk_id":   f"{issue_id}_description",
                "issue_id":   issue_id,
                "chunk_type": "description",
                "text":       description,
                "metadata":   {**base_meta, "chunk_type": "description"},
            })

        # ── Children: Journal Entries ──────────────────────────────────
        for journal in (issue.get("journals") or []):
            content = (journal.get("content") or "").strip()
            changes = journal.get("changes") or []

            # Build text from content + changes
            parts = []
            if content:
                parts.append(content)
            if changes:
                parts.append("Changes: " + "; ".join(changes))

            text = "\n".join(parts).strip()
            if not text:
                continue

            j_id = journal.get("journal_id", "?")
            chunks.append({
                "chunk_id":   f"{issue_id}_j_{j_id}",
                "issue_id":   issue_id,
                "chunk_type": "journal",
                "text":       text,
                "metadata":   {
                    **base_meta,
                    "chunk_type":  "journal",
                    "journal_id":  str(j_id),
                    "journal_author": journal.get("author", ""),
                    "journal_timestamp": journal.get("timestamp", ""),
                },
            })

        # ── Children: Attachment Metadata (no OCR) ─────────────────────
        for idx, att in enumerate(issue.get("attachments") or [], start=1):
            filename  = att.get("filename", "")
            mime_type = att.get("mime_type", "")
            size      = att.get("size", "")
            url       = att.get("url", "")
            att_id    = att.get("attachment_id", idx)

            # Text = searchable description of the attachment
            text = f"Attachment: {filename}"
            if mime_type:
                text += f" ({mime_type})"
            if size:
                text += f", size {size}"

            chunks.append({
                "chunk_id":   f"{issue_id}_att_meta_{att_id}",
                "issue_id":   issue_id,
                "chunk_type": "attachment_metadata",
                "text":       text,
                "metadata":   {
                    **base_meta,
                    "chunk_type":   "attachment_metadata",
                    "attachment_id": str(att_id),
                    "filename":     filename,
                    "mime_type":    mime_type or "",
                    "size":         size,
                    "url":          url,
                },
            })

        logger.debug(
            "[ChunkBuilder] issue %s — %d chunks built (%d journals, %d attachments)",
            issue_id,
            len(chunks),
            len([c for c in chunks if c["chunk_type"] == "journal"]),
            len([c for c in chunks if c["chunk_type"] == "attachment_metadata"]),
        )

        return chunks

    @staticmethod
    def _base_metadata(issue: dict) -> dict:
        """Common metadata stored on every chunk."""
        return {
            "issue_id":       str(issue.get("issue_id", "")),
            "project":        issue.get("project", ""),
            "tracker":        issue.get("tracker", ""),
            "status":         issue.get("status", ""),
            "priority":       issue.get("priority", ""),
            "category":       issue.get("category", ""),
            "target_version": issue.get("target_version", ""),
            "author":         issue.get("author", ""),
            "assignee":       issue.get("assignee", ""),
            "created_on":     issue.get("created_on", ""),
            "updated_on":     issue.get("updated_on", ""),
        }
