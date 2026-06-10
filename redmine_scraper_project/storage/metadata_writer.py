"""
Run Metadata Writer.

Every run generates a metadata file:
    output/TIMESTAMP/run_metadata.json

Schema:
    {
        "run_timestamp": "...",
        "issues_discovered": 100,
        "issues_fetched": 95,
        "issues_parsed": 95,
        "attachments_found": 230,
        "duration_seconds": 41
    }
"""

import logging
from pathlib import Path

from utils.file_utils import safe_write_json

logger = logging.getLogger("redmine_scraper")


class MetadataWriter:

    def save(self, run_dir, metadata):
        """
        Save run metadata.

        Args:
            run_dir: Path to the timestamped run directory.
            metadata: Dict with run statistics.
        """

        path = Path(run_dir) / "run_metadata.json"

        safe_write_json(path, metadata)

        logger.info(
            "Run metadata saved: %s", path
        )
