"""
When each repo last shipped to users.

Every platform releases differently, so each repo in repo_summary.REPOS names
the signal that best matches "users got a new version":

  sparkle      Mac: newest <item> pubDate in the Sparkle appcast the app polls.
               (GitHub Releases on Mac-App are per-build QA builds, not releases.)
  update_ini   Windows: Last-Modified of the update.ini the app polls.
  app_store    Mobile: currentVersionReleaseDate from the public App Store lookup
               API (iOS only; Google Play has no public equivalent).
  workflow     Web / backend / Linux: newest successful run of the deploy or
               package workflow(s).
  github       Latest GitHub Release, else the newest tag's commit date.

If the configured signal fails, the GitHub Release/tag fallback is used.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional

import requests

import github_api
from qa_metrics import UTC, parse_iso

SOURCE_SPARKLE = "sparkle"
SOURCE_UPDATE_INI = "update_ini"
SOURCE_APP_STORE = "app_store"
SOURCE_WORKFLOW = "workflow"
SOURCE_GITHUB = "github"

APP_STORE_LOOKUP_URL = "https://itunes.apple.com/lookup"
SPARKLE_NAMESPACE = "{http://www.andymatuschak.org/xml-namespaces/sparkle}"
UPDATE_INI_VERSION_KEY = "program_version"
WORKFLOW_SUCCESS = "success"
HTTP_TIMEOUT_SECONDS = 30

log = logging.getLogger("release_velocity")


@dataclass(frozen=True)
class Release:
    released_at: datetime
    version: str
    source: str


def parse_sparkle_appcast(xml_text: str) -> Optional[Release]:
    """The newest item in a Sparkle appcast."""
    channel = ElementTree.fromstring(xml_text).find("channel")
    if channel is None:
        return None
    newest: Optional[Release] = None
    for item in channel.findall("item"):
        published = _parse_http_date(item.findtext("pubDate"))
        if published is None:
            continue
        version = (item.findtext("title") or item.findtext(f"{SPARKLE_NAMESPACE}version") or "").strip()
        if newest is None or published > newest.released_at:
            newest = Release(published, version, "Sparkle appcast")
    return newest


def parse_update_ini_version(ini_text: str) -> str:
    for line in ini_text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == UPDATE_INI_VERSION_KEY:
            return value.strip()
    return ""


def parse_app_store_lookup(body: Dict[str, Any]) -> Optional[Release]:
    results = body.get("results") or []
    if not results:
        return None
    app = results[0]
    released = parse_iso(app.get("currentVersionReleaseDate"))
    if released is None:
        return None
    return Release(released, app.get("version") or "", "App Store (iOS)")


def _parse_http_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value.strip()).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _fetch_text(url: str) -> Optional[requests.Response]:
    response = github_api.request("GET", url, timeout=HTTP_TIMEOUT_SECONDS)
    if response.status_code != 200:
        log.warning("GET %s returned HTTP %d", url, response.status_code)
        return None
    return response


def fetch_sparkle(source: Dict[str, Any], repo_name: str) -> Optional[Release]:
    response = _fetch_text(source["url"])
    return parse_sparkle_appcast(response.text) if response is not None else None


def fetch_update_ini(source: Dict[str, Any], repo_name: str) -> Optional[Release]:
    response = _fetch_text(source["url"])
    if response is None:
        return None
    modified = _parse_http_date(response.headers.get("Last-Modified"))
    if modified is None:
        return None
    return Release(modified, parse_update_ini_version(response.text), "update.ini")


def fetch_app_store(source: Dict[str, Any], repo_name: str) -> Optional[Release]:
    response = github_api.request(
        "GET",
        APP_STORE_LOOKUP_URL,
        params={"id": source["app_id"], "country": source.get("country", "au")},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        log.warning("App Store lookup for %s returned HTTP %d", repo_name, response.status_code)
        return None
    return parse_app_store_lookup(response.json())


def fetch_workflow(source: Dict[str, Any], repo_name: str) -> Optional[Release]:
    """Newest successful run across the configured deploy workflows."""
    newest: Optional[Release] = None
    for workflow in source["workflows"]:
        params: Dict[str, Any] = {"status": WORKFLOW_SUCCESS, "per_page": 1}
        if source.get("branch"):
            params["branch"] = source["branch"]
        response = github_api.rest_get(f"/repos/{repo_name}/actions/workflows/{workflow}/runs", params)
        if response.status_code != 200:
            log.warning("Workflow runs for %s/%s returned HTTP %d", repo_name, workflow, response.status_code)
            continue
        runs = response.json().get("workflow_runs") or []
        if not runs:
            continue
        finished = parse_iso(runs[0].get("updated_at") or runs[0].get("created_at"))
        if finished and (newest is None or finished > newest.released_at):
            newest = Release(finished, runs[0].get("head_sha", "")[:7], source.get("label", workflow))
    return newest


def fetch_github_release(source: Optional[Dict[str, Any]], repo_name: str) -> Optional[Release]:
    response = github_api.rest_get(f"/repos/{repo_name}/releases/latest")
    if response.status_code == 200:
        data = response.json()
        published = parse_iso(data.get("published_at") or data.get("created_at"))
        if published:
            return Release(published, data.get("tag_name") or "", "GitHub release")
    return _fetch_latest_tag(repo_name)


def _fetch_latest_tag(repo_name: str) -> Optional[Release]:
    response = github_api.rest_get(f"/repos/{repo_name}/tags", {"per_page": 1})
    tags: List[Dict[str, Any]] = response.json() if response.status_code == 200 else []
    if not tags:
        return None
    commit_url = (tags[0].get("commit") or {}).get("url")
    if not commit_url:
        return None
    commit_response = github_api.rest_get(commit_url)
    if commit_response.status_code != 200:
        return None
    committed = parse_iso(((commit_response.json().get("commit") or {}).get("committer") or {}).get("date"))
    return Release(committed, tags[0].get("name", ""), "git tag") if committed else None


FETCHERS: Dict[str, Callable[[Dict[str, Any], str], Optional[Release]]] = {
    SOURCE_SPARKLE: fetch_sparkle,
    SOURCE_UPDATE_INI: fetch_update_ini,
    SOURCE_APP_STORE: fetch_app_store,
    SOURCE_WORKFLOW: fetch_workflow,
    SOURCE_GITHUB: fetch_github_release,
}


def fetch_last_release(repo_name: str, source: Optional[Dict[str, Any]]) -> Optional[Release]:
    kind = (source or {}).get("kind", SOURCE_GITHUB)
    try:
        release = FETCHERS[kind](source or {}, repo_name)
    except Exception as err:
        log.warning("Release lookup (%s) failed for %s: %s", kind, repo_name, err)
        release = None
    if release is None and kind != SOURCE_GITHUB:
        log.info("No %s release signal for %s; falling back to GitHub releases/tags", kind, repo_name)
        try:
            release = fetch_github_release(None, repo_name)
        except Exception as err:
            log.warning("GitHub release fallback failed for %s: %s", repo_name, err)
    return release
