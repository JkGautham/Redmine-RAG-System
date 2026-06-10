"""
Logger setup for the Redmine Acquisition Layer.

Dual output: console + run.log file.
"""

import logging
import sys
from pathlib import Path


def setup_logger(run_dir=None, name="redmine_scraper"):
    """
    Configure logging to both console and log file.

    Args:
        run_dir: Path to the run output directory.
                 If provided, logs also go to run_dir/logs/run.log
        name: Logger name.

    Returns:
        Configured logger instance.
    """

    logger = logging.getLogger(name)

    # Avoid duplicate handlers on re-init
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler
    if run_dir:
        log_dir = Path(run_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(
            log_dir / "run.log",
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
