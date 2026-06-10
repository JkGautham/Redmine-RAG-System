"""
Configuration settings for the Redmine Acquisition Layer.

All settings can be overridden via environment variables.
"""

import os
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_DIR = BASE_DIR / "output"

CHECKPOINT_DIR = BASE_DIR / "checkpoint"

CHECKPOINT_FILE = CHECKPOINT_DIR / "checkpoint.json"


# ============================================================
# REDMINE CONNECTION
# ============================================================

BASE_URL = os.environ.get(
    "REDMINE_URL",
    "https://www.redmine.org"
).rstrip("/")

USERNAME = os.environ.get(
    "REDMINE_USERNAME",
    "admin"
)

PASSWORD = os.environ.get(
    "REDMINE_PASSWORD",
    "gauth294"
)

# Optional: inject a raw session cookie for SSO/LDAP environments
# If set, username/password login is skipped
SESSION_COOKIE = os.environ.get(
    "REDMINE_SESSION_COOKIE",
    ""
)

# Set to True when the Redmine instance requires authentication.
# Public instances (e.g. redmine.org) can be scraped without login.
AUTH_REQUIRED = os.environ.get(
    "REDMINE_AUTH_REQUIRED",
    "false"
).strip().lower() in ("true", "1", "yes")


# ============================================================
# REQUEST PARAMETERS
# ============================================================

REQUEST_DELAY = float(os.environ.get(
    "REDMINE_REQUEST_DELAY",
    "0.2"
))

REQUEST_TIMEOUT = int(os.environ.get(
    "REDMINE_REQUEST_TIMEOUT",
    "30"
))

ISSUES_PER_PAGE = int(os.environ.get(
    "REDMINE_ISSUES_PER_PAGE",
    "100"
))


# ============================================================
# ISSUE LIST URL
# ============================================================

ISSUES_LIST_URL = (
    f"{BASE_URL}/issues"
    f"?set_filter=1&f[]=status_id&op[status_id]=*"
    f"&sort=updated_on:desc,id:desc"
    f"&limit={ISSUES_PER_PAGE}"
)
