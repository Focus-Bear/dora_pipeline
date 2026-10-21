"""
Pure calculations for the QA, roadmap and release-velocity metrics.

Nothing in here touches the network, so every function can be unit-tested
with hand-built inputs (see tests/test_qa_metrics.py).

A board item, as produced by repo_summary.fetch_project_issues_for_repo, is a
dict with at least:
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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

UTC = timezone.utc

SECONDS_PER_DAY = 86400

# A dev-to-QA ratio at or above this means issues reach QA at least as fast
# as new ones are filed.
ROADMAP_AHEAD_RATIO = 1.0

INDICATOR_AHEAD = "✅"
INDICATOR_BEHIND = "⚠️"
NOT_AVAILABLE = "–"

ARROW_UP = "↑"
ARROW_DOWN = "↓"
ARROW_FLAT = "→"


@dataclass(frozen=True)
class StatusChange:
    at: datetime
    previous: Optional[str]
    current: Optional[str]


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


def count_in_statuses_now(items: Iterable[Dict[str, Any]], statuses: Sequence[str]) -> int:
    wanted = set(statuses)
    return sum(1 for item in items if item.get("status") in wanted)


def moved_into(
    item: Dict[str, Any],
    statuses: Sequence[str],
    since: datetime,
    required_previous: Optional[Sequence[str]] = None,
) -> bool:
    """
    Whether the item moved into one of `statuses` after `since`.

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
        if change.at <= since or change.current not in wanted or change.previous in wanted:
            continue
        if allowed_previous is not None and change.previous not in allowed_previous:
            continue
        return True

    return _moved_without_recorded_history(item, wanted, since, allowed_previous)


def _moved_without_recorded_history(
    item: Dict[str, Any],
    wanted: set,
    since: datetime,
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
    return bool(item.get("status") in wanted and status_updated and status_updated > since)


def count_moved_into(
    items: Iterable[Dict[str, Any]],
    statuses: Sequence[str],
    since: datetime,
    required_previous: Optional[Sequence[str]] = None,
) -> int:
    return sum(1 for item in items if moved_into(item, statuses, since, required_previous))


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


def progress_ratio(moved_to_qa: int, created: int) -> Optional[float]:
    """Issues moved to Ready for QA per new issue filed. None when nothing was filed."""
    if created <= 0:
        return None
    return moved_to_qa / created


def is_ahead(moved_to_qa: int, created: int) -> Optional[bool]:
    """Whether devs got more issues to QA than were filed. None when there was no activity."""
    if moved_to_qa == 0 and created == 0:
        return None
    ratio = progress_ratio(moved_to_qa, created)
    return ratio is None or ratio >= ROADMAP_AHEAD_RATIO


def progress_indicator(moved_to_qa: int, created: int) -> str:
    ahead = is_ahead(moved_to_qa, created)
    if ahead is None:
        return NOT_AVAILABLE
    return INDICATOR_AHEAD if ahead else INDICATOR_BEHIND


def format_ratio(moved_to_qa: int, created: int) -> str:
    ratio = progress_ratio(moved_to_qa, created)
    if ratio is None:
        return "∞" if moved_to_qa > 0 else NOT_AVAILABLE
    return f"{ratio:.2f}×"


def days_since(when: Optional[datetime], now: datetime) -> Optional[int]:
    """Whole days elapsed since `when` (never negative)."""
    if when is None:
        return None
    return max(0, math.floor((now - when).total_seconds() / SECONDS_PER_DAY))


def sum_optional(values: Iterable[Optional[int]]) -> Optional[int]:
    """Sum the known values; None when none are known."""
    known: List[int] = [value for value in values if value is not None]
    return sum(known) if known else None
