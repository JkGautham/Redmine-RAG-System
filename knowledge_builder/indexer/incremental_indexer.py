"""
Task 2.11 — Incremental Indexer

Tracks which issues have been processed and detects changes.
State is persisted to indexer_state.json.

Comparison keys:
  - updated_on
  - journal_count
  - attachment_count
"""

import json
import logging
from pathlib import Path

from config import INDEXER_STATE_PATH, ENABLE_INCREMENTAL

logger = logging.getLogger("knowledge_builder.indexer")


class IncrementalIndexer:
    """Skip issues that haven't changed since last run."""

    def __init__(self):
        self._state: dict = {}
        self._dirty = False
        self._load()

    def needs_processing(self, issue: dict) -> bool:
        """
        Returns True if the issue should be (re)processed.

        Always returns True if ENABLE_INCREMENTAL is False.
        """
        if not ENABLE_INCREMENTAL:
            return True

        issue_id = str(issue.get("issue_id", ""))
        if not issue_id:
            return True

        current = self._fingerprint(issue)
        previous = self._state.get(issue_id)

        if previous is None:
            logger.debug("[Indexer] issue %s — NEW", issue_id)
            return True

        if current != previous:
            logger.debug(
                "[Indexer] issue %s — CHANGED (prev=%s, curr=%s)",
                issue_id, previous, current,
            )
            return True

        logger.debug("[Indexer] issue %s — UNCHANGED — skipping", issue_id)
        return False

    def mark_done(self, issue: dict) -> None:
        """Record the current fingerprint for this issue."""
        issue_id = str(issue.get("issue_id", ""))
        if issue_id:
            self._state[issue_id] = self._fingerprint(issue)
            self._dirty = True

    def save(self) -> None:
        """Persist state to disk."""
        if not self._dirty:
            return
        INDEXER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(INDEXER_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)
        logger.info(
            "[Indexer] State saved: %d issues tracked → %s",
            len(self._state), INDEXER_STATE_PATH,
        )
        self._dirty = False

    def stats(self) -> dict:
        return {"tracked_issues": len(self._state)}

    # ------------------------------------------------------------------ #
    # Private
    # ------------------------------------------------------------------ #

    def _load(self):
        if INDEXER_STATE_PATH.exists():
            with open(INDEXER_STATE_PATH, "r", encoding="utf-8") as f:
                self._state = json.load(f)
            logger.info(
                "[Indexer] State loaded: %d tracked issues",
                len(self._state),
            )
        else:
            logger.info("[Indexer] No state file — fresh run")

    @staticmethod
    def _fingerprint(issue: dict) -> dict:
        return {
            "updated_on":       issue.get("updated_on", ""),
            "journal_count":    len(issue.get("journals") or []),
            "attachment_count": len(issue.get("attachments") or []),
        }
