"""
Relation Parser.

Extracts issue relations from:
    div#relations

Supported relation types:
    blocks, blocked, duplicates, duplicated,
    relates, follows, precedes, copied_to, copied_from

Output:
    [{"type": "BLOCKS", "target_issue": 27934}]
"""

import re
import logging

from models.relation import Relation

logger = logging.getLogger("redmine_scraper")

# Map Redmine relation text to normalized types
RELATION_MAP = {
    "blocks": "BLOCKS",
    "blocked by": "BLOCKED",
    "is duplicate of": "DUPLICATES",
    "has duplicate": "DUPLICATED",
    "related to": "RELATES",
    "follows": "FOLLOWS",
    "precedes": "PRECEDES",
    "copied to": "COPIED_TO",
    "copied from": "COPIED_FROM",
}


class RelationParser:

    def parse(self, soup):
        """
        Extract relations from the issue page.

        Args:
            soup: BeautifulSoup of the issue page.

        Returns:
            List of Relation dicts.
        """

        relations = []

        rel_div = soup.select_one("div#relations")

        if not rel_div:
            return relations

        # Relations appear as text with links to target issues
        # e.g. "Related to #27934" or "Blocks #27935"
        # They can be in various formats depending on Redmine version

        # Try parsing from any links within the relations div
        for link in rel_div.select("a[href*='/issues/']"):

            try:

                href = link.get("href", "")

                # Extract target issue ID
                match = re.search(r"/issues/(\d+)", href)

                if not match:
                    continue

                target_id = int(match.group(1))

                # Determine relation type from surrounding text
                parent = link.parent

                if parent:
                    text = parent.get_text(" ", strip=True).lower()
                else:
                    text = ""

                relation_type = self._detect_type(text)

                relation = Relation(
                    type=relation_type,
                    target_issue=target_id
                )

                relations.append(relation.to_dict())

            except Exception as e:
                logger.warning(
                    "Failed parsing relation: %s", e
                )

        logger.debug(
            "Parsed %d relations", len(relations)
        )

        return relations

    def _detect_type(self, text):
        """
        Detect the relation type from surrounding text.

        Args:
            text: Lowercase text surrounding the relation link.

        Returns:
            Normalized relation type string.
        """

        for keyword, rel_type in RELATION_MAP.items():
            if keyword in text:
                return rel_type

        return "RELATES"
