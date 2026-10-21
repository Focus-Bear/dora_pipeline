"""
Small GitHub REST + GraphQL client shared by repo_summary.py and
release_velocity.py, with rate-limit handling.

Authenticates with GH_API_READ_TOKEN. Projects v2 boards need the token to have
`read:project` (classic PAT) or org "Projects: read" (fine-grained PAT).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import requests

BASE_GH = "https://api.github.com"
BASE_GH_GRAPHQL = "https://api.github.com/graphql"

GH_API_READ_TOKEN = os.getenv("GH_API_READ_TOKEN") or ""

REQUEST_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 6
INITIAL_BACKOFF_SECONDS = 2.0
BACKOFF_MULTIPLIER = 2.0
# Never park the daily job for longer than this waiting on a rate-limit reset.
MAX_RATE_LIMIT_SLEEP_SECONDS = 15 * 60
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
GRAPHQL_RATE_LIMITED = "RATE_LIMITED"

log = logging.getLogger("github_api")


class GitHubError(RuntimeError):
    pass


def rest_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GH_API_READ_TOKEN:
        headers["Authorization"] = f"Bearer {GH_API_READ_TOKEN}"
    return headers


def _rate_limit_wait_seconds(response: requests.Response) -> Optional[float]:
    """Seconds to wait before retrying a rate-limited response, or None if it is not one."""
    retry_after = response.headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return float(retry_after)
    if response.headers.get("X-RateLimit-Remaining") == "0":
        reset = response.headers.get("X-RateLimit-Reset", "")
        if reset.isdigit():
            return max(0.0, int(reset) - time.time()) + 1
    return None


def _sleep(seconds: float, reason: str) -> None:
    capped = min(seconds, MAX_RATE_LIMIT_SLEEP_SECONDS)
    log.warning("%s; sleeping %.0fs", reason, capped)
    time.sleep(capped)


def request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Send a request, retrying on rate limits and transient server errors."""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT_SECONDS)
    backoff = INITIAL_BACKOFF_SECONDS
    response: Optional[requests.Response] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.request(method, url, **kwargs)
        except requests.RequestException as err:
            if attempt == MAX_ATTEMPTS:
                raise
            _sleep(backoff, f"{method} {url} failed ({err})")
            backoff *= BACKOFF_MULTIPLIER
            continue

        if response.status_code in (403, 429):
            wait = _rate_limit_wait_seconds(response)
            if wait is not None and attempt < MAX_ATTEMPTS:
                _sleep(wait, f"Rate limited on {url}")
                continue
        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS:
            _sleep(backoff, f"HTTP {response.status_code} from {url}")
            backoff *= BACKOFF_MULTIPLIER
            continue
        return response
    assert response is not None
    return response


def rest_get(path_or_url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    url = path_or_url if path_or_url.startswith("http") else f"{BASE_GH}{path_or_url}"
    return request("GET", url, headers=rest_headers(), params=params)


def graphql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run a GraphQL query and return its `data`, retrying when rate limited."""
    if not GH_API_READ_TOKEN:
        raise GitHubError("GH_API_READ_TOKEN is not set")
    payload = {"query": query, "variables": variables or {}}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = request("POST", BASE_GH_GRAPHQL, headers=rest_headers(), json=payload)
        if response.status_code != 200:
            raise GitHubError(f"GraphQL HTTP {response.status_code}: {response.text[:300]}")
        body = response.json()
        errors = body.get("errors") or []
        if any(error.get("type") == GRAPHQL_RATE_LIMITED for error in errors) and attempt < MAX_ATTEMPTS:
            _sleep(_rate_limit_wait_seconds(response) or INITIAL_BACKOFF_SECONDS * attempt, "GraphQL rate limited")
            continue
        if errors and not body.get("data"):
            raise GitHubError(f"GraphQL errors: {errors}")
        if errors:
            log.warning("GraphQL returned partial data with errors: %s", errors)
        return body["data"]
    raise GitHubError("GraphQL rate limit retries exhausted")
