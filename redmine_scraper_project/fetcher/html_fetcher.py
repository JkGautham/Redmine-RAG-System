"""
HTML Fetcher.

Fetches raw issue HTML from Redmine.

Responsibilities:
    - Fetch issue page
    - Return raw HTML to caller
    - Respect request delay

No parsing allowed inside fetcher.
"""

import time
import logging

from config.settings import (
    BASE_URL,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger("redmine_scraper")


class HTMLFetcher:

    def fetch(self, session, issue_id):
        """
        Fetch the raw HTML for a single issue.

        Args:
            session: Authenticated requests.Session.
            issue_id: The Redmine issue ID.

        Returns:
            Raw HTML string.

        Raises:
            Exception if the fetch fails.
        """

        url = f"{BASE_URL}/issues/{issue_id}"

        logger.debug("Fetching issue %d: %s", issue_id, url)

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        logger.debug(
            "Fetched issue %d: %d bytes",
            issue_id,
            len(response.text)
        )

        # Respect rate limiting
        time.sleep(REQUEST_DELAY)

        return response.text
