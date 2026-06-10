"""
Issue Parser — Master Orchestrator.

Calls all sub-parsers to produce the canonical Issue JSON.

Input: raw HTML string
Output: Issue model with all fields populated

Wraps individual parser errors gracefully —
a failure in one parser does not prevent other parsers from running.
"""

import logging
from bs4 import BeautifulSoup

from models.issue import Issue
from parser.metadata_parser import MetadataParser
from parser.description_parser import DescriptionParser
from parser.attachment_parser import AttachmentParser
from parser.relation_parser import RelationParser
from parser.journal_parser import JournalParser
from parser.wiki_parser import WikiParser
from parser.custom_field_parser import CustomFieldParser

logger = logging.getLogger("redmine_scraper")


class IssueParser:

    def __init__(self):
        self.metadata_parser = MetadataParser()
        self.description_parser = DescriptionParser()
        self.attachment_parser = AttachmentParser()
        self.relation_parser = RelationParser()
        self.journal_parser = JournalParser()
        self.wiki_parser = WikiParser()
        self.custom_field_parser = CustomFieldParser()

    def parse(self, html, issue_id=None):
        """
        Parse raw HTML into a canonical Issue.

        Args:
            html: Raw HTML string of the issue page.
            issue_id: Optional issue ID (used as fallback).

        Returns:
            Dict matching the canonical JSON schema.
        """

        soup = BeautifulSoup(html, "lxml")

        issue = Issue()

        # If issue_id provided, set it as default
        if issue_id:
            issue.issue_id = issue_id

        # ------------------------------------------------
        # METADATA
        # ------------------------------------------------

        try:
            metadata = self.metadata_parser.parse(soup)

            issue.issue_id = metadata.get(
                "issue_id", issue.issue_id
            )
            issue.tracker = metadata.get("tracker", "")
            issue.subject = metadata.get("subject", "")
            issue.project = metadata.get("project", "")
            issue.status = metadata.get("status", "")
            issue.priority = metadata.get("priority", "")
            issue.author = metadata.get("author", "")
            issue.assignee = metadata.get("assignee", "")
            
            issue.category = metadata.get("category", "")
            issue.target_version = metadata.get("target_version", "")
            
            issue.start_date = metadata.get("start_date", "")
            issue.due_date = metadata.get("due_date", "")
            issue.done_ratio = metadata.get("done_ratio", "")
            issue.estimated_time = metadata.get("estimated_time", "")
            issue.spent_time = metadata.get("spent_time", "")

            issue.created_on = metadata.get("created_on", "")
            issue.updated_on = metadata.get("updated_on", "")

        except Exception as e:
            logger.warning(
                "Metadata parser failed for issue %s: %s",
                issue_id, e
            )

        # ------------------------------------------------
        # DESCRIPTION
        # ------------------------------------------------

        try:
            issue.description = self.description_parser.parse(soup)
        except Exception as e:
            logger.warning(
                "Description parser failed for issue %s: %s",
                issue.issue_id, e
            )

        # ------------------------------------------------
        # CUSTOM FIELDS
        # ------------------------------------------------

        try:
            issue.custom_fields = self.custom_field_parser.parse(soup)
        except Exception as e:
            logger.warning(
                "Custom field parser failed for issue %s: %s",
                issue.issue_id, e
            )

        # ------------------------------------------------
        # ATTACHMENTS
        # ------------------------------------------------

        try:
            issue.attachments = self.attachment_parser.parse(soup)
        except Exception as e:
            logger.warning(
                "Attachment parser failed for issue %s: %s",
                issue.issue_id, e
            )

        # ------------------------------------------------
        # RELATIONS
        # ------------------------------------------------

        try:
            issue.relations = self.relation_parser.parse(soup)
        except Exception as e:
            logger.warning(
                "Relation parser failed for issue %s: %s",
                issue.issue_id, e
            )

        # ------------------------------------------------
        # JOURNALS
        # ------------------------------------------------

        try:
            issue.journals = self.journal_parser.parse(soup)
        except Exception as e:
            logger.warning(
                "Journal parser failed for issue %s: %s",
                issue.issue_id, e
            )

        # ------------------------------------------------
        # WIKI LINKS
        # ------------------------------------------------

        try:
            issue.wiki_links = self.wiki_parser.parse(soup)
        except Exception as e:
            logger.warning(
                "Wiki parser failed for issue %s: %s",
                issue.issue_id, e
            )

        logger.debug(
            "Parsed issue %s: %s",
            issue.issue_id,
            issue.subject
        )

        return issue.to_dict()
