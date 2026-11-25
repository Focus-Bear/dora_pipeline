#!/usr/bin/env python3
"""
Build the Focus Bear dev report and send it to Zoho Cliq (#scrum channel).

This is the one script that produces the report; the numbers come from
repo_summary.py. Every figure is shown as "last 24 hours / last N days"
(default 7), per repo plus totals:

  1. Dev velocity    — PRs merged, issues moved to Ready for QA, PRs open now
  2. QA velocity     — fixes QA finished re-testing, split into passed / failed
  3. New issues vs QA failed
                     — new issues (not counting bugs QA found) next to QA
                       failed (fixes that failed re-test + bugs QA filed
                       straight into QA Failed)
  4. QA backlog      — issues in each board's Ready for QA column now, the
                       change vs 24 h and 7 days ago, the median wait and the
                       oldest issues
  Appendix           — days since each repo's last release

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
  python cliq_notify.py --days 14                    # a different longer window (24 h is always shown)
  python cliq_notify.py --dry-run --backlog-csv qa_backlog.csv
                                                     # also write the full QA backlog, oldest first
"""

from __future__ import annotations

import os
import sys
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import requests

from qa_metrics import NOT_AVAILABLE, BacklogEntry, sum_optional, trend_label

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

# Every figure is shown for the last day next to the longer window.
DAY_WINDOW_DAYS = 1
DEFAULT_WINDOW_DAYS = 7
# How many of each board's longest-waiting Ready for QA issues are named.
BACKLOG_OLDEST_SHOWN = 3
# The Ready for QA count is compared with these many days ago (repo_summary trend columns).
BACKLOG_TRENDS = ((1, "24h ago"), (7, "7d ago"))
BACKLOG_KEYS = ["issues_ready_for_qa"] + ["ready_for_qa_{}d_ago".format(days) for days, _ in BACKLOG_TRENDS]
QA_FAILED_KEYS = ["issues_qa_failed", "issues_found_by_qa"]
TOTAL_KEY = "total"

INLINE_SEPARATOR = " · "
WINDOW_SEPARATOR = " / "

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


@dataclass(frozen=True)
class RepoWindows:
    """One repo's report rows for the last 24 hours and for the longer window."""

    day: Row
    window: Row

    @property
    def name(self) -> str:
        return _name(self.window)


def pair_rows(day_rows: List[Row], window_rows: List[Row]) -> List[RepoWindows]:
    """Match each repo's 24-hour row to its longer-window row, keeping the longer window's repo order."""
    day_by_repo = {row.get("repo_name"): row for row in day_rows}
    return [RepoWindows(day_by_repo.get(row.get("repo_name"), {}), row) for row in window_rows]


def _both(repo: RepoWindows, value: Callable[[Row], Optional[int]]) -> str:
    """A figure as "last 24 h / last N days"."""
    return "{}{}{}".format(_show(value(repo.day)), WINDOW_SEPARATOR, _show(value(repo.window)))


def _key(key: str) -> Callable[[Row], Optional[int]]:
    return lambda row: _optional(row, key)


def _totals(repos: List[RepoWindows], value: Callable[[Row], Optional[int]]) -> RepoWindows:
    """A pseudo-repo whose figures are the sums over `repos` (unknown when no repo knows them)."""
    return RepoWindows(
        {TOTAL_KEY: sum_optional(value(repo.day) for repo in repos)},
        {TOTAL_KEY: sum_optional(value(repo.window) for repo in repos)},
    )


def _total_both(repos: List[RepoWindows], value: Callable[[Row], Optional[int]]) -> str:
    return _both(_totals(repos, value), _key(TOTAL_KEY))


def _is_active(repo: RepoWindows, values: List[Callable[[Row], Optional[int]]]) -> bool:
    return any(value(repo.window) or value(repo.day) for value in values)


def _has_qa_board(row: Row) -> bool:
    return _optional(row, "issues_ready_for_qa") is not None


def _has_failed_column(row: Row) -> bool:
    return _optional(row, "issues_qa_failed") is not None


def _repo_line(repo: RepoWindows, parts: List[str]) -> str:
    return "• *{}* — {}".format(repo.name, INLINE_SEPARATOR.join(parts))


# ---------- 1. Dev velocity ----------

def _velocity_parts(repo: RepoWindows) -> List[str]:
    parts = ["merged " + _both(repo, _key("prs_merged"))]
    if _optional(repo.window, "issues_moved_to_ready_for_qa") is not None:
        parts.append("to QA " + _both(repo, _key("issues_moved_to_ready_for_qa")))
    return parts + ["{} open".format(_show(_optional(repo.window, "prs_open")))]


def build_velocity_section(repos: List[RepoWindows]) -> List[str]:
    boards = [repo for repo in repos if _has_qa_board(repo.window)]
    header = "*1. Dev velocity* — merged {}{}to QA {}{}{} PRs open now".format(
        _total_both(repos, _key("prs_merged")), INLINE_SEPARATOR,
        _total_both(boards, _key("issues_moved_to_ready_for_qa")), INLINE_SEPARATOR,
        _show(sum_optional(_optional(repo.window, "prs_open") for repo in repos)),
    )
    active = [repo for repo in repos if _is_active(repo, [_key("prs_merged"), _key("prs_open")])]
    return [header] + [_repo_line(repo, _velocity_parts(repo)) for repo in active]


# ---------- 2. QA velocity ----------

def _qa_velocity_parts(repo: RepoWindows) -> List[str]:
    parts = [
        "tested " + _both(repo, _key("issues_qa_tested")),
        "passed " + _both(repo, _key("issues_qa_completed")),
    ]
    if _has_failed_column(repo.window):
        parts.append("failed " + _both(repo, _key("issues_qa_failed")))
    else:
        parts.append("no QA Failed column")
    return parts


def build_qa_velocity_section(repos: List[RepoWindows]) -> List[str]:
    boards = [repo for repo in repos if _has_qa_board(repo.window)]
    if not boards:
        return []
    with_failed = [repo for repo in boards if _has_failed_column(repo.window)]
    header = "*2. QA velocity* — tested {}{}passed {}{}failed {}".format(
        _total_both(boards, _key("issues_qa_tested")), INLINE_SEPARATOR,
        _total_both(boards, _key("issues_qa_completed")), INLINE_SEPARATOR,
        _total_both(with_failed, _key("issues_qa_failed")),
    )
    active = [repo for repo in boards if _is_active(repo, [_key("issues_qa_tested")])]
    return [header] + [_repo_line(repo, _qa_velocity_parts(repo)) for repo in active]


# ---------- 3. New issues vs QA failed ----------

def qa_failed_count(row: Row) -> Optional[int]:
    """Fixes that failed QA re-test plus bugs QA filed straight into QA Failed."""
    return sum_optional([_optional(row, "issues_qa_failed"), _optional(row, "issues_found_by_qa")])


def _new_issues(row: Row) -> Optional[int]:
    return _optional(row, "issues_new")


def _qa_failed_breakdown(row: Row, window_days: int) -> str:
    """The longer window's QA failed figure split into its two sources, e.g. "(7d: 23 failed re-test, 79 found by QA)"."""
    if not qa_failed_count(row):
        return ""
    return " ({}d: {} failed re-test, {} found by QA)".format(
        window_days, _int(row, "issues_qa_failed"), _int(row, "issues_found_by_qa")
    )


def _quality_parts(repo: RepoWindows, window_days: int) -> List[str]:
    parts = ["new issues " + _both(repo, _new_issues)]
    if _has_failed_column(repo.window):
        parts.append("QA failed " + _both(repo, qa_failed_count) + _qa_failed_breakdown(repo.window, window_days))
    return parts


def build_quality_section(repos: List[RepoWindows], window_days: int) -> List[str]:
    with_failed = [repo for repo in repos if _has_failed_column(repo.window)]
    window_totals = {key: sum_optional(_optional(repo.window, key) for repo in with_failed) for key in QA_FAILED_KEYS}
    header = "*3. New issues vs QA failed* — new issues {}{}QA failed {}{}".format(
        _total_both(repos, _new_issues), INLINE_SEPARATOR,
        _total_both(with_failed, qa_failed_count), _qa_failed_breakdown(window_totals, window_days),
    )
    active = [repo for repo in repos if _is_active(repo, [_new_issues, qa_failed_count])]
    return [header] + [_repo_line(repo, _quality_parts(repo, window_days)) for repo in active]


# ---------- 4. QA backlog ----------

def _backlog_issue_link(entry: BacklogEntry) -> str:
    label = "#{}".format(entry.number) if entry.number is not None else "?"
    age = "{}d".format(_show(entry.age_days))
    return "[{}]({}) {}".format(label, entry.url, age) if entry.url else "{} {}".format(label, age)


def _backlog_trend(waiting: Optional[int], row: Row) -> str:
    """"(↓2 vs 24h ago, ↑5 vs 7d ago)" for the Ready for QA count."""
    trends = [
        "{} vs {}".format(trend_label(waiting, _optional(row, "ready_for_qa_{}d_ago".format(days))), label)
        for days, label in BACKLOG_TRENDS
    ]
    return "({})".format(", ".join(trends))


def _backlog_repo_line(row: Row) -> str:
    waiting = _optional(row, "issues_ready_for_qa")
    parts = ["{} waiting {}".format(_show(waiting), _backlog_trend(waiting, row))]
    median = _optional(row, "qa_backlog_median_days")
    if median is not None:
        parts.append("median wait {}d".format(median))
    oldest = (row.get("qa_backlog") or [])[:BACKLOG_OLDEST_SHOWN]
    if oldest:
        parts.append("oldest " + ", ".join(_backlog_issue_link(entry) for entry in oldest))
    return "• *{}* — {}".format(_name(row), INLINE_SEPARATOR.join(parts))


def build_backlog_section(rows: List[Row]) -> List[str]:
    boards = [row for row in rows if _has_qa_board(row)]
    if not boards:
        return []
    totals = {key: sum_optional(_optional(row, key) for row in boards) for key in BACKLOG_KEYS}
    waiting = totals["issues_ready_for_qa"]
    oldest = max((_int(row, "qa_backlog_oldest_days") for row in boards), default=0)
    lines = ["*4. QA backlog* — {} waiting in Ready for QA {}{}oldest waiting {}d".format(
        _show(waiting), _backlog_trend(waiting, totals), INLINE_SEPARATOR, oldest
    )]
    lines.extend(_backlog_repo_line(row) for row in boards)
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


def build_legend(window_days: int) -> List[str]:
    return [
        "_Each figure is *last 24 hours / last {} days*._".format(window_days),
        "_Key: *merged* = PRs merged · *to QA* = issues devs moved to Ready for QA · "
        "*tested* = fixes QA finished re-testing, split into *passed* and *failed* · "
        "*new issues* = issues filed by anyone, not counting bugs QA found · "
        "*QA failed* = fixes that failed re-test plus bugs QA found and filed straight into QA Failed · "
        "*waiting* = issues in Ready for QA now._",
    ]


def build_daily_message(day_rows: List[Row], window_rows: List[Row], window_days: int = DEFAULT_WINDOW_DAYS) -> str:
    """The Cliq message from repo_summary rows (one per repo) for the last 24 hours and the longer window."""
    repos = pair_rows(day_rows, window_rows)
    lines: List[str] = ["📊 *Dev report* — " + _local_now().strftime("%a, %d %b %Y")]
    lines.extend(build_legend(window_days))
    for block in (
        build_velocity_section(repos),
        build_qa_velocity_section(repos),
        build_quality_section(repos, window_days),
        build_backlog_section(window_rows),
        build_release_appendix(window_rows),
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
    precomputed: Optional[Dict[int, List[Row]]] = None,
    dry_run: bool = False,
    backlog_csv: Optional[str] = None,
) -> str:
    """
    Build and send the Cliq report for the last 24 hours and the last `days` days.

    If inputs is None, fetches them via repo_summary (needs GH_API_READ_TOKEN).
    `precomputed` maps a window length in days to an already-generated
    repo_summary report, so callers (e.g. repo_summary.main) can avoid
    recomputing it; any window missing from it is generated here.
    Returns the message text (also useful for dry runs).
    """
    # Lazy import to avoid a hard import cycle with repo_summary.
    from repo_summary import collect_inputs, generate_report, write_backlog_csv

    windows = [DAY_WINDOW_DAYS, days]
    reports = dict(precomputed or {})
    missing = [window for window in windows if window not in reports]
    if missing:
        inputs = inputs or collect_inputs(windows)
        reports.update({window: generate_report(window, inputs) for window in missing})
    if backlog_csv:
        write_backlog_csv(reports[days], backlog_csv)

    message = build_daily_message(reports[DAY_WINDOW_DAYS], reports[days], days)
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
