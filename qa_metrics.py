"""
Pure calculations for the QA, QA-backlog and release-velocity metrics.

Nothing in here touches the network, so every function can be unit-tested
with hand-built inputs (see tests/test_qa_metrics.py).

A board item, as produced by repo_summary.fetch_project_issues_for_repo, is a
dict with at least:
    number, title, url, repository   the issue, for the QA backlog listing
    status             current Status option name (or None)
    status_updated_at  datetime the current Status value was set (or None)
    item_created_at    datetime the issue was added to the board (or None)
    item_updated_at    datetime any field on the board item last changed (or None)
    events             list of StatusChange, oldest first, for changes made
                       since the event-history cutoff; None when the history
                       was not fetched (the item has not changed since then)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

UTC = timezone.utc

SECONDS_PER_DAY = 86400

NOT_AVAILABLE = "–"

ARROW_UP = "↑"
ARROW_DOWN = "↓"
ARROW_FLAT = "→"


@dataclass(frozen=True)
class StatusChange:
    at: datetime
    previous: Optional[str]
    current: Optional[str]


@dataclass(frozen=True)
class BacklogEntry:
    """An issue waiting in a Ready for QA column, and for how long."""

    number: Optional[int]
    title: str
    url: str
    repository: str
    status: str
    waiting_since: Optional[datetime]
    age_days: Optional[int]


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse a GitHub ISO-8601 timestamp ("...Z") into an aware UTC datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, TypeError):
        return None


def status_at(item: Dict[str, Any], at: datetime) -> Optional[str]:
    """
    The Status the item had at time `at`, reconstructed from its change history.

    The first change after `at` records what the status was before it; with no
    change after `at` the status is still the current one. Returns None when
    the item was not on the board yet, or had no status.
    """
    created = item.get("item_created_at")
    if created and created > at:
        return None

    updated = item.get("item_updated_at")
    if updated is None or updated <= at:
        return item.get("status")

    later = [change for change in item.get("events") or [] if change.at > at]
    if later:
        return later[0].previous or None

    status_updated = item.get("status_updated_at")
    if status_updated and status_updated > at:
        # The status changed after `at` but no history was recorded for it,
        # so what it was before is unknown.
        return None
    return item.get("status")


def count_in_statuses_at(items: Iterable[Dict[str, Any]], statuses: Sequence[str], at: datetime) -> int:
    wanted = set(statuses)
    return sum(1 for item in items if status_at(item, at) in wanted)


def _in_window(at: datetime, since: datetime, until: Optional[datetime]) -> bool:
    return at > since and (until is None or at <= until)


def moved_into(
    item: Dict[str, Any],
    statuses: Sequence[str],
    since: datetime,
    required_previous: Optional[Sequence[str]] = None,
    until: Optional[datetime] = None,
) -> bool:
    """
    Whether the item moved into one of `statuses` after `since` (and no later
    than `until`, when given).

    Moves between two options of the same group (e.g. the two "Ready for QA"
    options some boards have) do not count. When `required_previous` is given
    the move only counts from one of those statuses.
    """
    wanted = set(statuses)
    if not wanted:
        return False
    allowed_previous = set(required_previous) if required_previous else None

    events = item.get("events") or []
    for change in events:
        if not _in_window(change.at, since, until) or change.current not in wanted or change.previous in wanted:
            continue
        if allowed_previous is not None and change.previous not in allowed_previous:
            continue
        return True

    return _moved_without_recorded_history(item, wanted, since, until, allowed_previous)


def _moved_without_recorded_history(
    item: Dict[str, Any],
    wanted: set,
    since: datetime,
    until: Optional[datetime],
    allowed_previous: Optional[set],
) -> bool:
    """
    Fall back to the current Status value's timestamp when GitHub recorded no
    change event for it. The previous status is unknown then, so a move that
    must come from particular statuses cannot be confirmed.
    """
    if allowed_previous is not None or item.get("events"):
        return False
    status_updated = item.get("status_updated_at")
    return bool(item.get("status") in wanted and status_updated and _in_window(status_updated, since, until))


def count_moved_into(
    items: Iterable[Dict[str, Any]],
    statuses: Sequence[str],
    since: datetime,
    required_previous: Optional[Sequence[str]] = None,
    until: Optional[datetime] = None,
) -> int:
    return sum(1 for item in items if moved_into(item, statuses, since, required_previous, until))


def count_tested(
    items: Iterable[Dict[str, Any]],
    passed: Sequence[str],
    failed: Sequence[str],
    in_qa: Sequence[str],
    since: datetime,
    until: Optional[datetime] = None,
) -> int:
    """
    Issues QA finished with in the window: moved out of an `in_qa` status into
    `passed` or `failed` (a failure may also come out of `passed`). Each issue
    counts once, whether it passed, failed or both.
    """
    failed_from = list(in_qa) + list(passed)
    return sum(
        1
        for item in items
        if moved_into(item, passed, since, in_qa, until) or moved_into(item, failed, since, failed_from, until)
    )


def waiting_since(item: Dict[str, Any]) -> Optional[datetime]:
    """When the item got its current Status (falls back to when it joined the board)."""
    return item.get("status_updated_at") or item.get("item_created_at")


def qa_backlog(items: Iterable[Dict[str, Any]], statuses: Sequence[str], now: datetime) -> List[BacklogEntry]:
    """Items currently in one of `statuses`, oldest wait first (unknown ages last)."""
    wanted = set(statuses)
    entries = [
        BacklogEntry(
            number=item.get("number"),
            title=item.get("title") or "",
            url=item.get("url") or "",
            repository=item.get("repository") or "",
            status=item.get("status") or "",
            waiting_since=waiting_since(item),
            age_days=days_since(waiting_since(item), now),
        )
        for item in items
        if item.get("status") in wanted
    ]
    return sorted(entries, key=lambda entry: (entry.age_days is None, -(entry.age_days or 0)))


def median_age_days(entries: Sequence[BacklogEntry]) -> Optional[int]:
    ages = [entry.age_days for entry in entries if entry.age_days is not None]
    return int(statistics.median(ages)) if ages else None


def oldest_age_days(entries: Sequence[BacklogEntry]) -> Optional[int]:
    ages = [entry.age_days for entry in entries if entry.age_days is not None]
    return max(ages) if ages else None


def trend_label(current: Optional[int], previous: Optional[int]) -> str:
    """"↑3", "↓2" or "→" comparing a count with its earlier value."""
    if current is None or previous is None:
        return NOT_AVAILABLE
    delta = current - previous
    if delta > 0:
        return f"{ARROW_UP}{delta}"
    if delta < 0:
        return f"{ARROW_DOWN}{-delta}"
    return ARROW_FLAT


def days_since(when: Optional[datetime], now: datetime) -> Optional[int]:
    """Whole days elapsed since `when` (never negative)."""
    if when is None:
        return None
    return max(0, math.floor((now - when).total_seconds() / SECONDS_PER_DAY))


def percent(part: Optional[int], whole: Optional[int]) -> Optional[int]:
    """`part` as a whole-number percentage of `whole`; None when it cannot be computed."""
    if part is None or not whole:
        return None
    return round(100 * part / whole)


def sum_optional(values: Iterable[Optional[int]]) -> Optional[int]:
    """Sum the known values; None when none are known."""
    known: List[int] = [value for value in values if value is not None]
    return sum(known) if known else None
