"""
JSON Writer.

Saves parsed issue data as JSON:
    output/TIMESTAMP/parsed_json/{issue_id}.json
"""

import json
import logging
from pathlib import Path

from utils.file_utils import safe_write_json

logger = logging.getLogger("redmine_scraper")


def save_json(data, path):
    """
    Save data as formatted JSON.

    Args:
        data: Dict to serialize.
        path: Target file path.
    """

    safe_write_json(path, data)


class JSONWriter:

    def save(self, run_dir, issue_id, issue_data):
        """
        Save parsed issue JSON.

        Args:
            run_dir: Path to the timestamped run directory.
            issue_id: The Redmine issue ID.
            issue_data: Parsed issue dict (canonical schema).
        """

        path = Path(run_dir) / "parsed_json" / f"{issue_id}.json"

        safe_write_json(path, issue_data)

        logger.debug(
            "Saved parsed JSON for issue %d: %s",
            issue_id,
            path
        )
