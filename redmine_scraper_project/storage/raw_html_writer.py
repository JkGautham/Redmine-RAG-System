"""
Raw HTML Writer.

Saves raw issue HTML to the archive:
    output/TIMESTAMP/raw_html/{issue_id}.html

Raw HTML is the source of truth and must be stored permanently.
"""

import logging
from pathlib import Path

from utils.file_utils import safe_write

logger = logging.getLogger("redmine_scraper")


class RawHTMLWriter:

    def save(self, run_dir, issue_id, html):
        """
        Save raw HTML for an issue.

        Args:
            run_dir: Path to the timestamped run directory.
            issue_id: The Redmine issue ID.
            html: Raw HTML string.
        """

        path = Path(run_dir) / "raw_html" / f"{issue_id}.html"

        safe_write(path, html)

        logger.debug(
            "Saved raw HTML for issue %d: %s (%d bytes)",
            issue_id,
            path,
            len(html)
        )
