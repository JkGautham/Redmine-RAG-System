"""
Session Manager.

Handles authentication to Redmine via:
    1. Anonymous access (for public instances like redmine.org)
    2. Raw session cookie injection (for SSO/LDAP/MFA environments)
    3. Username/password login with CSRF token (for standard deployments)

Validates the session by checking the homepage for "Logged in as".
"""

import logging
from bs4 import BeautifulSoup
import requests

from config.settings import (
    AUTH_REQUIRED,
    BASE_URL,
    USERNAME,
    PASSWORD,
    SESSION_COOKIE,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger("redmine_scraper")


class SessionManager:

    def create_session(self):
        """
        Create and return a requests.Session.

        If AUTH_REQUIRED is False, returns an anonymous session
        (no login, no validation). Otherwise authenticates via
        cookie injection or username/password login.

        Returns:
            A requests.Session (authenticated or anonymous).

        Raises:
            Exception if authentication is required but fails.
        """

        session = requests.Session()

        session.timeout = REQUEST_TIMEOUT

        if not AUTH_REQUIRED:
            return self._create_anonymous_session(session)

        if SESSION_COOKIE:
            self._inject_cookie(session)
        else:
            self._login(session)

        self._validate_session(session)

        return session

    def _create_anonymous_session(self, session):
        """
        Return a plain session for public Redmine instances
        that do not require authentication.

        Performs a basic connectivity check against BASE_URL.
        """

        logger.info(
            "AUTH_REQUIRED is False — using anonymous access"
        )

        response = session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        logger.info(
            "Anonymous session created — connected to %s", BASE_URL
        )

        return session

    def _inject_cookie(self, session):
        """
        Inject a raw session cookie into the session.

        The cookie value should be the _redmine_session value
        from a browser.
        """

        logger.info("Using session cookie authentication")

        session.cookies.set(
            "_redmine_session",
            SESSION_COOKIE,
            domain=BASE_URL.split("//")[-1].split(":")[0],
        )

    def _login(self, session):
        """
        Login via username/password with CSRF token.

        Mimics the browser login flow:
            1. GET /login → extract CSRF token
            2. POST /login with username, password, CSRF
        """

        login_url = f"{BASE_URL}/login"

        logger.info("Logging in to %s", login_url)

        # Step 1: GET login page for CSRF token
        response = session.get(
            login_url,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        csrf_token = ""

        token_tag = soup.find(
            "meta",
            attrs={"name": "csrf-token"}
        )

        if token_tag:
            csrf_token = token_tag.get("content", "")

        # Step 2: POST login
        payload = {
            "username": USERNAME,
            "password": PASSWORD,
        }

        headers = {}

        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token

        response = session.post(
            login_url,
            data=payload,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
        )

        if "/login" in response.url.lower():
            raise Exception(
                "Login failed — check credentials or Redmine URL"
            )

        logger.info("Login successful")

    def _validate_session(self, session):
        """
        Validate that the session is authenticated.

        Checks the homepage for "Logged in as".
        """

        response = session.get(
            BASE_URL,
            timeout=REQUEST_TIMEOUT
        )

        if "Logged in as" not in response.text:
            raise Exception(
                "Session validation failed — "
                "not logged in after authentication"
            )

        logger.info("Session validated — authenticated")
