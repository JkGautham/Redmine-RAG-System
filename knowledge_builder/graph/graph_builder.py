"""
Task 2.9 — Graph Builder

Writes all nodes and edges to Neo4j.
Uses MERGE (idempotent) + UNWIND batching for performance.

Skips all writes if ENABLE_NEO4J = False (useful for dry-run tests).
"""

import logging
from contextlib import contextmanager

from config import (
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    NEO4J_BATCH_SIZE,
    ENABLE_NEO4J,
)

logger = logging.getLogger("knowledge_builder.graph.builder")

# ─────────────────────────────────────────────────────────────
# Driver singleton
# ─────────────────────────────────────────────────────────────

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        from neo4j import GraphDatabase
        logger.info("[GraphBuilder] Connecting to Neo4j: %s", NEO4J_URI)
        _driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        logger.info("[GraphBuilder] Connected")
    return _driver


@contextmanager
def _session():
    driver = _get_driver()
    with driver.session() as s:
        yield s


# ─────────────────────────────────────────────────────────────
# Cypher templates
# ─────────────────────────────────────────────────────────────

_MERGE_ISSUE = """
UNWIND $rows AS row
MERGE (i:Issue {id: row.id})
SET
  i.subject        = row.subject,
  i.status         = row.status,
  i.priority       = row.priority,
  i.tracker        = row.tracker,
  i.category       = row.category,
  i.target_version = row.target_version,
  i.start_date     = row.start_date,
  i.due_date       = row.due_date,
  i.done_ratio     = row.done_ratio,
  i.estimated_time = row.estimated_time,
  i.spent_time     = row.spent_time,
  i.created_on     = row.created_on,
  i.updated_on     = row.updated_on,
  i.summary        = row.summary
"""

_MERGE_SINGLETON = """
UNWIND $rows AS row
MERGE (n:{label} {{name: row.name}})
"""

_MERGE_ATTACHMENT = """
UNWIND $rows AS row
MERGE (a:Attachment {attachment_id: row.attachment_id})
SET
  a.filename  = row.filename,
  a.url       = row.url,
  a.size      = row.size
"""

_MERGE_JOURNAL = """
UNWIND $rows AS row
MERGE (j:JournalEntry {journal_id: row.journal_id})
SET
  j.author    = row.author,
  j.timestamp = row.timestamp,
  j.content   = row.content,
  j.changes   = row.changes
"""

_MERGE_ENTITY = """
UNWIND $rows AS row
MERGE (e:Entity {canonical_name: row.canonical_name, entity_type: row.entity_type})
SET
  e.display_name = row.display_name,
  e.label        = row.label
"""

# Generic edge template — rel_type is injected as string (validated from allowlist)
_MERGE_EDGE_TEMPLATE = """
UNWIND $rows AS row
MATCH (src:{src_label} {{{src_key}: row.source_id}})
MATCH (tgt:{tgt_label} {{{tgt_key}: row.target_id}})
MERGE (src)-[r:{rel_type}]->(tgt)
SET r.confidence = row.confidence,
    r.source     = row.source
"""

# Allowlist of valid relationship types (prevents injection)
_VALID_REL_TYPES = {
    "BELONGS_TO", "HAS_TRACKER", "HAS_STATUS", "HAS_PRIORITY",
    "IN_CATEGORY", "TARGETS_VERSION", "REPORTED_BY", "ASSIGNED_TO",
    "UPDATED_BY", "HAS_ATTACHMENT", "HAS_JOURNAL", "AUTHORED_BY",
    "HAS_EVENT", "MENTIONS", "USES", "AFFECTS",
    "BLOCKS", "BLOCKED_BY", "RELATED_TO", "DUPLICATES", "DUPLICATED_BY",
    "PRECEDES", "FOLLOWS", "PARENT_OF", "CHILD_OF", "COPIED_TO", "COPIED_FROM",
}

# Label → id property name
_LABEL_KEY = {
    "Issue":       "id",
    "Project":     "name",
    "User":        "name",
    "Tracker":     "name",
    "Status":      "name",
    "Priority":    "name",
    "Category":    "name",
    "Version":     "name",
    "Attachment":  "attachment_id",
    "JournalEntry":"journal_id",
    "Entity":      "canonical_name",
}


class GraphBuilder:
    """Write nodes and edges to Neo4j."""

    def write_issue(self, issue: dict, summary: str = "") -> None:
        """Upsert the Issue node."""
        if not ENABLE_NEO4J:
            return
        try:
            with _session() as s:
                s.run(_MERGE_ISSUE, rows=[{
                    "id":            issue["issue_id"],
                    "subject":       issue.get("subject", ""),
                    "status":        issue.get("status", ""),
                    "priority":      issue.get("priority", ""),
                    "tracker":       issue.get("tracker", ""),
                    "category":      issue.get("category", ""),
                    "target_version":issue.get("target_version", ""),
                    "start_date":    issue.get("start_date", ""),
                    "due_date":      issue.get("due_date", ""),
                    "done_ratio":    issue.get("done_ratio", ""),
                    "estimated_time":issue.get("estimated_time", ""),
                    "spent_time":    issue.get("spent_time", ""),
                    "created_on":    issue.get("created_on", ""),
                    "updated_on":    issue.get("updated_on", ""),
                    "summary":       summary,
                }])
            logger.debug("[GraphBuilder] Issue %s upserted", issue["issue_id"])
        except Exception as e:
            logger.error("[GraphBuilder] write_issue failed: %s", e)

    def write_entities(self, entities: list[dict]) -> None:
        """Upsert entity nodes by label type."""
        if not ENABLE_NEO4J or not entities:
            return

        # Group by label
        by_label: dict[str, list] = {}
        for ent in entities:
            lbl = ent.get("label", "Entity")
            by_label.setdefault(lbl, []).append(ent)

        try:
            with _session() as s:
                for label, group in by_label.items():
                    for i in range(0, len(group), NEO4J_BATCH_SIZE):
                        batch = group[i : i + NEO4J_BATCH_SIZE]
                        if label == "Entity":
                            s.run(_MERGE_ENTITY, rows=[{
                                "canonical_name": e.get("canonical_name", e["name"]),
                                "display_name":   e["name"],
                                "entity_type":    e.get("entity_type", "Unknown"),
                                "label":          label,
                            } for e in batch])
                        else:
                            s.run(
                                _MERGE_SINGLETON.format(label=label),
                                rows=[{"name": e["name"]} for e in batch],
                            )
            logger.debug(
                "[GraphBuilder] %d entity nodes written", len(entities)
            )
        except Exception as e:
            logger.error("[GraphBuilder] write_entities failed: %s", e)

    def write_attachments(self, issue: dict) -> None:
        """Upsert Attachment nodes."""
        if not ENABLE_NEO4J:
            return
        attachments = issue.get("attachments") or []
        if not attachments:
            return
        try:
            rows = [{
                "attachment_id": str(a["attachment_id"]),
                "filename":      a.get("filename", ""),
                "url":           a.get("url", ""),
                "size":          a.get("size", ""),
            } for a in attachments if a.get("attachment_id")]
            with _session() as s:
                for i in range(0, len(rows), NEO4J_BATCH_SIZE):
                    s.run(_MERGE_ATTACHMENT, rows=rows[i : i + NEO4J_BATCH_SIZE])
        except Exception as e:
            logger.error("[GraphBuilder] write_attachments failed: %s", e)

    def write_journals(self, issue: dict) -> None:
        """Upsert JournalEntry nodes."""
        if not ENABLE_NEO4J:
            return
        journals = issue.get("journals") or []
        if not journals:
            return
        try:
            rows = [{
                "journal_id": str(j["journal_id"]),
                "author":     j.get("author", ""),
                "timestamp":  j.get("timestamp", ""),
                "content":    j.get("content", ""),
                "changes":    j.get("changes", []),
            } for j in journals if j.get("journal_id")]
            with _session() as s:
                for i in range(0, len(rows), NEO4J_BATCH_SIZE):
                    s.run(_MERGE_JOURNAL, rows=rows[i : i + NEO4J_BATCH_SIZE])
        except Exception as e:
            logger.error("[GraphBuilder] write_journals failed: %s", e)

    def write_edges(self, edges: list[dict]) -> None:
        """
        Write all edge types in bulk.
        Edges are grouped by (src_label, tgt_label, rel_type) for batching.
        """
        if not ENABLE_NEO4J or not edges:
            return

        # Group edges
        groups: dict[tuple, list] = {}
        for edge in edges:
            rel = edge.get("rel_type", "RELATED_TO")
            if rel not in _VALID_REL_TYPES:
                logger.warning("[GraphBuilder] Skipping unknown rel_type: %s", rel)
                continue
            key = (edge["source_label"], edge["target_label"], rel)
            groups.setdefault(key, []).append(edge)

        try:
            with _session() as s:
                for (src_lbl, tgt_lbl, rel_type), group in groups.items():
                    src_key = _LABEL_KEY.get(src_lbl, "id")
                    tgt_key = _LABEL_KEY.get(tgt_lbl, "id")
                    cypher = _MERGE_EDGE_TEMPLATE.format(
                        src_label=src_lbl,
                        src_key=src_key,
                        tgt_label=tgt_lbl,
                        tgt_key=tgt_key,
                        rel_type=rel_type,
                    )
                    for i in range(0, len(group), NEO4J_BATCH_SIZE):
                        batch = group[i : i + NEO4J_BATCH_SIZE]
                        rows = [{
                            "source_id":  e["source_id"],
                            "target_id":  e["target_id"],
                            "confidence": e.get("confidence", 1.0),
                            "source":     e.get("source", ""),
                        } for e in batch]
                        s.run(cypher, rows=rows)

            logger.debug("[GraphBuilder] %d edges written", len(edges))
        except Exception as e:
            logger.error("[GraphBuilder] write_edges failed: %s", e)

    def write_entity_edges(self, issue_id: int, entities: list[dict]) -> None:
        """
        Write Issue→Entity MENTIONS edges for semantically extracted entities.
        """
        if not ENABLE_NEO4J or not entities:
            return
        sem_entities = [e for e in entities if e.get("source") in ("gliner", "qwen_llm")]
        if not sem_entities:
            return
        edges = [{
            "source_label": "Issue",
            "source_id":    issue_id,
            "rel_type":     "MENTIONS",
            "target_label": "Entity",
            "target_id":    e.get("canonical_name", e["name"]),
            "confidence":   e.get("confidence", 0.7),
            "source":       e.get("source", ""),
        } for e in sem_entities]
        self.write_edges(edges)

    def close(self):
        global _driver
        if _driver:
            _driver.close()
            _driver = None
            logger.info("[GraphBuilder] Neo4j connection closed")
