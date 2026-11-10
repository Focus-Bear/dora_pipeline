#!/usr/bin/env python3
"""
Build the Focus Bear dev report and send it to Zoho Cliq (#scrum channel).

This is the one script that produces the report; the numbers come from
repo_summary.py. For the last N days (default 7), compared with the N days
before ("prev"), it reports per repo plus totals:

  1. Dev velocity — PRs merged, PRs open now
  2. Quality      — new issues filed (and how many are labelled bug), and how
                    many issues QA failed out of those QA tested
  3. QA backlog   — issues in each board's Ready for QA column now, the change
                    vs 7 days ago, the median wait and the oldest issues
  Appendix        — days since each repo's last release

Posts via a Zoho Cliq bot incoming webhook whose Deluge handler forwards the
JSON body to the target channel, e.g.:

    POST https://cliq.zoho.com.au/api/v2/bots/<bot>/incoming?zapikey=<token>
    body: {"channel": "scrum", "text": "<message>"}

Configuration (env vars):
  GH_API_READ_TOKEN    GitHub token with repo + read:project (required)
  CLIQ_WEBHOOK_TOKEN   zapikey for the bot incoming webhook (required to send)
  CLIQ_BOT_NAME        bot unique name (default: "ciupdates")
  CLIQ_CHANNEL         target channel unique name (default: "scrum")
  CLIQ_API_BASE        API base (default: "https://cliq.zoho.com.au/api/v2")
  CLIQ_WEBHOOK_URL     full webhook URL incl. zapikey (overrides the three above)

CLI:
  python cliq_notify.py                              # fetch real data, build + send
  python cliq_notify.py --dry-run                    # build + print, do not send
  python cliq_notify.py --days 14                    # a different window length
  python cliq_notify.py --dry-run --backlog-csv qa_backlog.csv
                                                     # also write the full QA backlog, oldest first
"""

from __future__ import annotations

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import requests

from qa_metrics import NOT_AVAILABLE, BacklogEntry, percent, sum_optional, trend_label

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

DEFAULT_WINDOW_DAYS = 7
# How many of each board's longest-waiting Ready for QA issues are named.
BACKLOG_OLDEST_SHOWN = 3
# The Ready for QA count is compared with this many days ago (a repo_summary trend column).
BACKLOG_TREND_DAYS = 7

INLINE_SEPARATOR = " · "

log = logging.getLogger("cliq_notify")

Row = Dict[str, Any]


def _local_now() -> datetime:
    """Now in Australia/Sydney when available, else UTC."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Australia/Sydney"))
    except Exception:
        return datetime.now(UTC)


def _int(row: Row, key: str) -> int:
    return int(row.get(key) or 0)


def _optional(row: Row, key: str) -> Optional[int]:
    value = row.get(key)
    return None if value is None or value == "" else int(value)


def _name(row: Row) -> str:
    return row.get("display_name") or row.get("repo_name") or "?"


def _show(value: Optional[int]) -> str:
    return NOT_AVAILABLE if value is None else str(value)


def _plural(count: int, noun: str) -> str:
    return "{} {}{}".format(count, noun, "" if count == 1 else "s")


def _total(rows: List[Row], key: str) -> int:
    return sum(_int(row, key) for row in rows)


def _total_optional(rows: List[Row], key: str) -> Optional[int]:
    return sum_optional(_optional(row, key) for row in rows)


def _sorted_desc(rows: List[Row], key: Callable[[Row], int]) -> List[Row]:
    return sorted(rows, key=key, reverse=True)


def _has_qa_board(row: Row) -> bool:
    return _optional(row, "issues_ready_for_qa") is not None


# ---------- 1. Dev velocity ----------

def _velocity_repo_line(row: Row) -> str:
    return "• *{}* — {} merged (prev {}){}{} open".format(
        _name(row), _int(row, "prs_merged"), _int(row, "prs_merged_prev"), INLINE_SEPARATOR, _int(row, "prs_open")
    )


def build_velocity_section(rows: List[Row]) -> List[str]:
    merged = _total(rows, "prs_merged")
    merged_prev = _total(rows, "prs_merged_prev")
    lines = ["*1. Dev velocity* — {} merged (prev {}, {}){}{} open".format(
        _plural(merged, "PR"), merged_prev, trend_label(merged, merged_prev), INLINE_SEPARATOR, _plural(_total(rows, "prs_open"), "PR")
    )]
    active = [row for row in rows if _int(row, "prs_merged") or _int(row, "prs_merged_prev") or _int(row, "prs_open")]
    lines.extend(_velocity_repo_line(row) for row in _sorted_desc(active, lambda row: _int(row, "prs_merged")))
    return lines


# ---------- 2. Quality ----------

def _failed_text(failed: Optional[int], tested: Optional[int]) -> str:
    if failed is None:
        return "no QA Failed column"
    share = percent(failed, tested)
    return "QA failed {} of {} tested{}".format(failed, _show(tested), " ({}%)".format(share) if share is not None else "")


def _failed_prev_text(failed: Optional[int], tested: Optional[int]) -> str:
    return "prev {} of {}".format(failed, _show(tested)) if failed is not None else ""


def _quality_repo_line(row: Row) -> str:
    parts = ["{} (prev {})".format(_plural(_int(row, "issues_created"), "new issue"), _int(row, "issues_created_prev"))]
    if _has_qa_board(row):
        failed_prev = _failed_prev_text(_optional(row, "issues_qa_failed_prev"), _optional(row, "issues_qa_tested_prev"))
        failed = _failed_text(_optional(row, "issues_qa_failed"), _optional(row, "issues_qa_tested"))
        parts.append(failed + (" ({})".format(failed_prev) if failed_prev else ""))
    return "• *{}* — {}".format(_name(row), INLINE_SEPARATOR.join(parts))


def build_quality_section(rows: List[Row]) -> List[str]:
    created = _total(rows, "issues_created")
    created_prev = _total(rows, "issues_created_prev")
    failed = _total_optional(rows, "issues_qa_failed")
    failed_prev = _total_optional(rows, "issues_qa_failed_prev")
    with_failed_column = [row for row in rows if _optional(row, "issues_qa_failed") is not None]
    tested = _total_optional(with_failed_column, "issues_qa_tested")
    tested_prev = _total_optional(with_failed_column, "issues_qa_tested_prev")
    header = "*2. Quality* — {} (prev {}, {}), {} labelled bug{}{}".format(
        _plural(created, "new issue"), created_prev, trend_label(created, created_prev), _total(rows, "bugs_created"),
        INLINE_SEPARATOR, _failed_text(failed, tested),
    )
    failed_prev_text = _failed_prev_text(failed_prev, tested_prev)
    lines = [header + (" ({})".format(failed_prev_text) if failed_prev_text else "")]
    active = [row for row in rows if _int(row, "issues_created") or _int(row, "issues_created_prev") or _int(row, "issues_qa_tested")]
    lines.extend(_quality_repo_line(row) for row in _sorted_desc(active, lambda row: _int(row, "issues_created")))
    return lines


# ---------- 3. QA backlog ----------

def _backlog_issue_link(entry: BacklogEntry) -> str:
    label = "#{}".format(entry.number) if entry.number is not None else "?"
    age = "{}d".format(_show(entry.age_days))
    return "[{}]({}) {}".format(label, entry.url, age) if entry.url else "{} {}".format(label, age)


def _backlog_repo_line(row: Row) -> str:
    oldest = (row.get("qa_backlog") or [])[:BACKLOG_OLDEST_SHOWN]
    median = _optional(row, "qa_backlog_median_days")
    parts = [
        "{} waiting ({} vs {}d ago)".format(
            _int(row, "issues_ready_for_qa"),
            trend_label(_optional(row, "issues_ready_for_qa"), _optional(row, "ready_for_qa_{}d_ago".format(BACKLOG_TREND_DAYS))),
            BACKLOG_TREND_DAYS,
        ),
    ]
    if median is not None:
        parts.append("median wait {}d".format(median))
    if oldest:
        parts.append("oldest " + ", ".join(_backlog_issue_link(entry) for entry in oldest))
    return "• *{}* — {}".format(_name(row), INLINE_SEPARATOR.join(parts))


def build_backlog_section(rows: List[Row]) -> List[str]:
    boards = [row for row in rows if _has_qa_board(row)]
    if not boards:
        return []
    waiting = _total_optional(boards, "issues_ready_for_qa")
    week_ago = _total_optional(boards, "ready_for_qa_{}d_ago".format(BACKLOG_TREND_DAYS))
    oldest = max((_int(row, "qa_backlog_oldest_days") for row in boards), default=0)
    lines = ["*3. QA backlog* — {} in Ready for QA ({} vs {}d ago){}oldest waiting {}d".format(
        _plural(waiting or 0, "issue"), trend_label(waiting, week_ago), BACKLOG_TREND_DAYS, INLINE_SEPARATOR, oldest
    )]
    lines.extend(_backlog_repo_line(row) for row in _sorted_desc(boards, lambda row: _int(row, "qa_backlog_oldest_days")))
    return lines


# ---------- Appendix: release velocity ----------

def _release_text(row: Row) -> str:
    days = _optional(row, "days_since_last_release")
    version = row.get("release_version") or ""
    return "{} {}d{}".format(_name(row), days, " ({})".format(version) if version else "")


def build_release_appendix(rows: List[Row]) -> List[str]:
    known = [row for row in rows if _optional(row, "days_since_last_release") is not None]
    if not known:
        return []
    ordered = sorted(known, key=lambda row: _int(row, "days_since_last_release"))
    return ["_Appendix — days since last release:_ " + INLINE_SEPARATOR.join(_release_text(row) for row in ordered)]


def build_daily_message(rows: List[Row], window_days: int = DEFAULT_WINDOW_DAYS) -> str:
    """The Cliq message for one window, from repo_summary rows (one per repo)."""
    lines: List[str] = [
        "📊 *Dev report* — " + _local_now().strftime("%a, %d %b %Y"),
        "_Last {0} days; \"prev\" is the {0} days before that._".format(window_days),
    ]
    for block in (
        build_velocity_section(rows),
        build_quality_section(rows),
        build_backlog_section(rows),
        build_release_appendix(rows),
    ):
        if block:
            lines.append("")
            lines.extend(block)

    if DORA_DASHBOARD_URL:
        lines.append("")
        lines.append("[DORA dashboard](" + DORA_DASHBOARD_URL + ")")

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
    days: int = DEFAULT_WINDOW_DAYS,
    precomputed: Optional[List[Row]] = None,
    dry_run: bool = False,
    backlog_csv: Optional[str] = None,
) -> str:
    """
    Build and send the Cliq report for the last `days` days.

    If inputs is None, fetches them via repo_summary (needs GH_API_READ_TOKEN).
    `precomputed` is an already-generated repo_summary report for `days`, so
    callers (e.g. repo_summary.main) can avoid recomputing it.
    Returns the message text (also useful for dry runs).
    """
    # Lazy import to avoid a hard import cycle with repo_summary.
    from repo_summary import collect_inputs, generate_report, write_backlog_csv

    rows = precomputed
    if rows is None:
        rows = generate_report(days, inputs or collect_inputs([days]))
    if backlog_csv:
        write_backlog_csv(rows, backlog_csv)

    message = build_daily_message(rows, days)
    if dry_run:
        print(message)
        return message

    post_to_cliq(message)
    return message


def _option_value(args: List[str], flag: str) -> Optional[str]:
    if flag not in args:
        return None
    index = args.index(flag) + 1
    if index >= len(args):
        log.error("%s needs a value", flag)
        sys.exit(2)
    return args[index]


def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    args = sys.argv[1:]
    days_value = _option_value(args, "--days")
    if days_value is not None and not days_value.isdigit():
        log.error("--days takes a whole number of days, e.g. --days 7")
        sys.exit(2)
    send_daily_update(
        days=int(days_value) if days_value else DEFAULT_WINDOW_DAYS,
        dry_run="--dry-run" in args,
        backlog_csv=_option_value(args, "--backlog-csv"),
    )


if __name__ == "__main__":
    main()
