"""
Issue Poller.

Discovers issues from the Redmine issues list page.
Implements paginated traversal with early-stop.

Source URL:
    /issues?sort=updated_on:desc,id:desc&limit=100&page=N

The poller stops as soon as it encounters an issue whose
updated_on is <= the checkpoint timestamp (early-stop).
This yields O(changed issues) rather than O(total issues).
"""

import time
import logging
from bs4 import BeautifulSoup

from config.settings import (
    BASE_URL,
    ISSUES_LIST_URL,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
)
from utils.date_utils import parse_redmine_date

logger = logging.getLogger("redmine_scraper")


class IssuePoller:

    def poll(self, session, checkpoint_timestamp=None):
        """
        Poll all changed issues with early-stop.

        Args:
            session: Authenticated requests.Session.
            checkpoint_timestamp: ISO string of last successful scrape.
                                 None = full scan (first run).

        Returns:
            List of issue dicts discovered since checkpoint.
        """

        checkpoint_dt = None

        if checkpoint_timestamp:
            checkpoint_dt = parse_redmine_date(checkpoint_timestamp)
            logger.info(
                "Polling issues updated after %s",
                checkpoint_timestamp
            )
        else:
            logger.info("No checkpoint — full scan")

        all_issues = []
        page = 1
        stop = False

        while not stop:

            url = f"{ISSUES_LIST_URL}&page={page}"

            logger.info("Polling page %d: %s", page, url)

            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code != 200:
                logger.warning(
                    "Page %d returned status %d — stopping",
                    page,
                    response.status_code
                )
                break

            issues = self._parse_issue_list(response.text)

            if not issues:
                logger.info(
                    "No issues found on page %d — end of list",
                    page
                )
                break

            for issue in issues:

                # Early-stop check
                if checkpoint_dt and issue.get("updated_on"):

                    issue_dt = parse_redmine_date(
                        issue["updated_on"]
                    )

                    if issue_dt and issue_dt <= checkpoint_dt:
                        logger.info(
                            "Early stop: issue %d updated_on %s <= checkpoint %s",
                            issue["issue_id"],
                            issue["updated_on"],
                            checkpoint_timestamp
                        )
                        stop = True
                        break

                all_issues.append(issue)

            page += 1

            if not stop:
                time.sleep(REQUEST_DELAY)

        logger.info(
            "Polling complete: %d issues discovered",
            len(all_issues)
        )

        return all_issues

    def _parse_issue_list(self, html):
        """
        Parse one page of the issues list.

        Extracts from each <tr class="issue"> row:
            issue_id, issue_url, project, tracker,
            status, priority, subject, assignee, updated_on

        Selectors validated against real Redmine HTML.
        """

        soup = BeautifulSoup(html, "lxml")

        issues = []

        rows = soup.select("table.issues tbody tr")

        for row in rows:

            try:

                issue_link = row.select_one("td.id a")

                if not issue_link:
                    continue

                issue_id = int(issue_link.text.strip())

                href = issue_link.get("href", "")

                # Build full URL
                if href.startswith("/"):
                    issue_url = f"{BASE_URL}{href}"
                else:
                    issue_url = href

                project = self._safe_text(
                    row.select_one("td.project")
                )

                tracker = self._safe_text(
                    row.select_one("td.tracker")
                )

                status = self._safe_text(
                    row.select_one("td.status")
                )

                priority = self._safe_text(
                    row.select_one("td.priority")
                )

                subject = self._safe_text(
                    row.select_one("td.subject")
                )

                assignee = self._safe_text(
                    row.select_one("td.assigned_to")
                )

                updated_on = self._safe_text(
                    row.select_one("td.updated_on")
                )

                issues.append({
                    "issue_id": issue_id,
                    "issue_url": issue_url,
                    "project": project,
                    "tracker": tracker,
                    "status": status,
                    "priority": priority,
                    "subject": subject,
                    "assignee": assignee,
                    "updated_on": updated_on,
                })

            except Exception as e:
                logger.warning("Failed parsing issue row: %s", e)

        return issues

    def _safe_text(self, node):
        """Extract text from a node, or return empty string."""

        if node:
            return node.get_text(strip=True)

        return ""
