"""
Stage 2d: Live HTML Fallback

Used ONLY when: a specific issue ID is requested AND query complexity is "simple".
Fetches real-time data from Redmine — not stored permanently.
"""

import requests
from bs4 import BeautifulSoup
from config import REDMINE_BASE_URL, REDMINE_SESSION_COOKIE


def _get_cookies() -> dict:
    if REDMINE_SESSION_COOKIE:
        return {"_redmine_session": REDMINE_SESSION_COOKIE}
    return {}


def fetch_issue_html(issue_id: int) -> dict:
    """
    Fetch and parse a single Redmine issue page.
    Returns clean structured dict — no raw HTML stored.
    """
    url = f"{REDMINE_BASE_URL}/issues/{issue_id}"
    try:
        resp = requests.get(url, cookies=_get_cookies(), timeout=15)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}", "issue_id": issue_id}
        return _parse_issue_html(resp.text, issue_id)
    except Exception as e:
        return {"error": str(e), "issue_id": issue_id}


def _parse_issue_html(html: str, issue_id: int) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    def text(selector):
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else ""

    subject  = text("h3.issue-subject") or text(".subject h3")
    status   = text(".status .value")
    priority = text(".priority .value")
    tracker  = text(".tracker .value")
    author   = text(".author .value a") or text(".author a")
    created  = text(".created-on .value")
    desc     = text("#issue_description_wiki")

    journals = []
    for note in soup.select(".journal"):
        author_el = note.select_one(".user a") or note.select_one(".user")
        date_el   = note.select_one(".created_on")
        body_el   = note.select_one(".wiki")
        journals.append({
            "author":     author_el.get_text(strip=True) if author_el else "",
            "created_on": date_el.get_text(strip=True)   if date_el   else "",
            "note":       body_el.get_text(strip=True)   if body_el   else ""
        })

    return {
        "issue_id":    issue_id,
        "subject":     subject,
        "status":      status,
        "priority":    priority,
        "tracker":     tracker,
        "author":      author,
        "created_on":  created,
        "description": desc,
        "journals":    journals,
        "source":      "live_html"
    }
