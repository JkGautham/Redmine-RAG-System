"""
Attachment Parser.

Extracts attachment metadata from:
    div.attachments table tr

Each row has:
    - <a class="icon icon-attachment"> → filename + URL
    - <span class="size"> → file size
    - Attachment ID extracted from URL: /attachments/NNNNN

Does NOT download files, run OCR, or generate embeddings.
Metadata only.
"""

import re
import logging

from models.attachment import Attachment

logger = logging.getLogger("redmine_scraper")


class AttachmentParser:

    def parse(self, soup):
        """
        Extract attachment metadata.

        Args:
            soup: BeautifulSoup of the issue page.

        Returns:
            List of Attachment dicts.
        """

        attachments = []

        attachments_div = soup.select_one("div.attachments")

        if not attachments_div:
            return attachments

        # Each attachment is in a <tr> inside the attachments table
        for row in attachments_div.select("table tr"):

            try:

                # Find the attachment link
                link = row.select_one("a.icon-attachment")

                if not link:
                    # Try alternative selector
                    link = row.select_one('a[icon="attachment"]')

                if not link:
                    continue

                href = link.get("href", "")

                # Extract filename from the link text
                # The filename is inside <span class="icon-label">
                label = link.select_one("span.icon-label")

                if label:
                    filename = label.get_text(strip=True)
                else:
                    filename = link.get_text(strip=True)

                # Extract attachment_id from URL
                # URL pattern: /attachments/10249
                attachment_id = None

                match = re.search(r"/attachments/(\d+)", href)

                if match:
                    attachment_id = int(match.group(1))

                # Extract file size
                size_span = row.select_one("span.size")

                size = ""

                if size_span:
                    size = size_span.get_text(strip=True)
                    # Clean up: "(3.83 KB)" → "3.83 KB"
                    size = size.strip("()")

                attachment = Attachment(
                    attachment_id=attachment_id,
                    filename=filename,
                    url=href,
                    size=size
                )

                attachments.append(attachment.to_dict())

            except Exception as e:
                logger.warning(
                    "Failed parsing attachment row: %s", e
                )

        logger.debug(
            "Parsed %d attachments", len(attachments)
        )

        return attachments
