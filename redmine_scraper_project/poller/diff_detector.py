"""
Diff Detector.

Compares polled issues against the checkpoint to determine
which issues are new or modified.

Input:
    Issue list from poller
    Checkpoint timestamp

Output:
    {"new": [...], "modified": [...]}
"""

import logging

from utils.date_utils import parse_redmine_date

logger = logging.getLogger("redmine_scraper")


class DiffDetector:

    def detect(self, issues, checkpoint_timestamp):
        """
        Classify issues as new or modified relative to checkpoint.

        If no checkpoint exists, all issues are treated as new.

        Args:
            issues: List of issue dicts from the poller.
            checkpoint_timestamp: ISO string of last successful scrape,
                                  or None for first run.

        Returns:
            Dict with "new" and "modified" lists.
        """

        if not checkpoint_timestamp:
            logger.info(
                "No checkpoint — all %d issues classified as new",
                len(issues)
            )
            return {
                "new": issues,
                "modified": []
            }

        checkpoint_dt = parse_redmine_date(checkpoint_timestamp)

        new_issues = []
        modified_issues = []

        for issue in issues:

            updated = issue.get("updated_on")

            if not updated:
                # If we can't determine the date, treat as new
                new_issues.append(issue)
                continue

            issue_dt = parse_redmine_date(updated)

            if issue_dt and issue_dt > checkpoint_dt:
                modified_issues.append(issue)
            else:
                # Should not happen due to early-stop,
                # but treat as modified to be safe
                modified_issues.append(issue)

        logger.info(
            "Diff detected: %d new, %d modified",
            len(new_issues),
            len(modified_issues)
        )

        return {
            "new": new_issues,
            "modified": modified_issues
        }
