"""
File system utilities.
"""

import json
from pathlib import Path


def ensure_dir(path):
    """Create directory and all parents if they don't exist."""

    Path(path).mkdir(parents=True, exist_ok=True)


def safe_write(path, content, encoding="utf-8"):
    """
    Write content to file safely.

    Creates parent directories if needed.
    """

    path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(content, encoding=encoding)


def safe_write_json(path, data):
    """Write JSON data to file safely with pretty formatting."""

    path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
