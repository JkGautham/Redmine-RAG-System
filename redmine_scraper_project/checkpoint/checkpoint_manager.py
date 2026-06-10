"""
Checkpoint Manager.

Tracks the last successful scrape so incremental runs
only process issues updated since the checkpoint.

Schema:
    {
        "last_successful_scrape": "2026-06-05T11:30:00",
        "issues_processed": 1244,
        "run_id": "2026-06-05_11-30-00"
    }

Checkpoint must only update after successful ingestion.
"""

import json
import shutil
import logging
from pathlib import Path

from config.settings import CHECKPOINT_FILE, CHECKPOINT_DIR

logger = logging.getLogger("redmine_scraper")


class CheckpointManager:

    def __init__(self):
        self._backup = None

    def load_checkpoint(self):
        """
        Load checkpoint from disk.

        Returns:
            dict with checkpoint data, or None if no checkpoint exists.
        """

        if not CHECKPOINT_FILE.exists():
            logger.info("No checkpoint found — full ingestion mode")
            return None

        try:
            data = json.loads(
                CHECKPOINT_FILE.read_text(encoding="utf-8")
            )

            logger.info(
                "Checkpoint loaded: last_scrape=%s, issues=%s, run=%s",
                data.get("last_successful_scrape"),
                data.get("issues_processed"),
                data.get("run_id")
            )

            return data

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(
                "Failed to load checkpoint: %s — treating as fresh run",
                e
            )
            return None

    def save_checkpoint(self, last_scrape, issues_processed, run_id):
        """
        Save checkpoint to disk atomically.

        Only call this after successful ingestion.

        Args:
            last_scrape: ISO timestamp of this scrape.
            issues_processed: Total issues processed this run.
            run_id: The run directory timestamp.
        """

        # Backup current checkpoint before overwriting
        self._backup_current()

        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

        payload = {
            "last_successful_scrape": last_scrape,
            "issues_processed": issues_processed,
            "run_id": run_id
        }

        # Atomic write: write to temp then rename
        tmp_file = CHECKPOINT_FILE.with_suffix(".tmp")

        try:
            tmp_file.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8"
            )

            tmp_file.replace(CHECKPOINT_FILE)

            logger.info(
                "Checkpoint saved: run=%s, issues=%d",
                run_id,
                issues_processed
            )

        except IOError as e:
            logger.error("Failed to save checkpoint: %s", e)

            if tmp_file.exists():
                tmp_file.unlink()

            raise

    def rollback_checkpoint(self):
        """
        Restore the previous checkpoint from backup.

        Use when ingestion fails and the checkpoint should not advance.
        """

        backup_file = CHECKPOINT_FILE.with_suffix(".bak")

        if backup_file.exists():

            shutil.copy2(backup_file, CHECKPOINT_FILE)

            logger.info("Checkpoint rolled back to previous state")

        elif CHECKPOINT_FILE.exists():

            CHECKPOINT_FILE.unlink()

            logger.info("Checkpoint removed (no backup to restore)")

    def _backup_current(self):
        """Create a backup of the current checkpoint."""

        if CHECKPOINT_FILE.exists():
            backup_file = CHECKPOINT_FILE.with_suffix(".bak")
            shutil.copy2(CHECKPOINT_FILE, backup_file)
