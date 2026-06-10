"""
Task 2.4 — Deterministic Relationship Extractor

Builds graph edges directly from structured JSON fields.
No LLM. Confidence = 1.0.

Produces edge dicts:
{
    "source_label": "Issue",
    "source_id":    int,
    "rel_type":     str,      # Neo4j relationship type
    "target_label": str,
    "target_id":    str | int,
    "properties":   dict,     # extra edge properties
    "confidence":   float,
    "source":       "deterministic",
}
"""

import logging
import re

logger = logging.getLogger("knowledge_builder.relation.deterministic_extractor")

# Redmine relations[] type → Neo4j relationship type
RELATION_TYPE_MAP = {
    "DUPLICATES":    "DUPLICATES",
    "DUPLICATED":    "DUPLICATED_BY",
    "BLOCKS":        "BLOCKS",
    "BLOCKED":       "BLOCKED_BY",
    "RELATES":       "RELATED_TO",
    "PRECEDES":      "PRECEDES",
    "FOLLOWS":       "FOLLOWS",
    "COPIED_TO":     "COPIED_TO",
    "COPIED_FROM":   "COPIED_FROM",
    "PARENT":        "PARENT_OF",
    "CHILD":         "CHILD_OF",
}


class DeterministicRelationExtractor:
    """Extract edges from JSON fields with full confidence."""

    def extract(self, issue: dict) -> list[dict]:
        """
        Args:
            issue: Parsed issue dict.

        Returns:
            List of edge dicts.
        """
        edges = []
        issue_id = issue.get("issue_id")

        # ── Issue → Project ────────────────────────────────────────────
        if issue.get("project"):
            edges.append(self._edge(
                issue_id, "Issue", "BELONGS_TO",
                issue["project"], "Project",
            ))

        # ── Issue → Tracker ────────────────────────────────────────────
        if issue.get("tracker"):
            edges.append(self._edge(
                issue_id, "Issue", "HAS_TRACKER",
                issue["tracker"], "Tracker",
            ))

        # ── Issue → Status ─────────────────────────────────────────────
        if issue.get("status"):
            edges.append(self._edge(
                issue_id, "Issue", "HAS_STATUS",
                issue["status"], "Status",
            ))

        # ── Issue → Priority ───────────────────────────────────────────
        if issue.get("priority"):
            edges.append(self._edge(
                issue_id, "Issue", "HAS_PRIORITY",
                issue["priority"], "Priority",
            ))

        # ── Issue → Category ───────────────────────────────────────────
        if issue.get("category") and issue["category"] not in ("-", ""):
            edges.append(self._edge(
                issue_id, "Issue", "IN_CATEGORY",
                issue["category"], "Category",
            ))

        # ── Issue → Version ────────────────────────────────────────────
        if issue.get("target_version") and issue["target_version"] not in ("-", ""):
            edges.append(self._edge(
                issue_id, "Issue", "TARGETS_VERSION",
                issue["target_version"], "Version",
            ))

        # ── Issue → User (author) ──────────────────────────────────────
        if issue.get("author") and issue["author"] not in ("-", ""):
            edges.append(self._edge(
                issue_id, "Issue", "REPORTED_BY",
                issue["author"], "User",
            ))

        # ── Issue → User (assignee) ────────────────────────────────────
        if issue.get("assignee") and issue["assignee"] not in ("-", ""):
            edges.append(self._edge(
                issue_id, "Issue", "ASSIGNED_TO",
                issue["assignee"], "User",
            ))

        # ── Issue → Attachment ─────────────────────────────────────────
        for att in (issue.get("attachments") or []):
            att_id = att.get("attachment_id")
            if att_id:
                edges.append(self._edge(
                    issue_id, "Issue", "HAS_ATTACHMENT",
                    att_id, "Attachment",
                ))

        # ── Issue → JournalEntry ───────────────────────────────────────
        for j in (issue.get("journals") or []):
            j_id = j.get("journal_id")
            if j_id:
                edges.append(self._edge(
                    issue_id, "Issue", "HAS_JOURNAL",
                    j_id, "JournalEntry",
                ))
                # JournalEntry → User (author)
                if j.get("author") and j["author"] not in ("", "-"):
                    edges.append(self._edge(
                        j_id, "JournalEntry", "AUTHORED_BY",
                        j["author"], "User",
                    ))

        # ── Issue → Issue (relations[]) ────────────────────────────────
        for rel in (issue.get("relations") or []):
            rel_type = RELATION_TYPE_MAP.get(
                str(rel.get("type", "")).upper().strip(),
                "RELATED_TO",
            )
            target = rel.get("target_issue")
            if target:
                target_str = str(target).strip()
                if target_str.lower().startswith('r'):
                    continue
                digits = re.sub(r"[^\d]", "", target_str)
                if digits:
                    edges.append(self._edge(
                        issue_id, "Issue", rel_type,
                        int(digits), "Issue",
                    ))

        logger.debug(
            "[DeterministicRelation] issue %s — %d edges extracted",
            issue_id, len(edges),
        )

        return edges

    @staticmethod
    def _edge(
        source_id, source_label,
        rel_type,
        target_id, target_label,
        properties=None,
        confidence=1.0,
    ) -> dict:
        return {
            "source_label": source_label,
            "source_id":    source_id,
            "rel_type":     rel_type,
            "target_label": target_label,
            "target_id":    target_id,
            "properties":   properties or {},
            "confidence":   confidence,
            "source":       "deterministic",
        }
