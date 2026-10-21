#!/usr/bin/env python3
"""
Fetch repository summary metrics for the Focus Bear repositories and export
them to CSV (one file per time window) for the dashboard and the Cliq update.

Per repo:
  - Open PRs (split into draft / approved) and PRs merged in the window
  - QA progress from the repo's GitHub Projects v2 board: issues moved to QA
    passed / QA failed in the window, issues currently in Ready for QA, and
    the Ready for QA count 24 h and 7 days ago (for the trend)
  - Roadmap progress: issues moved into Ready for QA vs new issues (and new
    bug-labelled issues) filed in the window
  - Release velocity: days since the last release (see release_velocity.py)

Status history comes from the issues' ProjectV2ItemStatusChangedEvent timeline
events, so past Ready for QA counts are reconstructed rather than snapshotted.
"""

from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import github_api
import qa_metrics
from qa_metrics import UTC, StatusChange, parse_iso
from release_velocity import (
    SOURCE_APP_STORE,
    SOURCE_SPARKLE,
    SOURCE_UPDATE_INI,
    SOURCE_WORKFLOW,
    Release,
    fetch_last_release,
)

NOW_UTC = datetime.now(UTC)

GH_API_READ_TOKEN = github_api.GH_API_READ_TOKEN
GH_TOKEN = GH_API_READ_TOKEN  # backward compat alias

GH_ORG = "Focus-Bear"
STATUS_FIELD_NAME = "Status"
BUG_LABEL = "bug"

# Status option names on each board. Boards name their columns differently, so
# each repo lists its own. `passed_from` restricts a "passed" move to moves out
# of those statuses, for boards whose passed column is a generic Done column.
STANDARD_QA = {
    "ready": ["Ready for QA"],
    "passed": ["QA Passed/Done"],
    "failed": ["QA Failed"],
}

# Repositories to track. Each has its own board at
# https://github.com/orgs/Focus-Bear/projects/{project_number}.
# `qa` is None for boards with no QA columns. `release` picks the signal that
# best means "users got a new version" (see release_velocity.py).
REPOS: List[Dict[str, Any]] = [
    {
        "name": "Focus-Bear/web_dashboard",
        "display_name": "Web Dashboard",
        "short_name": "web_dashboard",
        "project_number": 6,
        "qa": {**STANDARD_QA, "ready": ["Ready for QA", "Ready for QA high priority"]},
        "release": {"kind": SOURCE_WORKFLOW, "workflows": ["s3-deployment-prod.yaml"], "branch": "main", "label": "prod deploy"},
    },
    {
        "name": "Focus-Bear/backend",
        "display_name": "Backend",
        "short_name": "backend",
        "project_number": 4,
        "qa": {"ready": ["Deployed awaiting QA"], "passed": ["QA'd"], "failed": []},
        "release": {
            "kind": SOURCE_WORKFLOW,
            "workflows": ["github-aws-prod-deployment.yaml", "github-aws-hotfix-deploy.yaml"],
            "label": "prod deploy",
        },
    },
    {
        "name": "Focus-Bear/mobile-app",
        "display_name": "Mobile",
        "short_name": "mobile-app",
        "project_number": 3,
        "qa": STANDARD_QA,
        "release": {"kind": SOURCE_APP_STORE, "app_id": "1673296334"},
    },
    {
        "name": "Focus-Bear/Mac-App",
        "display_name": "Mac",
        "short_name": "Mac-App",
        "project_number": 1,
        "qa": STANDARD_QA,
        "release": {"kind": SOURCE_SPARKLE, "url": "https://downloads.focusbear.io/update/mac/new/latest-version.xml"},
    },
    {
        "name": "Focus-Bear/windows-app-v2",
        "display_name": "Windows",
        "short_name": "windows-app-v2",
        "project_number": 5,
        "qa": STANDARD_QA,
        "release": {"kind": SOURCE_UPDATE_INI, "url": "https://downloads.focusbear.io/update/windows/update.ini"},
    },
    {
        "name": "Focus-Bear/Linux-App",
        "display_name": "Linux",
        "short_name": "Linux-App",
        "project_number": 45,
        "qa": {"ready": ["Ready for QA"], "passed": ["Done/Closed"], "failed": [], "passed_from": ["Ready for QA", "QA"]},
        "release": {"kind": SOURCE_WORKFLOW, "workflows": ["build-deb.yml"], "branch": "main", "label": ".deb build"},
    },
    {
        "name": "Focus-Bear/chrome_extension",
        "display_name": "Browser Extension",
        "short_name": "chrome_extension",
        "project_number": 43,
        "qa": None,
        "release": None,
    },
]

# Time periods (days) to generate dashboard CSVs for.
TIME_PERIODS = [7, 30]
# Windows reported in the Cliq update.
CLIQ_WINDOWS = [1, 7]
# How far back the Ready for QA count is compared, in days.
TREND_LOOKBACK_DAYS = [1, 7]
DEFAULT_REPORT_DAYS = 30

PROJECT_ITEMS_PAGE_SIZE = 100
TIMELINE_BATCH_SIZE = 50
TIMELINE_PAGE_SIZE = 100
GITHUB_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

CSV_FIELDNAMES = [
    "repo_name",
    "display_name",
    "prs_open",
    "prs_merged",
    "issues_ready_for_qa",
    "issues_qa_completed",
    "days_since_last_release",
    "fetched_at",
    # Added with the QA / roadmap / release metrics; appended so older readers
    # of the first eight columns keep working.
    "window_days",
    "prs_draft",
    "prs_approved",
    "issues_qa_failed",
    "issues_moved_to_ready_for_qa",
    "issues_created",
    "bugs_created",
    "ready_for_qa_1d_ago",
    "ready_for_qa_7d_ago",
    "last_release_at",
    "release_version",
    "release_source",
]

PROJECT_ITEMS_QUERY = """
query($org: String!, $project: Int!, $first: Int!, $after: String, $statusField: String!) {
  organization(login: $org) {
    projectV2(number: $project) {
      items(first: $first, after: $after) {
        nodes {
          createdAt
          updatedAt
          content {
            __typename
            ... on Issue { id number updatedAt }
          }
          fieldValueByName(name: $statusField) {
            ... on ProjectV2ItemFieldSingleSelectValue { name updatedAt }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

STATUS_EVENTS_QUERY = """
query($ids: [ID!]!, $since: DateTime!, $first: Int!) {
  nodes(ids: $ids) {
    ... on Issue {
      id
      timelineItems(first: $first, since: $since, itemTypes: [PROJECT_V2_ITEM_STATUS_CHANGED_EVENT]) {
        pageInfo { hasNextPage }
        nodes {
          ... on ProjectV2ItemStatusChangedEvent {
            createdAt
            previousStatus
            status
            project { number }
          }
        }
      }
    }
  }
}
"""

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("repo_summary")


@dataclass
class SummaryInputs:
    """Everything fetched from GitHub and the release feeds for one run."""

    fetched_at: datetime
    items_by_repo: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    counts_by_repo: Dict[str, Dict[str, int]] = field(default_factory=dict)
    releases_by_repo: Dict[str, Optional[Release]] = field(default_factory=dict)
    errors_by_repo: Dict[str, str] = field(default_factory=dict)


# ---------- Project boards ----------

def fetch_project_issues_for_repo(project_number: int) -> List[Dict[str, Any]]:
    """Every issue on a Projects v2 board with its current Status (see qa_metrics for the item shape)."""
    variables: Dict[str, Any] = {
        "org": GH_ORG,
        "project": project_number,
        "first": PROJECT_ITEMS_PAGE_SIZE,
        "after": None,
        "statusField": STATUS_FIELD_NAME,
    }
    items: List[Dict[str, Any]] = []
    while True:
        project = (github_api.graphql(PROJECT_ITEMS_QUERY, variables).get("organization") or {}).get("projectV2")
        if not project:
            raise github_api.GitHubError(
                f"Project {project_number} not visible — the token needs read:project (Projects: read)"
            )
        for node in project["items"]["nodes"]:
            item = _board_item(node)
            if item:
                items.append(item)
        page_info = project["items"]["pageInfo"]
        if not page_info["hasNextPage"]:
            return items
        variables["after"] = page_info["endCursor"]


def _board_item(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    content = node.get("content") or {}
    if content.get("__typename") != "Issue":
        return None
    status_value = node.get("fieldValueByName") or {}
    return {
        "id": content.get("id"),
        "number": content.get("number"),
        "updated_at": content.get("updatedAt"),
        "status": status_value.get("name"),
        "status_updated_at": parse_iso(status_value.get("updatedAt")),
        "item_created_at": parse_iso(node.get("createdAt")),
        "item_updated_at": parse_iso(node.get("updatedAt")),
        "events": None,
    }


def attach_status_events(items: List[Dict[str, Any]], project_number: int, since: datetime) -> None:
    """
    Fill in `events` for the items whose board entry changed after `since`,
    batching the timeline lookups. Items untouched since then keep events=None.
    """
    by_id = {
        item["id"]: item
        for item in items
        if item["id"] and item["item_updated_at"] and item["item_updated_at"] > since
    }
    ids = list(by_id)
    for start in range(0, len(ids), TIMELINE_BATCH_SIZE):
        data = github_api.graphql(
            STATUS_EVENTS_QUERY,
            {
                "ids": ids[start:start + TIMELINE_BATCH_SIZE],
                "since": since.strftime(GITHUB_DATETIME_FORMAT),
                "first": TIMELINE_PAGE_SIZE,
            },
        )
        for node in data.get("nodes") or []:
            if node and node.get("id") in by_id:
                by_id[node["id"]]["events"] = _status_changes(node, project_number)


def _status_changes(issue_node: Dict[str, Any], project_number: int) -> List[StatusChange]:
    timeline = issue_node.get("timelineItems") or {}
    if (timeline.get("pageInfo") or {}).get("hasNextPage"):
        log.warning("Issue %s has more than %d status changes in the window; later ones ignored",
                    issue_node.get("id"), TIMELINE_PAGE_SIZE)
    changes: List[StatusChange] = []
    for event in timeline.get("nodes") or []:
        at = parse_iso((event or {}).get("createdAt"))
        # An issue can sit on several boards; only this board's changes count.
        if at is None or (event.get("project") or {}).get("number") != project_number:
            continue
        changes.append(StatusChange(at, event.get("previousStatus") or None, event.get("status") or None))
    changes.sort(key=lambda change: change.at)
    return changes


def fetch_board(repo: Dict[str, Any], history_since: datetime) -> List[Dict[str, Any]]:
    items = fetch_project_issues_for_repo(repo["project_number"])
    if repo.get("qa"):
        attach_status_events(items, repo["project_number"], history_since)
    return items


# ---------- PR / issue counts (GitHub search, batched per repo) ----------

def count_queries(repo_name: str, windows: Sequence[int], now: datetime) -> Dict[str, str]:
    """GitHub search queries keyed by the count they produce."""
    repo = f"repo:{repo_name}"
    queries = {
        "prs_open": f"{repo} is:pr is:open",
        "prs_draft": f"{repo} is:pr is:open draft:true",
        "prs_approved": f"{repo} is:pr is:open review:approved",
    }
    for days in windows:
        since = (now - timedelta(days=days)).strftime(GITHUB_DATETIME_FORMAT)
        queries[f"prs_merged_{days}d"] = f"{repo} is:pr is:merged merged:>={since}"
        queries[f"issues_created_{days}d"] = f"{repo} is:issue created:>={since}"
        queries[f"bugs_created_{days}d"] = f"{repo} is:issue label:{BUG_LABEL} created:>={since}"
    return queries


def fetch_counts(repo_name: str, windows: Sequence[int], now: datetime) -> Dict[str, int]:
    """All of a repo's search counts in one GraphQL request."""
    queries = count_queries(repo_name, windows, now)
    aliases = {key: f"q{index}" for index, key in enumerate(queries)}
    declarations = ", ".join(f"${alias}: String!" for alias in aliases.values())
    selections = "\n".join(
        f"{alias}: search(type: ISSUE, query: ${alias}, first: 0) {{ issueCount }}" for alias in aliases.values()
    )
    data = github_api.graphql(
        f"query({declarations}) {{\n{selections}\n}}",
        {alias: queries[key] for key, alias in aliases.items()},
    )
    return {key: int((data.get(alias) or {}).get("issueCount") or 0) for key, alias in aliases.items()}


# ---------- Collection ----------

def collect_inputs(windows: Sequence[int], now: datetime = NOW_UTC) -> SummaryInputs:
    """Fetch boards, counts and releases for every repo once; every report is built from this."""
    history_since = now - timedelta(days=max(list(windows) + TREND_LOOKBACK_DAYS))
    inputs = SummaryInputs(fetched_at=now)
    for repo in REPOS:
        short_name = repo["short_name"]
        log.info("Fetching %s (board #%d)...", repo["name"], repo["project_number"])
        try:
            inputs.items_by_repo[short_name] = fetch_board(repo, history_since)
            inputs.counts_by_repo[short_name] = fetch_counts(repo["name"], windows, now)
        except Exception as err:
            log.error("Failed to fetch %s: %s", repo["name"], err)
            inputs.errors_by_repo[short_name] = str(err)
        inputs.releases_by_repo[short_name] = fetch_last_release(repo["name"], repo.get("release"))
        items = inputs.items_by_repo.get(short_name, [])
        log.info("  %d board issues, %d with status history", len(items),
                 sum(1 for item in items if item["events"] is not None))
    return inputs


# ---------- Reports ----------

def qa_row(items: List[Dict[str, Any]], qa: Optional[Dict[str, Any]], days: int, now: datetime) -> Dict[str, Optional[int]]:
    trend_keys = [f"ready_for_qa_{lookback}d_ago" for lookback in TREND_LOOKBACK_DAYS]
    if not qa:
        empty_keys = ["issues_ready_for_qa", "issues_qa_completed", "issues_qa_failed", "issues_moved_to_ready_for_qa"]
        return {key: None for key in empty_keys + trend_keys}
    since = now - timedelta(days=days)
    row: Dict[str, Optional[int]] = {
        "issues_ready_for_qa": qa_metrics.count_in_statuses_now(items, qa["ready"]),
        "issues_qa_completed": qa_metrics.count_moved_into(items, qa["passed"], since, qa.get("passed_from")),
        "issues_qa_failed": qa_metrics.count_moved_into(items, qa["failed"], since) if qa["failed"] else None,
        "issues_moved_to_ready_for_qa": qa_metrics.count_moved_into(items, qa["ready"], since),
    }
    for key, lookback in zip(trend_keys, TREND_LOOKBACK_DAYS):
        row[key] = qa_metrics.count_in_statuses_at(items, qa["ready"], now - timedelta(days=lookback))
    return row


def release_row(release: Optional[Release], now: datetime) -> Dict[str, Any]:
    if release is None:
        return {"days_since_last_release": None, "last_release_at": None, "release_version": None, "release_source": None}
    return {
        "days_since_last_release": qa_metrics.days_since(release.released_at, now),
        "last_release_at": release.released_at.isoformat(),
        "release_version": release.version,
        "release_source": release.source,
    }


def build_repo_row(repo: Dict[str, Any], days: int, inputs: SummaryInputs) -> Dict[str, Any]:
    short_name = repo["short_name"]
    counts = inputs.counts_by_repo.get(short_name, {})
    row: Dict[str, Any] = {
        "repo_name": repo["name"],
        "display_name": repo["display_name"],
        "window_days": days,
        "fetched_at": inputs.fetched_at.isoformat(),
        "prs_open": counts.get("prs_open", 0),
        "prs_draft": counts.get("prs_draft", 0),
        "prs_approved": counts.get("prs_approved", 0),
        "prs_merged": counts.get(f"prs_merged_{days}d", 0),
        "issues_created": counts.get(f"issues_created_{days}d", 0),
        "bugs_created": counts.get(f"bugs_created_{days}d", 0),
    }
    row.update(qa_row(inputs.items_by_repo.get(short_name, []), repo.get("qa"), days, inputs.fetched_at))
    row.update(release_row(inputs.releases_by_repo.get(short_name), inputs.fetched_at))
    if short_name in inputs.errors_by_repo:
        row["error"] = inputs.errors_by_repo[short_name]
    return row


def generate_report(lookback_days: int, inputs: SummaryInputs) -> List[Dict[str, Any]]:
    rows = [build_repo_row(repo, lookback_days, inputs) for repo in REPOS]
    for row in rows:
        log.info(
            "  %s (%dd): PRs open=%s, merged=%s, ready for QA=%s (1d ago %s, 7d ago %s), QA passed=%s, failed=%s, "
            "to QA=%s vs new=%s (bugs %s), days since release=%s",
            row["display_name"], lookback_days, row["prs_open"], row["prs_merged"], row["issues_ready_for_qa"],
            row["ready_for_qa_1d_ago"], row["ready_for_qa_7d_ago"], row["issues_qa_completed"],
            row["issues_qa_failed"], row["issues_moved_to_ready_for_qa"], row["issues_created"],
            row["bugs_created"], row["days_since_last_release"],
        )
    return rows


def _csv_value(value: Any) -> Any:
    # The dashboard's CSV reader splits on commas, so keep them out of values.
    if value is None:
        return ""
    return value.replace(",", " ") if isinstance(value, str) else value


def write_csv(results: List[Dict[str, Any]], output_file: str) -> None:
    with open(output_file, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            writer.writerow({key: _csv_value(row.get(key)) for key in CSV_FIELDNAMES})
    log.info("Exported repo summary to %s", output_file)


def log_totals(days: int, results: List[Dict[str, Any]]) -> None:
    log.info(
        "Totals (%dd): PRs open=%s, merged=%s, ready for QA=%s, QA passed=%s, to QA=%s vs new=%s",
        days,
        sum(row["prs_open"] for row in results),
        sum(row["prs_merged"] for row in results),
        qa_metrics.sum_optional(row["issues_ready_for_qa"] for row in results),
        qa_metrics.sum_optional(row["issues_qa_completed"] for row in results),
        qa_metrics.sum_optional(row["issues_moved_to_ready_for_qa"] for row in results),
        sum(row["issues_created"] for row in results),
    )


def is_cliq_configured() -> bool:
    return bool(os.getenv("CLIQ_WEBHOOK_TOKEN") or os.getenv("CLIQ_WEBHOOK_URL"))


def main() -> None:
    if not GH_TOKEN:
        log.warning("GH_API_READ_TOKEN not set. API rate limits will be very low.")

    windows = sorted(set(TIME_PERIODS + CLIQ_WINDOWS))
    inputs = collect_inputs(windows)

    reports: Dict[int, List[Dict[str, Any]]] = {}
    for days in windows:
        reports[days] = generate_report(days, inputs)
        log_totals(days, reports[days])
    for days in TIME_PERIODS:
        write_csv(reports[days], f"repo_summary_{days}d.csv")
    # repo_summary.csv (30 days) is kept for backward compatibility.
    write_csv(reports[DEFAULT_REPORT_DAYS], "repo_summary.csv")

    if not is_cliq_configured():
        log.info("CLIQ_WEBHOOK_TOKEN not set; skipping Cliq daily update.")
        return
    try:
        from cliq_notify import send_daily_update

        log.info("Sending daily update to Zoho Cliq...")
        send_daily_update(inputs=inputs, windows=CLIQ_WINDOWS, precomputed=reports)
    except Exception as err:
        log.error("Failed to send Cliq daily update: %s", err)


if __name__ == "__main__":
    main()
