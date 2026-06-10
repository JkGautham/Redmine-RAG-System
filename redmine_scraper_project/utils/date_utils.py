"""
Date parsing utilities for Redmine HTML timestamps.

Redmine uses formats like:
    05/21/2013 01:42 AM
    05/21/2013 07:39 AM
    06/27/2022 03:04 PM
"""

from datetime import datetime
from dateutil import parser as dateutil_parser


def parse_redmine_date(text):
    """
    Parse a Redmine date string into a datetime object.

    Handles multiple formats commonly found in Redmine HTML.
    Returns None if parsing fails.
    """

    if not text:
        return None

    text = text.strip()

    # Try common Redmine formats
    formats = [
        "%m/%d/%Y %I:%M %p",    # 05/21/2013 01:42 AM
        "%m/%d/%Y %H:%M",       # 05/21/2013 13:42
        "%Y-%m-%d %H:%M:%S",    # 2013-05-21 01:42:00
        "%Y-%m-%dT%H:%M:%S",    # 2013-05-21T01:42:00
        "%Y-%m-%d",             # 2013-05-21
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    # Fallback to dateutil
    try:
        return dateutil_parser.parse(text)
    except (ValueError, TypeError):
        return None


def format_run_timestamp(dt=None):
    """
    Generate a timestamped directory name.

    Format: YYYY-MM-DD_HH-MM-SS
    """

    if dt is None:
        dt = datetime.now()

    return dt.strftime("%Y-%m-%d_%H-%M-%S")


def to_iso(dt):
    """Convert a datetime to ISO 8601 string."""

    if dt is None:
        return None

    return dt.isoformat()
