"""
Metadata Parser.

Extracts issue metadata from the DOM:
    - issue_id, tracker (from <h2>)
    - subject (from div.subject h3)
    - project (from h1 span.current-project)
    - status, priority, assignee, etc. (from div.attributes)
    - author, created_on, updated_on (from p.author)

DOM selectors validated against real Redmine HTML.
"""

import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger("redmine_scraper")


class MetadataParser:

    def parse(self, soup):
        """
        Extract metadata from the issue page.

        Args:
            soup: BeautifulSoup of the issue page.

        Returns:
            Dict with metadata fields.
        """

        metadata = {}

        # ------------------------------------------------
        # ISSUE ID + TRACKER from <h2>
        # e.g. "Feature #27933"
        # ------------------------------------------------

        h2 = soup.select_one("h2")

        if h2:
            h2_text = h2.get_text(strip=True)

            # Parse "Feature #27933" or "Bug #12345"
            match = re.match(
                r"(\w+)\s+#(\d+)",
                h2_text
            )

            if match:
                metadata["tracker"] = match.group(1)
                metadata["issue_id"] = int(match.group(2))

        # ------------------------------------------------
        # SUBJECT from div.subject h3
        # ------------------------------------------------

        subject = soup.select_one("div.subject h3")

        if subject:
            metadata["subject"] = subject.get_text(strip=True)

        # ------------------------------------------------
        # PROJECT from h1 span.current-project
        # ------------------------------------------------

        project = soup.select_one("h1 span.current-project")

        if project:
            metadata["project"] = project.get_text(strip=True)
        else:
            # Fallback: try h1 directly
            h1 = soup.select_one("h1")
            if h1:
                metadata["project"] = h1.get_text(strip=True)

        # ------------------------------------------------
        # ATTRIBUTES from div.attributes
        #
        # Structure:
        #   <div class="attribute">
        #       <div class="label">Status:</div>
        #       <div class="value">New</div>
        #   </div>
        # ------------------------------------------------

        attr_block = soup.select_one("div.attributes")

        if attr_block:

            for attr_div in attr_block.select("div.attribute"):

                label_el = attr_div.select_one("div.label")
                value_el = attr_div.select_one("div.value")

                if label_el and value_el:

                    label = label_el.get_text(strip=True)
                    label = label.rstrip(":")

                    value = value_el.get_text(strip=True)

                    # Map to canonical field names
                    label_lower = label.lower()

                    if label_lower == "status":
                        metadata["status"] = value

                    elif label_lower == "priority":
                        metadata["priority"] = value

                    elif label_lower in (
                        "assignee", "assigned to"
                    ):
                        metadata["assignee"] = value

                    elif label_lower == "start date":
                        metadata["start_date"] = value

                    elif label_lower == "due date":
                        metadata["due_date"] = value

                    elif label_lower in ("% done", "done ratio"):
                        metadata["done_ratio"] = value

                    elif label_lower == "estimated time":
                        metadata["estimated_time"] = value
                        
                    elif label_lower == "spent time":
                        metadata["spent_time"] = value
                        
                    elif label_lower == "category":
                        metadata["category"] = value
                        
                    elif label_lower == "target version":
                        metadata["target_version"] = value

        # ------------------------------------------------
        # AUTHOR + DATES from p.author
        #
        # "Added by Redmine Admin about 13 years ago.
        #  Updated about 13 years ago."
        #
        # The actual dates are in <a title="..."> tags:
        #   <a title="05/21/2013 01:42 AM">about 13 years</a>
        # ------------------------------------------------

        author_p = soup.select_one("p.author")

        if author_p:

            # Author name from user link
            author_link = author_p.select_one("a.user")

            if author_link:
                metadata["author"] = author_link.get_text(
                    strip=True
                )

            # Extract dates from <a title="..."> tags
            date_links = author_p.select("a[title]")

            if len(date_links) >= 1:
                metadata["created_on"] = (
                    date_links[0].get("title", "")
                )

            if len(date_links) >= 2:
                metadata["updated_on"] = (
                    date_links[1].get("title", "")
                )

        return metadata
