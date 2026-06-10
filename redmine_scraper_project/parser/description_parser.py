"""
Description Parser.

Extracts the issue description from:
    div.description div.wiki

Preserves:
    - Plain text
    - Lists
    - Hyperlinks (as text)
    - Code blocks

No summarization. Store normalized text.
"""

import logging

logger = logging.getLogger("redmine_scraper")


class DescriptionParser:

    def parse(self, soup):
        """
        Extract the issue description.

        Args:
            soup: BeautifulSoup of the issue page.

        Returns:
            Description text as string.
        """

        desc_div = soup.select_one("div.description div.wiki")

        if not desc_div:
            # Fallback: try div.description directly
            desc_div = soup.select_one("div.description")

        if not desc_div:
            return ""

        # Get text preserving structure with newlines
        text = desc_div.get_text("\n", strip=True)

        return text
