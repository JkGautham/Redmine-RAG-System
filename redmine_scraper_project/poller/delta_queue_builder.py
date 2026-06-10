"""
Delta Queue Builder.

Builds a flat, serializable list of issue IDs to process
from the diff detector output.
"""

import logging

logger = logging.getLogger("redmine_scraper")


class DeltaQueueBuilder:

    def build(self, diff_result):
        """
        Build a processing queue from diff detector output.

        Args:
            diff_result: Dict with "new" and "modified" lists.

        Returns:
            List of issue IDs to process (serializable).
        """

        queue = []

        for issue in diff_result.get("new", []):
            issue_id = issue.get("issue_id")
            if issue_id and issue_id not in queue:
                queue.append(issue_id)

        for issue in diff_result.get("modified", []):
            issue_id = issue.get("issue_id")
            if issue_id and issue_id not in queue:
                queue.append(issue_id)

        logger.info(
            "Delta queue built: %d issues to process",
            len(queue)
        )

        return queue
