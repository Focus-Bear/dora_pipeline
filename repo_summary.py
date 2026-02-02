#!/usr/bin/env python3
"""
Fetch repository summary metrics (PRs opened, PRs merged, issues ready for QA, issues QA completed)
for multiple Focus Bear repositories and export to CSV.

QA stats are fetched from GitHub Project V2 board using GraphQL API.
Generates separate CSV files for different time periods (7 days and 30 days).
"""

import os
import csv
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

UTC = timezone.utc
NOW_UTC = datetime.now(UTC)

# GitHub token from environment
GH_TOKEN = os.getenv("GH_TOKEN") or ""

# Repositories to track (with their display names and project board numbers)
# Each repo has its own project board at https://github.com/orgs/Focus-Bear/projects/{project_number}
REPOS = [
    {"name": "Focus-Bear/web_dashboard", "display_name": "Web Dashboard", "short_name": "web_dashboard", "project_number": 6},
    {"name": "Focus-Bear/backend", "display_name": "Backend", "short_name": "backend", "project_number": 4},
    {"name": "Focus-Bear/mobile-app", "display_name": "Mobile", "short_name": "mobile-app", "project_number": 3},
    {"name": "Focus-Bear/Mac-App", "display_name": "Mac", "short_name": "Mac-App", "project_number": 1},
    {"name": "Focus-Bear/windows-app-v2", "display_name": "Windows", "short_name": "windows-app-v2", "project_number": 5},
]

# GitHub organization
GH_ORG = "Focus-Bear"

# QA status field values in the project board
# "Ready for QA" shows total count of issues in these statuses (no time filtering)
QA_READY_STATUSES = ["Ready for QA", "Deployed awaiting QA", "In Review"]
# "QA Completed" shows issues moved to these statuses within the time period
QA_COMPLETED_STATUSES = ["QA'd", "QA Passed", "Done"]

# Time periods to generate reports for
TIME_PERIODS = [7, 30]

BASE_GH = "https://api.github.com"
BASE_GH_GRAPHQL = "https://api.github.com/graphql"

# Logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("repo_summary")


def get_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }
    if GH_TOKEN:
        headers["Authorization"] = f"token {GH_TOKEN}"
    return headers


def get_graphql_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def gh_get_paged(url: str, params: Optional[Dict[str, Any]] = None, cap_pages: int = 10) -> List[Any]:
    """Fetch paginated GitHub API results."""
    out: List[Any] = []
    page = 1
    params = dict(params or {})
    headers = get_headers()
    
    while page <= cap_pages:
        params.update({"per_page": 100, "page": page})
        r = requests.get(url, headers=headers, params=params)
        if r.status_code == 403:
            log.warning("Rate limited or access denied for %s", url)
            break
        r.raise_for_status()
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def fetch_project_issues_for_repo(project_number: int, repo_short_name: str) -> List[Dict[str, Any]]:
    """
    Fetch all issues from a specific GitHub Project V2 board using GraphQL API.
    Returns a list of issues with their statuses and updated_at.
    """
    if not GH_TOKEN:
        log.warning("GH_TOKEN not set, cannot fetch project issues")
        return []

    query = """
    query($org: String!, $project: Int!, $first: Int!, $after: String) {
      organization(login: $org) {
        projectV2(number: $project) {
          title
          items(first: $first, after: $after) {
            nodes {
              content {
                __typename
                ... on Issue {
                  number
                  title
                  updatedAt
                  repository {
                    name
                    nameWithOwner
                  }
                }
              }
              fieldValues(first: 20) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    updatedAt
                  }
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
      }
    }
    """

    headers = get_graphql_headers()
    variables = {"org": GH_ORG, "project": project_number, "first": 100, "after": None}
    
    issues: List[Dict[str, Any]] = []
    
    while True:
        r = requests.post(BASE_GH_GRAPHQL, headers=headers, json={"query": query, "variables": variables})
        if r.status_code != 200:
            log.error("GraphQL request failed for project %d: %s - %s", project_number, r.status_code, r.text)
            break
        
        data = r.json()
        if "errors" in data:
            log.error("GraphQL errors for project %d: %s", project_number, data["errors"])
            break
            
        project = data.get("data", {}).get("organization", {}).get("projectV2")
        if not project:
            log.warning("No project found for org=%s, project=%d", GH_ORG, project_number)
            break

        for item in project["items"]["nodes"]:
            content = item.get("content")
            if not content or content.get("__typename") != "Issue":
                continue
                
            issue_number = content.get("number")
            issue_updated_at = content.get("updatedAt")
            
            # Get the status from field values
            status = None
            status_updated_at = None
            for fv in item.get("fieldValues", {}).get("nodes", []):
                if fv and fv.get("name"):
                    status = fv.get("name")
                    status_updated_at = fv.get("updatedAt")
            
            if issue_number:
                issues.append({
                    "number": issue_number,
                    "status": status,
                    "updated_at": issue_updated_at,
                    "status_updated_at": status_updated_at,
                })

        page_info = project["items"]["pageInfo"]
        if page_info["hasNextPage"]:
            variables["after"] = page_info["endCursor"]
        else:
            break
    
    return issues


def fetch_all_project_issues() -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch issues from all repo-specific GitHub Project V2 boards.
    Returns a dict mapping repo short name to list of issues with their statuses and updated_at.
    """
    issues_by_repo: Dict[str, List[Dict[str, Any]]] = {}
    
    for repo in REPOS:
        short_name = repo["short_name"]
        project_number = repo["project_number"]
        
        log.info("Fetching issues from project #%d for %s...", project_number, short_name)
        issues = fetch_project_issues_for_repo(project_number, short_name)
        issues_by_repo[short_name] = issues
        log.info("  Found %d issues for %s", len(issues), short_name)
    
    return issues_by_repo


def fetch_repo_pr_metrics(repo_name: str, lookback_days: int) -> Dict[str, int]:
    """Fetch PR metrics for a single repository within the lookback period."""
    cutoff_date = NOW_UTC - timedelta(days=lookback_days)
    
    # Fetch PRs
    prs = gh_get_paged(f"{BASE_GH}/repos/{repo_name}/pulls", params={"state": "all"})
    
    # Filter PRs created in the lookback period
    recent_prs = [
        pr for pr in prs
        if pr.get("created_at") and datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00")) >= cutoff_date
    ]
    
    prs_opened = len(recent_prs)
    
    # Filter PRs merged in the lookback period (by merge date, not creation date)
    prs_merged = len([
        pr for pr in prs
        if pr.get("merged_at") and datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00")) >= cutoff_date
    ])
    
    return {
        "prs_opened": prs_opened,
        "prs_merged": prs_merged,
    }


def count_qa_issues(issues: List[Dict[str, Any]], lookback_days: int) -> Dict[str, int]:
    """
    Count issues by QA status.
    
    - Ready for QA: Total count of issues currently in QA_READY_STATUSES (no time filtering)
    - QA Completed: Issues moved to QA_COMPLETED_STATUSES within the lookback period
    """
    cutoff_date = NOW_UTC - timedelta(days=lookback_days)
    
    issues_ready_for_qa = 0
    issues_qa_completed = 0
    
    for issue in issues:
        status = issue.get("status")
        if not status:
            continue
        
        # Ready for QA: Count ALL issues currently in these statuses (no time filtering)
        if status in QA_READY_STATUSES:
            issues_ready_for_qa += 1
        
        # QA Completed: Only count issues that were moved to completed status within the time period
        elif status in QA_COMPLETED_STATUSES:
            # Use status_updated_at if available, otherwise use updated_at
            updated_str = issue.get("status_updated_at") or issue.get("updated_at")
            if updated_str:
                try:
                    updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                    if updated_at >= cutoff_date:
                        issues_qa_completed += 1
                except (ValueError, TypeError):
                    pass
    
    return {
        "issues_ready_for_qa": issues_ready_for_qa,
        "issues_qa_completed": issues_qa_completed,
    }


def generate_report(lookback_days: int, issues_by_repo: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Generate a report for a specific lookback period."""
    results = []
    
    for repo in REPOS:
        repo_name = repo["name"]
        display_name = repo["display_name"]
        short_name = repo["short_name"]
        
        log.info("Fetching metrics for %s (last %d days)...", repo_name, lookback_days)
        
        try:
            # Fetch PR metrics
            pr_metrics = fetch_repo_pr_metrics(repo_name, lookback_days)
            
            # Count QA issues from project board data
            repo_issues = issues_by_repo.get(short_name, [])
            qa_metrics = count_qa_issues(repo_issues, lookback_days)
            
            results.append({
                "repo_name": repo_name,
                "display_name": display_name,
                "prs_opened": pr_metrics["prs_opened"],
                "prs_merged": pr_metrics["prs_merged"],
                "issues_ready_for_qa": qa_metrics["issues_ready_for_qa"],
                "issues_qa_completed": qa_metrics["issues_qa_completed"],
                "fetched_at": NOW_UTC.isoformat(),
            })
            log.info(
                "  %s: PRs opened=%d, merged=%d, ready for QA=%d, QA completed=%d",
                display_name,
                pr_metrics["prs_opened"],
                pr_metrics["prs_merged"],
                qa_metrics["issues_ready_for_qa"],
                qa_metrics["issues_qa_completed"],
            )
        except Exception as e:
            log.error("Failed to fetch metrics for %s: %s", repo_name, e)
            results.append({
                "repo_name": repo_name,
                "display_name": display_name,
                "prs_opened": 0,
                "prs_merged": 0,
                "issues_ready_for_qa": 0,
                "issues_qa_completed": 0,
                "fetched_at": NOW_UTC.isoformat(),
                "error": str(e),
            })
    
    return results


def write_csv(results: List[Dict[str, Any]], output_file: str):
    """Write results to a CSV file."""
    fieldnames = [
        "repo_name",
        "display_name",
        "prs_opened",
        "prs_merged",
        "issues_ready_for_qa",
        "issues_qa_completed",
        "fetched_at",
    ]
    
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    
    log.info("Exported repo summary to %s", output_file)


def main():
    if not GH_TOKEN:
        log.warning("GH_TOKEN not set. API rate limits will be very low.")
    
    # Fetch issues from all repo-specific project boards
    log.info("Fetching issues from GitHub Project V2 boards...")
    issues_by_repo = fetch_all_project_issues()
    
    # Generate reports for each time period
    for days in TIME_PERIODS:
        log.info("Generating report for last %d days...", days)
        results = generate_report(days, issues_by_repo)
        
        # Write to CSV
        output_file = f"repo_summary_{days}d.csv"
        write_csv(results, output_file)
        
        # Calculate totals
        total_prs_opened = sum(r["prs_opened"] for r in results)
        total_prs_merged = sum(r["prs_merged"] for r in results)
        total_ready_for_qa = sum(r["issues_ready_for_qa"] for r in results)
        total_qa_completed = sum(r["issues_qa_completed"] for r in results)
        
        log.info(
            "Totals (%dd): PRs opened=%d, merged=%d, ready for QA=%d, QA completed=%d",
            days,
            total_prs_opened,
            total_prs_merged,
            total_ready_for_qa,
            total_qa_completed,
        )
    
    # Also generate the default repo_summary.csv (30 days) for backward compatibility
    log.info("Generating default repo_summary.csv (30 days) for backward compatibility...")
    results_30d = generate_report(30, issues_by_repo)
    write_csv(results_30d, "repo_summary.csv")


if __name__ == "__main__":
    main()
