"""
Task 2.2 — Entity Canonicalization

Normalises entity names:
  - lowercase
  - strip whitespace / trailing punctuation
  - replace spaces with underscores for multi-word tech names
  - fuzzy deduplication via RapidFuzz (threshold 90)

Maintains an EntityRegistry dict that persists across the run
and is saved to disk as entity_registry.json.
"""

import re
import json
import logging
from pathlib import Path

from rapidfuzz import fuzz

logger = logging.getLogger("knowledge_builder.entity.canonicalizer")

# Minimum similarity score (0-100) to consider two names the same entity
FUZZY_THRESHOLD = 88


def _base_normalize(name: str) -> str:
    """Lowercase, strip punctuation, compress whitespace."""
    name = name.strip().lower()
    # Remove trailing colon/dash artefacts from Redmine field parsing
    name = re.sub(r"[:\-]+$", "", name).strip()
    # Collapse internal whitespace
    name = re.sub(r"\s+", " ", name)
    return name


def _to_canonical(name: str) -> str:
    """Convert to a canonical key: snake_case."""
    name = _base_normalize(name)
    # Replace spaces and common separators with underscores
    name = re.sub(r"[\s\-/]+", "_", name)
    # Remove any remaining non-alphanumeric except underscore and dot
    name = re.sub(r"[^\w.]", "", name)
    return name


class EntityRegistry:
    """
    In-memory store: canonical_key → {display_name, label, aliases}.
    Can be saved/loaded as JSON.
    """

    def __init__(self, path: Path):
        self._path = path
        self._registry: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def register(self, name: str, label: str) -> str:
        """
        Register an entity name.

        Returns the canonical key.
        """
        canonical = _to_canonical(name)

        if canonical in self._registry:
            # Already known — just add alias
            existing = self._registry[canonical]
            if name not in existing["aliases"]:
                existing["aliases"].append(name)
            return canonical

        # Fuzzy search among existing canonical keys
        matched = self._fuzzy_match(canonical, label)
        if matched:
            entry = self._registry[matched]
            if name not in entry["aliases"]:
                entry["aliases"].append(name)
            logger.debug(
                "[Canonicalizer] '%s' → fuzzy match '%s' (label=%s)",
                name, matched, label,
            )
            return matched

        # New entity
        self._registry[canonical] = {
            "canonical_name": canonical,
            "display_name":   name,
            "label":          label,
            "aliases":        [name],
        }

        logger.debug(
            "[Canonicalizer] New entity: '%s' (label=%s)", canonical, label
        )

        return canonical

    def get(self, canonical_key: str) -> dict | None:
        return self._registry.get(canonical_key)

    def all_entities(self) -> list[dict]:
        return list(self._registry.values())

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=2, ensure_ascii=False)
        logger.info(
            "[Canonicalizer] Registry saved: %d entities → %s",
            len(self._registry), self._path,
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _load(self):
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._registry = json.load(f)
            logger.info(
                "[Canonicalizer] Registry loaded: %d entities",
                len(self._registry),
            )
        else:
            logger.info("[Canonicalizer] No existing registry — starting fresh")

    def _fuzzy_match(self, canonical: str, label: str) -> str | None:
        """Find an existing entry that is close enough to be the same entity."""
        for key, entry in self._registry.items():
            # Only fuzzy-match within the same label type
            if entry.get("label") != label:
                continue
            score = fuzz.ratio(canonical, key)
            if score >= FUZZY_THRESHOLD:
                return key
        return None


class Canonicalizer:
    """Wraps EntityRegistry to canonicalize a list of entity dicts."""

    def __init__(self, registry: EntityRegistry):
        self._registry = registry

    def canonicalize(self, entities: list[dict]) -> list[dict]:
        """
        Attach `canonical_name` to each entity dict.

        Args:
            entities: Output of EntityHarvester or SemanticExtractor.

        Returns:
            Same list with `canonical_name` field added.
        """
        result = []
        for ent in entities:
            name  = ent.get("name", "")
            label = ent.get("label", "Entity")

            canonical = self._registry.register(name, label)

            result.append({**ent, "canonical_name": canonical})

        return result
