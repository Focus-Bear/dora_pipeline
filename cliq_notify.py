#!/usr/bin/env python3
"""
Send a daily DORA update to Zoho Cliq (#scrum channel).

Reuses repo_summary.py's per-repo metrics to report:
  - for each window (last 24 hours, last 7 days): PRs merged, issues moved to
    QA passed / QA failed, and roadmap progress (issues moved to Ready for QA
    vs new issues filed, with an ahead/behind indicator)
  - Ready for QA now, with its change vs 24 h and 7 days ago
  - open PRs (draft / approved split)
  - days since each repo's last release
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
  python cliq_notify.py                 # fetch real data, build + send (24h + 7d)
  python cliq_notify.py --dry-run       # build + log, do not send
  python cliq_notify.py --days 1,7      # explicit windows (comma-separated days)
"""

from __future__ import annotations

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import requests

from qa_metrics import NOT_AVAILABLE, format_ratio, progress_indicator, sum_optional, trend_label

if TYPE_CHECKING:
    from repo_summary import SummaryInputs

UTC = timezone.utc

# --- Cliq config ---
CLIQ_WEBHOOK_TOKEN = os.getenv("CLIQ_WEBHOOK_TOKEN") or ""
CLIQ_BOT_NAME = os.getenv("CLIQ_BOT_NAME", "ciupdates")
CLIQ_CHANNEL = os.getenv("CLIQ_CHANNEL", "scrum")
CLIQ_API_BASE = os.getenv("CLIQ_API_BASE", "https://cliq.zoho.com.au/api/v2")
CLIQ_WEBHOOK_URL = os.getenv("CLIQ_WEBHOOK_URL") or ""

# Link to the DORA dashboard, appended to the message footer.
DORA_DASHBOARD_URL = os.getenv("DORA_DASHBOARD_URL", "https://dora-pipeline.pages.dev")

# Windows (in days) to report, in display order: 24h first, then 7 days.
DEFAULT_WINDOWS = [1, 7]

SEPARATOR = "  ·  "
INLINE_SEPARATOR = " · "

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
        return "Last 24h"
    if lookback_days == 7:
        return "Last 7 days"
    return f"Last {lookback_days} days"


def _int(row: Dict[str, Any], key: str) -> int:
    return int(row.get(key) or 0)


def _optional(row: Dict[str, Any], key: str) -> Optional[int]:
    value = row.get(key)
    return None if value is None or value == "" else int(value)


def _name(row: Dict[str, Any]) -> str:
    return row.get("display_name") or row.get("repo_name") or "?"


def _show(value: Optional[int]) -> str:
    return NOT_AVAILABLE if value is None else str(value)


def _plural(count: int, noun: str) -> str:
    return "{} {}{}".format(count, noun, "" if count == 1 else "s")


def _qa_text(passed: Optional[int], failed: Optional[int]) -> str:
    return "✅ {} passed / ❌ {} failed".format(_show(passed), _show(failed))


def _roadmap_text(moved_to_qa: int, created: int, bugs: int) -> str:
    return "{} to QA vs {} new ({}) {} {}".format(
        moved_to_qa,
        created,
        _plural(bugs, "bug"),
        progress_indicator(moved_to_qa, created),
        format_ratio(moved_to_qa, created),
    )


def _is_active(row: Dict[str, Any]) -> bool:
    activity_keys = ["prs_merged", "issues_qa_completed", "issues_qa_failed", "issues_moved_to_ready_for_qa", "issues_created"]
    return any(_int(row, key) > 0 for key in activity_keys)


def _activity_sort_key(row: Dict[str, Any]) -> Tuple[int, int, int]:
    return (_int(row, "prs_merged"), _int(row, "issues_qa_completed"), _int(row, "issues_moved_to_ready_for_qa"))


def _repo_window_line(row: Dict[str, Any]) -> str:
    parts = [_plural(_int(row, "prs_merged"), "PR") + " merged"]
    if _optional(row, "issues_ready_for_qa") is not None:
        parts.append("QA ✅ {} ❌ {}".format(_show(_optional(row, "issues_qa_completed")), _show(_optional(row, "issues_qa_failed"))))
        moved = _int(row, "issues_moved_to_ready_for_qa")
        created = _int(row, "issues_created")
        parts.append("{} to QA vs {} new {}".format(moved, created, progress_indicator(moved, created)))
    else:
        parts.append("{} new".format(_plural(_int(row, "issues_created"), "issue")))
    return "• *{}* — {}".format(_name(row), INLINE_SEPARATOR.join(parts))


def _build_section(results: List[Dict[str, Any]], lookback_days: int) -> List[str]:
    """Build the lines for one window (header with totals + per-repo lines)."""
    total_merged = sum(_int(row, "prs_merged") for row in results)
    total_passed = sum_optional(_optional(row, "issues_qa_completed") for row in results)
    total_failed = sum_optional(_optional(row, "issues_qa_failed") for row in results)
    total_moved = sum(_int(row, "issues_moved_to_ready_for_qa") for row in results)
    total_created = sum(_int(row, "issues_created") for row in results)
    total_bugs = sum(_int(row, "bugs_created") for row in results)

    lines: List[str] = [
        SEPARATOR.join([
            "*{}* — *PRs merged:* {}".format(_window_label(lookback_days), total_merged),
            "*QA:* " + _qa_text(total_passed, total_failed),
            "*Roadmap:* " + _roadmap_text(total_moved, total_created, total_bugs),
        ])
    ]

    active = sorted((row for row in results if _is_active(row)), key=_activity_sort_key, reverse=True)
    if not active:
        lines.append("_No PRs merged, QA moves or new issues._ 🌙")
    lines.extend(_repo_window_line(row) for row in active)
    return lines


def _trend_text(current: Optional[int], day_ago: Optional[int], week_ago: Optional[int]) -> str:
    return "{} vs 24h{}{} vs 7d".format(trend_label(current, day_ago), INLINE_SEPARATOR, trend_label(current, week_ago))


def _ready_for_qa_line(row: Dict[str, Any]) -> str:
    current = _optional(row, "issues_ready_for_qa")
    return "• *{}* {} ({})".format(
        _name(row),
        _show(current),
        _trend_text(current, _optional(row, "ready_for_qa_1d_ago"), _optional(row, "ready_for_qa_7d_ago")),
    )


def _build_ready_for_qa_section(results: List[Dict[str, Any]]) -> List[str]:
    rows = [row for row in results if _optional(row, "issues_ready_for_qa") is not None]
    if not rows:
        return []
    total_now = sum_optional(_optional(row, "issues_ready_for_qa") for row in rows)
    total_day_ago = sum_optional(_optional(row, "ready_for_qa_1d_ago") for row in rows)
    total_week_ago = sum_optional(_optional(row, "ready_for_qa_7d_ago") for row in rows)
    lines = ["*📥 Ready for QA:* {} ({})".format(_show(total_now), _trend_text(total_now, total_day_ago, total_week_ago))]
    ordered = sorted(rows, key=lambda row: _int(row, "issues_ready_for_qa"), reverse=True)
    lines.extend(_ready_for_qa_line(row) for row in ordered)
    return lines


def _build_open_prs_section(results: List[Dict[str, Any]]) -> List[str]:
    total_open = sum(_int(row, "prs_open") for row in results)
    total_draft = sum(_int(row, "prs_draft") for row in results)
    total_approved = sum(_int(row, "prs_approved") for row in results)
    per_repo = INLINE_SEPARATOR.join(
        "{} {}".format(_name(row), _int(row, "prs_open"))
        for row in sorted(results, key=lambda r: _int(r, "prs_open"), reverse=True)
        if _int(row, "prs_open") > 0
    )
    lines = ["*🔀 Open PRs:* {} ({} draft{}{} approved)".format(total_open, total_draft, INLINE_SEPARATOR, total_approved)]
    if per_repo:
        lines.append(per_repo)
    return lines


def _release_text(row: Dict[str, Any]) -> str:
    days = _optional(row, "days_since_last_release")
    if days is None:
        return "{} {}".format(_name(row), NOT_AVAILABLE)
    version = row.get("release_version") or ""
    return "{} {}d{}".format(_name(row), days, " ({})".format(version) if version else "")


def _build_release_section(results: List[Dict[str, Any]]) -> List[str]:
    known = [row for row in results if _optional(row, "days_since_last_release") is not None]
    if not known:
        return []
    ordered = sorted(known, key=lambda row: _int(row, "days_since_last_release"))
    return ["*🚢 Days since last release:*", INLINE_SEPARATOR.join(_release_text(row) for row in ordered)]


def build_daily_message(sections: List[Tuple[int, List[Dict[str, Any]]]]) -> str:
    """
    Build the Cliq message text from one or more (lookback_days, results)
    windows, rendered in the order given, followed by the window-independent
    sections (Ready for QA trend, open PRs, release velocity) taken from the
    first window's rows. Each result dict is a repo_summary row.
    """
    now = _local_now()
    date_str = now.strftime("%a, %d %b %Y")

    lines: List[str] = ["🚀 *DORA Update* — " + date_str]
    for lookback_days, results in sections:
        lines.append("")
        lines.extend(_build_section(results, lookback_days))

    if sections:
        latest = sections[0][1]
        for block in (_build_ready_for_qa_section(latest), _build_open_prs_section(latest), _build_release_section(latest)):
            if block:
                lines.append("")
                lines.extend(block)

    if DORA_DASHBOARD_URL:
        lines.append("")
        lines.append("📊 [DORA dashboard](" + DORA_DASHBOARD_URL + ")")

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
    inputs: Optional["SummaryInputs"] = None,
    windows: Optional[List[int]] = None,
    precomputed: Optional[Dict[int, List[Dict[str, Any]]]] = None,
    dry_run: bool = False,
) -> Optional[str]:
    """
    Build and send the daily Cliq update for one or more windows (in days).

    If inputs is None, fetches them via repo_summary (needs GH_API_READ_TOKEN).
    `precomputed` maps a window (days) to an already-generated report so callers
    (e.g. repo_summary.main) can avoid recomputing windows they already built.
    Returns the message text (also useful for dry runs), or None if nothing was built.
    """
    # Lazy import to avoid a hard import cycle with repo_summary.
    from repo_summary import collect_inputs, generate_report

    windows = windows or DEFAULT_WINDOWS
    precomputed = dict(precomputed or {})

    missing = [days for days in windows if days not in precomputed]
    if missing and inputs is None:
        inputs = collect_inputs(windows)

    sections: List[Tuple[int, List[Dict[str, Any]]]] = []
    for days in windows:
        results = precomputed.get(days)
        if results is None:
            results = generate_report(days, inputs)
        sections.append((days, results))

    message = build_daily_message(sections)

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
    windows = DEFAULT_WINDOWS
    if "--days" in args:
        try:
            raw = args[args.index("--days") + 1]
            windows = [int(d) for d in raw.split(",") if d.strip()]
        except (ValueError, IndexError):
            log.error("--days requires day counts, e.g. --days 1,7")
            sys.exit(2)

    send_daily_update(windows=windows, dry_run=dry_run)


if __name__ == "__main__":
    main()
