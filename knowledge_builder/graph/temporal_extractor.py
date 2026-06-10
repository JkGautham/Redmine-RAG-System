"""
Task 2.10 — Temporal Event Extractor

Parses journal changes[] strings into structured StatusChange,
PriorityChange, AssigneeChange, VersionChange, CategoryChange events.

These become HAS_EVENT edges in Neo4j:
  (Issue)-[:HAS_EVENT]->(StatusChange {old, new, timestamp, author})
"""

import re
import logging

logger = logging.getLogger("knowledge_builder.graph.temporal_extractor")

# Patterns: (regex, event_type, group_map)
_CHANGE_PATTERNS = [
    (
        re.compile(
            r"Status changed from (.+?) to (.+)", re.IGNORECASE
        ),
        "StatusChange",
    ),
    (
        re.compile(
            r"Priority changed from (.+?) to (.+)", re.IGNORECASE
        ),
        "PriorityChange",
    ),
    (
        re.compile(
            r"Assignee (?:changed from (.+?) to|set to) (.+)",
            re.IGNORECASE,
        ),
        "AssigneeChange",
    ),
    (
        re.compile(
            r"Target version (?:changed from (.+?) to|set to) (.+)",
            re.IGNORECASE,
        ),
        "VersionChange",
    ),
    (
        re.compile(
            r"Category (?:changed from (.+?) to|set to) (.+)",
            re.IGNORECASE,
        ),
        "CategoryChange",
    ),
    (
        re.compile(
            r"Resolution (?:changed from (.+?) to|set to) (.+)",
            re.IGNORECASE,
        ),
        "ResolutionChange",
    ),
    (
        re.compile(
            r"Subject changed from (.+?) to (.+)",
            re.IGNORECASE,
        ),
        "SubjectChange",
    ),
]


def _parse_change_string(change: str) -> tuple[str, str, str] | None:
    """
    Parse one change string.

    Returns (event_type, old_value, new_value) or None if no pattern matches.
    """
    for pattern, event_type in _CHANGE_PATTERNS:
        m = pattern.match(change.strip())
        if m:
            groups = m.groups()
            if len(groups) == 2:
                old_val = (groups[0] or "").strip()
                new_val = (groups[1] or "").strip()
                return event_type, old_val, new_val
    return None


class TemporalExtractor:
    """Extract structured change events from issue journals."""

    def extract(self, issue: dict) -> list[dict]:
        """
        Args:
            issue: Parsed issue dict.

        Returns:
            List of event dicts:
            {
                "event_type":  str,
                "old_value":   str,
                "new_value":   str,
                "timestamp":   str,
                "author":      str,
                "issue_id":    int,
                "journal_id":  str,
            }
        """
        events = []
        issue_id = issue.get("issue_id")

        for journal in (issue.get("journals") or []):
            j_id      = journal.get("journal_id", "")
            timestamp = journal.get("timestamp", "")
            author    = journal.get("author", "")

            for change in (journal.get("changes") or []):
                parsed = _parse_change_string(change)
                if parsed:
                    event_type, old_val, new_val = parsed
                    events.append({
                        "event_type": event_type,
                        "old_value":  old_val,
                        "new_value":  new_val,
                        "timestamp":  timestamp,
                        "author":     author,
                        "issue_id":   issue_id,
                        "journal_id": str(j_id),
                        "raw":        change,
                    })

        logger.debug(
            "[TemporalExtractor] issue %s — %d events extracted",
            issue_id, len(events),
        )

        return events

    def write_events(self, events: list[dict], graph_builder) -> None:
        """
        Write event nodes + HAS_EVENT edges to Neo4j via graph_builder.

        Each event becomes a node of its event_type label, connected to Issue.
        """
        if not events:
            return

        from config import ENABLE_NEO4J
        if not ENABLE_NEO4J:
            return

        try:
            from graph.graph_builder import _session, NEO4J_BATCH_SIZE

            # Group by event_type for batching
            by_type: dict[str, list] = {}
            for ev in events:
                by_type.setdefault(ev["event_type"], []).append(ev)

            merge_event_cypher = """
UNWIND $rows AS row
MATCH (i:Issue {{id: row.issue_id}})
CREATE (e:{event_type} {{
    old_value:  row.old_value,
    new_value:  row.new_value,
    timestamp:  row.timestamp,
    author:     row.author,
    journal_id: row.journal_id,
    raw:        row.raw
}})
MERGE (i)-[:HAS_EVENT]->(e)
"""
            with _session() as s:
                for event_type, group in by_type.items():
                    cypher = merge_event_cypher.format(event_type=event_type)
                    for i in range(0, len(group), NEO4J_BATCH_SIZE):
                        s.run(cypher, rows=group[i : i + NEO4J_BATCH_SIZE])

            logger.debug(
                "[TemporalExtractor] %d events written to Neo4j", len(events)
            )
        except Exception as e:
            logger.error("[TemporalExtractor] write_events failed: %s", e)
