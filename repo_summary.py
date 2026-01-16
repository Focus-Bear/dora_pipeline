#!/usr/bin/env python3
"""
Fetch repository summary metrics (PRs opened, PRs merged, issues ready for QA, issues QA completed)
for multiple Focus Bear repositories and export to CSV.
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

# Repositories to track
REPOS = [
    {"name": "Focus-Bear/web_dashboard", "display_name": "Web Dashboard"},
    {"name": "Focus-Bear/backend", "display_name": "Backend"},
    {"name": "Focus-Bear/mobile-app", "display_name": "Mobile"},
    {"name": "Focus-Bear/Mac-App", "display_name": "Mac"},
    {"name": "Focus-Bear/windows-app-v2", "display_name": "Windows"},
]

# Lookback period
LOOKBACK_DAYS = 30

BASE_GH = "https://api.github.com"

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


def fetch_repo_metrics(repo_name: str) -> Dict[str, int]:
    """Fetch PR and issue metrics for a single repository."""
    cutoff_date = NOW_UTC - timedelta(days=LOOKBACK_DAYS)
    
    # Fetch PRs
    prs = gh_get_paged(f"{BASE_GH}/repos/{repo_name}/pulls", params={"state": "all"})
    
    # Filter PRs created in the last 30 days
    recent_prs = [
        pr for pr in prs
        if pr.get("created_at") and datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00")) >= cutoff_date
    ]
    
    prs_opened = len(recent_prs)
    prs_merged = len([pr for pr in recent_prs if pr.get("merged_at")])
    
    # Fetch issues (excluding PRs)
    issues = gh_get_paged(f"{BASE_GH}/repos/{repo_name}/issues", params={"state": "all"})
    
    # Filter out pull requests (GitHub API returns PRs as issues too)
    actual_issues = [issue for issue in issues if "pull_request" not in issue]
    
    # Count issues by QA status based on labels
    issues_ready_for_qa = 0
    issues_qa_completed = 0
    
    for issue in actual_issues:
        labels = [label.get("name", "").lower() for label in issue.get("labels", [])]
        
        # Check for "ready for QA" labels
        if any(
            "ready for qa" in label or
            "ready-for-qa" in label or
            "qa ready" in label
            for label in labels
        ):
            issues_ready_for_qa += 1
        
        # Check for "QA completed" labels
        if any(
            "qa completed" in label or
            "qa-completed" in label or
            "qa done" in label or
            "qa-done" in label or
            "qa'd" in label
            for label in labels
        ):
            issues_qa_completed += 1
    
    return {
        "prs_opened": prs_opened,
        "prs_merged": prs_merged,
        "issues_ready_for_qa": issues_ready_for_qa,
        "issues_qa_completed": issues_qa_completed,
    }


def main():
    if not GH_TOKEN:
        log.warning("GH_TOKEN not set. API rate limits will be very low.")
    
    results = []
    
    for repo in REPOS:
        repo_name = repo["name"]
        display_name = repo["display_name"]
        
        log.info("Fetching metrics for %s...", repo_name)
        
        try:
            metrics = fetch_repo_metrics(repo_name)
            results.append({
                "repo_name": repo_name,
                "display_name": display_name,
                "prs_opened": metrics["prs_opened"],
                "prs_merged": metrics["prs_merged"],
                "issues_ready_for_qa": metrics["issues_ready_for_qa"],
                "issues_qa_completed": metrics["issues_qa_completed"],
                "fetched_at": NOW_UTC.isoformat(),
            })
            log.info(
                "  %s: PRs opened=%d, merged=%d, ready for QA=%d, QA completed=%d",
                display_name,
                metrics["prs_opened"],
                metrics["prs_merged"],
                metrics["issues_ready_for_qa"],
                metrics["issues_qa_completed"],
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
    
    # Write to CSV
    output_file = "repo_summary.csv"
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
    
    # Calculate totals
    total_prs_opened = sum(r["prs_opened"] for r in results)
    total_prs_merged = sum(r["prs_merged"] for r in results)
    total_ready_for_qa = sum(r["issues_ready_for_qa"] for r in results)
    total_qa_completed = sum(r["issues_qa_completed"] for r in results)
    
    log.info(
        "Totals: PRs opened=%d, merged=%d, ready for QA=%d, QA completed=%d",
        total_prs_opened,
        total_prs_merged,
        total_ready_for_qa,
        total_qa_completed,
    )


if __name__ == "__main__":
    main()
