"""
Redmine Acquisition Layer — Main Entry Point.

Orchestrates the full ingestion pipeline:

    1. Load settings
    2. Create timestamped run directory
    3. Setup logger
    4. Load checkpoint
    5. Create session (login)
    6. Poll issues (with early-stop)
    7. Detect diffs against checkpoint
    8. Build delta queue
    9. For each issue in queue:
        a. Fetch HTML
        b. Save raw HTML
        c. Parse HTML → Issue model
        d. Save parsed JSON
        e. Log progress
        f. Handle single-issue failures (log & continue)
    10. Save run metadata
    11. Update checkpoint (only on success)
"""

import sys
import time
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import OUTPUT_DIR
from utils.logger import setup_logger
from utils.date_utils import format_run_timestamp, to_iso
from utils.file_utils import ensure_dir
from checkpoint.checkpoint_manager import CheckpointManager
from session.session_manager import SessionManager
from poller.issue_poller import IssuePoller
from poller.diff_detector import DiffDetector
from poller.delta_queue_builder import DeltaQueueBuilder
from fetcher.html_fetcher import HTMLFetcher
from parser.issue_parser import IssueParser
from storage.raw_html_writer import RawHTMLWriter
from storage.json_writer import JSONWriter
from storage.metadata_writer import MetadataWriter


def main():
    """Run the full Redmine acquisition pipeline."""

    start_time = time.time()

    # ========================================================
    # 1. CREATE RUN DIRECTORY
    # ========================================================

    run_id = format_run_timestamp()
    run_dir = OUTPUT_DIR / run_id

    ensure_dir(run_dir / "raw_html")
    ensure_dir(run_dir / "parsed_json")
    ensure_dir(run_dir / "logs")

    # ========================================================
    # 2. SETUP LOGGER
    # ========================================================

    logger = setup_logger(run_dir)

    logger.info("=" * 60)
    logger.info("REDMINE ACQUISITION LAYER")
    logger.info("Run ID: %s", run_id)
    logger.info("Run directory: %s", run_dir)
    logger.info("=" * 60)

    # ========================================================
    # 3. LOAD CHECKPOINT
    # ========================================================

    checkpoint_mgr = CheckpointManager()

    checkpoint = checkpoint_mgr.load_checkpoint()

    checkpoint_timestamp = None

    if checkpoint:
        checkpoint_timestamp = checkpoint.get(
            "last_successful_scrape"
        )

    # ========================================================
    # 4. CREATE SESSION (LOGIN)
    # ========================================================

    try:
        session_mgr = SessionManager()
        session = session_mgr.create_session()
    except Exception as e:
        logger.error("Session creation failed: %s", e)
        return

    # ========================================================
    # 5. POLL ISSUES
    # ========================================================

    poller = IssuePoller()

    issues = poller.poll(session, checkpoint_timestamp)

    issues_discovered = len(issues)

    if issues_discovered == 0:
        logger.info("No new or modified issues found — nothing to do")

        # Still save run metadata
        _save_metadata(
            run_dir, run_id, start_time,
            issues_discovered=0,
            issues_fetched=0,
            issues_parsed=0,
            attachments_found=0
        )
        return

    # ========================================================
    # 6. DETECT DIFFS
    # ========================================================

    diff_detector = DiffDetector()

    diff_result = diff_detector.detect(issues, checkpoint_timestamp)

    # ========================================================
    # 7. BUILD DELTA QUEUE
    # ========================================================

    queue_builder = DeltaQueueBuilder()

    queue = queue_builder.build(diff_result)

    if not queue:
        logger.info("Delta queue is empty — nothing to process")
        return

    # ========================================================
    # 8. PROCESS EACH ISSUE
    # ========================================================

    fetcher = HTMLFetcher()
    parser = IssueParser()
    html_writer = RawHTMLWriter()
    json_writer = JSONWriter()

    issues_fetched = 0
    issues_parsed = 0
    total_attachments = 0
    failed_issues = []

    for i, issue_id in enumerate(queue, 1):

        logger.info(
            "[%d/%d] Processing issue %d",
            i, len(queue), issue_id
        )

        try:

            # a. Fetch HTML
            html = fetcher.fetch(session, issue_id)

            issues_fetched += 1

            # b. Save raw HTML
            html_writer.save(run_dir, issue_id, html)

            # c. Parse HTML
            issue_data = parser.parse(html, issue_id=issue_id)

            issues_parsed += 1

            # Count attachments
            attachments = issue_data.get("attachments", [])
            total_attachments += len(attachments)

            # d. Save parsed JSON
            json_writer.save(run_dir, issue_id, issue_data)

            logger.info(
                "  ✓ Issue %d: %s | %d attachments | %d journals",
                issue_id,
                issue_data.get("subject", "?")[:50],
                len(attachments),
                len(issue_data.get("journals", []))
            )

        except Exception as e:

            # Single issue failures must NOT stop the run
            logger.error(
                "  ✗ Issue %d FAILED: %s", issue_id, e
            )
            failed_issues.append(issue_id)

    # ========================================================
    # 9. SAVE RUN METADATA
    # ========================================================

    _save_metadata(
        run_dir, run_id, start_time,
        issues_discovered=issues_discovered,
        issues_fetched=issues_fetched,
        issues_parsed=issues_parsed,
        attachments_found=total_attachments,
        failed_issues=failed_issues
    )

    # ========================================================
    # 10. UPDATE CHECKPOINT
    # ========================================================

    # Checkpoint must not advance if ingestion fails
    if issues_parsed > 0:

        checkpoint_mgr.save_checkpoint(
            last_scrape=to_iso(datetime.now()),
            issues_processed=issues_parsed,
            run_id=run_id
        )

    else:
        logger.warning(
            "No issues were successfully parsed — "
            "checkpoint NOT updated"
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    duration = time.time() - start_time

    logger.info("=" * 60)
    logger.info("RUN COMPLETE")
    logger.info("  Discovered: %d", issues_discovered)
    logger.info("  Fetched:    %d", issues_fetched)
    logger.info("  Parsed:     %d", issues_parsed)
    logger.info("  Attachments:%d", total_attachments)
    logger.info("  Failed:     %d", len(failed_issues))
    logger.info("  Duration:   %.1f seconds", duration)
    logger.info("=" * 60)

    if failed_issues:
        logger.warning(
            "Failed issues: %s", failed_issues
        )


def _save_metadata(
    run_dir, run_id, start_time,
    issues_discovered, issues_fetched,
    issues_parsed, attachments_found,
    failed_issues=None
):
    """Save run metadata to the output directory."""

    duration = time.time() - start_time

    metadata = {
        "run_timestamp": run_id,
        "issues_discovered": issues_discovered,
        "issues_fetched": issues_fetched,
        "issues_parsed": issues_parsed,
        "attachments_found": attachments_found,
        "duration_seconds": round(duration, 1),
    }

    if failed_issues:
        metadata["failed_issues"] = failed_issues

    writer = MetadataWriter()
    writer.save(run_dir, metadata)


if __name__ == "__main__":
    main()
