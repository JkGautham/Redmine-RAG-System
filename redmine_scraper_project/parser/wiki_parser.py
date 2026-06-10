"""
Wiki Parser.

Extracts wiki page references from:
    a.wiki-page

Deduplicates and returns a sorted list of unique wiki page names.

Output:
    ["Plugins", "RedmineInstall", "Theme_List"]
"""

import logging

logger = logging.getLogger("redmine_scraper")


class WikiParser:

    def parse(self, soup):
        """
        Extract unique wiki page references.

        Args:
            soup: BeautifulSoup of the issue page.

        Returns:
            Sorted list of unique wiki page name strings.
        """

        wiki_links = set()

        for link in soup.select("a.wiki-page"):

            text = link.get_text(strip=True)

            if text:
                wiki_links.add(text)

        result = sorted(wiki_links)

        logger.debug(
            "Parsed %d unique wiki links", len(result)
        )

        return result
