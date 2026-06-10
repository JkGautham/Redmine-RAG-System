"""
Custom Field Parser.

Dynamically discovers custom fields from the issue attributes.

Custom fields in Redmine are rendered the same way as standard
attributes (div.attribute with label/value), but have names
that don't match the known standard fields.

Never hardcodes field names — discovers them dynamically.

Output:
    {"custom_fields": {"Environment": "Production", "Severity": "Critical"}}
"""

import logging

logger = logging.getLogger("redmine_scraper")

# Standard Redmine attribute labels (case-insensitive)
# These are NOT custom fields.
STANDARD_FIELDS = {
    "status",
    "priority",
    "assignee",
    "assigned to",
    "start date",
    "due date",
    "% done",
    "estimated time",
    "target version",
    "category",
    "done ratio",
    "spent time",
}


class CustomFieldParser:

    def parse(self, soup):
        """
        Discover and extract custom fields.

        Args:
            soup: BeautifulSoup of the issue page.

        Returns:
            Dict of custom field name → value.
        """

        custom_fields = {}

        attr_block = soup.select_one("div.attributes")

        if not attr_block:
            return custom_fields

        for attr_div in attr_block.select("div.attribute"):

            label_el = attr_div.select_one("div.label")
            value_el = attr_div.select_one("div.value")

            if not label_el or not value_el:
                continue

            label = label_el.get_text(strip=True).rstrip(":")
            value = value_el.get_text(strip=True)

            # Skip standard fields
            if label.lower() in STANDARD_FIELDS:
                continue

            # Skip empty values
            if not value or value == "-":
                continue

            custom_fields[label] = value

        logger.debug(
            "Parsed %d custom fields: %s",
            len(custom_fields),
            list(custom_fields.keys())
        )

        return custom_fields
