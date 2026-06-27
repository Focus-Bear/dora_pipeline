#!/usr/bin/env python3
"""
Send a daily DORA update to Zoho Cliq (#scrum channel).

Reuses repo_summary.py's per-repo metrics to report, for the last 24 hours:
  - PRs merged per repo
  - Issues QA-closed (QA completed) per repo
plus org-wide totals.

Posts via a Zoho Cliq bot incoming webhook whose Deluge handler forwards the
JSON body to the target channel, e.g.:

    POST https://cliq.zoho.com.au/api/v2/bots/<bot>/incoming?zapikey=<token>
    body: {"channel": "scrum", "text": "<message>"}

Configuration (env vars):
  CLIQ_WEBHOOK_TOKEN   zapikey for the bot incoming webhook (required to send)
  CLIQ_BOT_NAME        bot unique name (default: "ciupdates")
  CLIQ_CHANNEL         target channel unique name (default: "scrum")
  CLIQ_API_BASE        API base (default: "https://cliq.zoho.com.au/api/v2")
  CLIQ_WEBHOOK_URL     full webhook URL incl. zapikey (overrides the three above)

CLI:
  python cliq_notify.py                 # fetch real data, build + send
  python cliq_notify.py --dry-run       # build + print, do not send
  python cliq_notify.py --days 7        # use a 7-day window instead of 24h
"""

from __future__ import annotations

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

UTC = timezone.utc

# --- Cliq config ---
CLIQ_WEBHOOK_TOKEN = os.getenv("CLIQ_WEBHOOK_TOKEN") or ""
CLIQ_BOT_NAME = os.getenv("CLIQ_BOT_NAME", "ciupdates")
CLIQ_CHANNEL = os.getenv("CLIQ_CHANNEL", "scrum")
CLIQ_API_BASE = os.getenv("CLIQ_API_BASE", "https://cliq.zoho.com.au/api/v2")
CLIQ_WEBHOOK_URL = os.getenv("CLIQ_WEBHOOK_URL") or ""

# Display order / window
DEFAULT_LOOKBACK_DAYS = int(os.getenv("CLIQ_LOOKBACK_DAYS", "1"))

log = logging.getLogger("cliq_notify")


def _local_now() -> datetime:
    """Now in Australia/Sydney when available, else UTC."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Australia/Sydney"))
    except Exception:
        return datetime.now(UTC)


def _window_label(lookback_days: int) -> str:
    if lookback_days == 1:
        return "last 24h"
    return f"last {lookback_days} days"


def build_daily_message(results: List[Dict[str, Any]], lookback_days: int = 1) -> str:
    """
    Build the Cliq message text from repo_summary.generate_report() results.

    Each result is a dict with at least:
      display_name, prs_merged, issues_qa_completed
    """
    now = _local_now()
    date_str = now.strftime("%a, %d %b %Y")
    window = _window_label(lookback_days)

    total_merged = sum(int(r.get("prs_merged") or 0) for r in results)
    total_qa = sum(int(r.get("issues_qa_completed") or 0) for r in results)

    lines: List[str] = []
    lines.append("🚀 *DORA Daily Update* — " + date_str)
    lines.append("_" + window.capitalize() + "_")
    lines.append("")
    lines.append(
        "*PRs merged:* {}  ·  *Issues QA-closed:* {}".format(total_merged, total_qa)
    )
    lines.append("")

    # Per-repo lines, only repos with activity, busiest first.
    active = [
        r
        for r in results
        if int(r.get("prs_merged") or 0) > 0 or int(r.get("issues_qa_completed") or 0) > 0
    ]
    active.sort(
        key=lambda r: (int(r.get("prs_merged") or 0), int(r.get("issues_qa_completed") or 0)),
        reverse=True,
    )

    if not active:
        lines.append("No PRs merged or issues QA-closed in the " + window + ". 🌙")
    else:
        for r in active:
            name = r.get("display_name") or r.get("repo_name") or "?"
            merged = int(r.get("prs_merged") or 0)
            qa = int(r.get("issues_qa_completed") or 0)
            lines.append(
                "• *{}* — {} PR{} merged, {} QA-closed".format(
                    name, merged, "" if merged == 1 else "s", qa
                )
            )

    return "\n".join(lines)


def _webhook_url() -> str:
    if CLIQ_WEBHOOK_URL:
        return CLIQ_WEBHOOK_URL
    return "{}/bots/{}/incoming?zapikey={}".format(
        CLIQ_API_BASE.rstrip("/"), CLIQ_BOT_NAME, CLIQ_WEBHOOK_TOKEN
    )


def post_to_cliq(text: str, channel: Optional[str] = None) -> bool:
    """Post a message to Cliq. Returns True on apparent success."""
    if not CLIQ_WEBHOOK_TOKEN and not CLIQ_WEBHOOK_URL:
        log.warning("CLIQ_WEBHOOK_TOKEN/CLIQ_WEBHOOK_URL not set; skipping Cliq post.")
        return False

    channel = channel or CLIQ_CHANNEL
    url = _webhook_url()
    payload = {"channel": channel, "text": text}

    try:
        r = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=30,
        )
    except Exception as e:
        log.error("Cliq request failed: %s", e)
        return False

    if 200 <= r.status_code < 300:
        log.info("Posted daily update to Cliq #%s (HTTP %d).", channel, r.status_code)
        return True

    log.error("Cliq post failed: HTTP %d — %s", r.status_code, r.text[:300])
    return False


def send_daily_update(
    issues_by_repo: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    dry_run: bool = False,
) -> Optional[str]:
    """
    Build and send the daily Cliq update.

    If issues_by_repo is None, fetches it via repo_summary (needs GH_API_READ_TOKEN).
    Otherwise reuses the already-fetched project board issues to avoid extra calls.
    Returns the message text (also useful for dry runs), or None if nothing was built.
    """
    # Lazy import to avoid a hard import cycle with repo_summary.
    from repo_summary import fetch_all_project_issues, generate_report

    if issues_by_repo is None:
        issues_by_repo = fetch_all_project_issues()

    results = generate_report(lookback_days, issues_by_repo)
    message = build_daily_message(results, lookback_days)

    if dry_run:
        log.info("[dry-run] Cliq message:\n%s", message)
        return message

    post_to_cliq(message)
    return message


def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    lookback_days = DEFAULT_LOOKBACK_DAYS
    if "--days" in args:
        try:
            lookback_days = int(args[args.index("--days") + 1])
        except (ValueError, IndexError):
            log.error("--days requires an integer argument")
            sys.exit(2)

    send_daily_update(lookback_days=lookback_days, dry_run=dry_run)


if __name__ == "__main__":
    main()
