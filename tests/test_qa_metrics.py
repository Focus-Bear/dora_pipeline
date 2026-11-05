import unittest
from datetime import datetime, timedelta

import qa_metrics as q
from qa_metrics import UTC, StatusChange

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
READY = ["Ready for QA"]
PASSED = ["QA Passed/Done"]


def hours_ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


def item(status, events=None, created_hours_ago=1000, updated_hours_ago=None, status_hours_ago=None):
    """A board item; updated_at defaults to the newest event (or long ago)."""
    newest_event = max((change.at for change in events or []), default=None)
    return {
        "status": status,
        "status_updated_at": hours_ago(status_hours_ago) if status_hours_ago is not None else newest_event,
        "item_created_at": hours_ago(created_hours_ago),
        "item_updated_at": hours_ago(updated_hours_ago) if updated_hours_ago is not None else (newest_event or hours_ago(900)),
        "events": events,
    }


def change(hours, previous, current):
    return StatusChange(hours_ago(hours), previous, current)


class StatusAtTests(unittest.TestCase):
    def test_unchanged_item_keeps_current_status(self):
        self.assertEqual(q.status_at(item("Ready for QA"), hours_ago(24)), "Ready for QA")

    def test_status_before_a_later_change_is_its_previous_value(self):
        moved = item("QA Passed/Done", [change(5, "Ready for QA", "QA Passed/Done")])
        self.assertEqual(q.status_at(moved, hours_ago(24)), "Ready for QA")
        self.assertEqual(q.status_at(moved, hours_ago(1)), "QA Passed/Done")

    def test_uses_first_change_after_the_time(self):
        hopped = item("Done", [
            change(30, "In Progress", "Ready for QA"),
            change(10, "Ready for QA", "QA in Progress"),
            change(2, "QA in Progress", "Done"),
        ])
        self.assertEqual(q.status_at(hopped, hours_ago(48)), "In Progress")
        self.assertEqual(q.status_at(hopped, hours_ago(24)), "Ready for QA")
        self.assertEqual(q.status_at(hopped, hours_ago(5)), "QA in Progress")

    def test_item_added_after_the_time_had_no_status(self):
        self.assertIsNone(q.status_at(item("Ready for QA", created_hours_ago=3), hours_ago(24)))

    def test_empty_previous_status_means_none(self):
        added = item("Ready for QA", [change(3, None, "Ready for QA")], created_hours_ago=200)
        self.assertIsNone(q.status_at(added, hours_ago(24)))

    def test_other_field_changes_do_not_change_status(self):
        edited = item("Ready for QA", events=[], updated_hours_ago=2)
        self.assertEqual(q.status_at(edited, hours_ago(24)), "Ready for QA")

    def test_status_change_without_history_is_unknown(self):
        unrecorded = item("Ready for QA", events=[], updated_hours_ago=2, status_hours_ago=2)
        self.assertIsNone(q.status_at(unrecorded, hours_ago(24)))


class CountTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            item("Ready for QA"),
            item("QA Passed/Done", [change(5, "Ready for QA", "QA Passed/Done")]),
            item("Ready for QA", [change(30, "In Progress", "Ready for QA")]),
            item("QA Failed", [change(3, "QA in Progress", "QA Failed")]),
            item("In Progress"),
        ]

    def test_counts_now_and_in_the_past(self):
        self.assertEqual(q.count_in_statuses_now(self.items, READY), 2)
        self.assertEqual(q.count_in_statuses_at(self.items, READY, hours_ago(24)), 3)
        self.assertEqual(q.count_in_statuses_at(self.items, READY, hours_ago(48)), 2)

    def test_moves_within_window(self):
        self.assertEqual(q.count_moved_into(self.items, PASSED, hours_ago(24)), 1)
        self.assertEqual(q.count_moved_into(self.items, ["QA Failed"], hours_ago(24)), 1)
        self.assertEqual(q.count_moved_into(self.items, READY, hours_ago(24)), 0)
        self.assertEqual(q.count_moved_into(self.items, READY, hours_ago(24 * 7)), 1)

    def test_move_between_options_of_the_same_group_is_ignored(self):
        duplicate = item("Ready for QA", [change(2, "Ready for QA", "Ready for QA")])
        self.assertFalse(q.moved_into(duplicate, READY, hours_ago(24)))

    def test_required_previous_status(self):
        closed_from_qa = item("Done/Closed", [change(2, "QA", "Done/Closed")])
        closed_from_backlog = item("Done/Closed", [change(2, "Backlog", "Done/Closed")])
        self.assertTrue(q.moved_into(closed_from_qa, ["Done/Closed"], hours_ago(24), ["Ready for QA", "QA"]))
        self.assertFalse(q.moved_into(closed_from_backlog, ["Done/Closed"], hours_ago(24), ["Ready for QA", "QA"]))

    def test_falls_back_to_status_timestamp_without_history(self):
        unrecorded = item("QA Passed/Done", events=[], updated_hours_ago=2, status_hours_ago=2)
        self.assertTrue(q.moved_into(unrecorded, PASSED, hours_ago(24)))
        self.assertFalse(q.moved_into(unrecorded, PASSED, hours_ago(24), ["Ready for QA"]))

    def test_empty_status_group_never_matches(self):
        self.assertEqual(q.count_moved_into(self.items, [], hours_ago(24)), 0)


class TrendTests(unittest.TestCase):
    def test_trend_label(self):
        self.assertEqual(q.trend_label(10, 7), "↑3")
        self.assertEqual(q.trend_label(7, 10), "↓3")
        self.assertEqual(q.trend_label(5, 5), "→")
        self.assertEqual(q.trend_label(None, 5), q.NOT_AVAILABLE)
        self.assertEqual(q.trend_label(5, None), q.NOT_AVAILABLE)


class RoadmapTests(unittest.TestCase):
    def test_ratio(self):
        self.assertAlmostEqual(q.progress_ratio(3, 4), 0.75)
        self.assertIsNone(q.progress_ratio(3, 0))

    def test_indicator(self):
        self.assertEqual(q.progress_indicator(5, 4), q.INDICATOR_AHEAD)
        self.assertEqual(q.progress_indicator(4, 4), q.INDICATOR_AHEAD)
        self.assertEqual(q.progress_indicator(3, 4), q.INDICATOR_BEHIND)
        self.assertEqual(q.progress_indicator(2, 0), q.INDICATOR_AHEAD)
        self.assertEqual(q.progress_indicator(0, 0), q.NOT_AVAILABLE)

    def test_format_ratio(self):
        self.assertEqual(q.format_ratio(1, 2), "0.50×")
        self.assertEqual(q.format_ratio(2, 0), "∞")
        self.assertEqual(q.format_ratio(0, 0), q.NOT_AVAILABLE)


class DaysSinceTests(unittest.TestCase):
    def test_whole_days(self):
        self.assertEqual(q.days_since(NOW - timedelta(days=3, hours=23), NOW), 3)
        self.assertEqual(q.days_since(NOW - timedelta(hours=1), NOW), 0)

    def test_future_or_missing(self):
        self.assertEqual(q.days_since(NOW + timedelta(hours=5), NOW), 0)
        self.assertIsNone(q.days_since(None, NOW))


class HelperTests(unittest.TestCase):
    def test_parse_iso(self):
        self.assertEqual(q.parse_iso("2026-10-21T15:28:29Z"), datetime(2026, 10, 21, 15, 28, 29, tzinfo=UTC))
        self.assertIsNone(q.parse_iso(""))
        self.assertIsNone(q.parse_iso("not a date"))

    def test_sum_optional(self):
        self.assertEqual(q.sum_optional([1, None, 2]), 3)
        self.assertIsNone(q.sum_optional([None, None]))


if __name__ == "__main__":
    unittest.main()
