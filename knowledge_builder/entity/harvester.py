"""
Task 2.1 — Entity Harvester

Extracts structured entities directly from JSON fields.
No LLM. No inference. Confidence = 1.0.

Returns a flat list of entity dicts ready for canonicalization.
"""

import logging

logger = logging.getLogger("knowledge_builder.entity.harvester")

# Field → Neo4j node label mapping
FIELD_LABEL_MAP = {
    "project":         "Project",
    "author":          "User",
    "assignee":        "User",
    "tracker":         "Tracker",
    "status":          "Status",
    "category":        "Category",
    "target_version":  "Version",
    "priority":        "Priority",
}

# Values that mean "no value" in Redmine
EMPTY_VALUES = {"-", "", None, "none", "n/a"}


class EntityHarvester:
    """Extract typed entities from a parsed issue JSON dict."""

    def harvest(self, issue: dict) -> list[dict]:
        """
        Args:
            issue: Parsed issue dict from scraper JSON.

        Returns:
            List of entity dicts:
            {
                "name":       str,
                "label":      str,   # Neo4j node label
                "source":     "json_field",
                "confidence": 1.0,
            }
        """
        entities = []
        seen = set()

        for field, label in FIELD_LABEL_MAP.items():
            value = issue.get(field, "")

            # Normalise: strip, skip empty/placeholder values
            if isinstance(value, str):
                value = value.strip()

            if str(value).lower() in EMPTY_VALUES:
                continue

            key = (label, str(value).lower())
            if key in seen:
                continue
            seen.add(key)

            entities.append({
                "name":       str(value),
                "label":      label,
                "source":     "json_field",
                "confidence": 1.0,
            })

            logger.debug(
                "[Harvester] issue %s → %s: %s",
                issue.get("issue_id"), label, value,
            )

        # Custom fields — treat each as a generic Entity
        for cf_name, cf_value in (issue.get("custom_fields") or {}).items():
            if not cf_value or str(cf_value).lower() in EMPTY_VALUES:
                continue
            key = ("CustomField", cf_name.lower())
            if key in seen:
                continue
            seen.add(key)

            entities.append({
                "name":       cf_value,
                "label":      "Entity",
                "source":     "custom_field",
                "field_name": cf_name,
                "confidence": 1.0,
            })

        logger.debug(
            "[Harvester] issue %s — %d entities harvested",
            issue.get("issue_id"), len(entities),
        )

        return entities
