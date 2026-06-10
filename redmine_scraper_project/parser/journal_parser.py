"""
Journal Parser.

Extracts journal entries (history/notes) from:
    div#history div.journal

Each journal entry has:
    - journal_id: from the div id attribute (e.g. "change-42174")
    - author: from h4 user link
    - timestamp: from h4 <a title="...">
    - content: from .wiki div
    - changes: from ul.details li

Preserves complete text.
"""

import re
import logging

from models.journal import Journal

logger = logging.getLogger("redmine_scraper")


class JournalParser:

    def parse(self, soup):
        """
        Extract journal entries from the issue page.

        Args:
            soup: BeautifulSoup of the issue page.

        Returns:
            List of Journal dicts.
        """

        journals = []

        history_div = soup.select_one("div#history")

        if not history_div:
            return journals

        for journal_div in history_div.select("div.journal"):

            try:

                journal = self._parse_one(journal_div)

                journals.append(journal.to_dict())

            except Exception as e:
                logger.warning(
                    "Failed parsing journal entry: %s", e
                )

        logger.debug(
            "Parsed %d journal entries", len(journals)
        )

        return journals

    def _parse_one(self, journal_div):
        """Parse a single journal div into a Journal model."""

        # ------------------------------------------------
        # JOURNAL ID from div id
        # e.g. id="change-42174" → 42174
        # ------------------------------------------------

        journal_id = ""

        div_id = journal_div.get("id", "")

        match = re.search(r"change-(\d+)", div_id)

        if match:
            journal_id = match.group(1)

        # ------------------------------------------------
        # AUTHOR from h4 user link
        # ------------------------------------------------

        author = ""

        h4 = journal_div.select_one("h4")

        if h4:
            user_link = h4.select_one("a.user")

            if user_link:
                author = user_link.get_text(strip=True)

        # ------------------------------------------------
        # TIMESTAMP from h4 <a title="...">
        # The actual date is in the title attribute:
        #   <a title="05/21/2013 07:39 AM">...
        # ------------------------------------------------

        timestamp = ""

        if h4:
            date_link = h4.select_one("a[title]")

            if date_link:
                timestamp = date_link.get("title", "")

        # ------------------------------------------------
        # CONTENT from .wiki div
        # ------------------------------------------------

        content = ""

        wiki_div = journal_div.select_one(".wiki")

        if wiki_div:
            content = wiki_div.get_text("\n", strip=True)

        # ------------------------------------------------
        # CHANGES from ul.details li
        # ------------------------------------------------

        changes = []

        for li in journal_div.select("ul.details li"):
            change_text = li.get_text(" ", strip=True)
            if change_text:
                changes.append(change_text)

        return Journal(
            journal_id=journal_id,
            author=author,
            timestamp=timestamp,
            content=content,
            changes=changes
        )
