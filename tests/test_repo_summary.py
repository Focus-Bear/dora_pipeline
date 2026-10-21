import csv
import os
import tempfile
import unittest
from datetime import datetime, timedelta

import repo_summary as rs
from qa_metrics import UTC, StatusChange
from release_velocity import Release

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
MAC = next(repo for repo in rs.REPOS if repo["short_name"] == "Mac-App")
EXTENSION = next(repo for repo in rs.REPOS if repo["qa"] is None)


def board_item(status, events, item_updated):
    return {
        "id": "I_1",
        "number": 1,
        "status": status,
        "status_updated_at": events[-1].at if events else None,
        "item_created_at": NOW - timedelta(days=100),
        "item_updated_at": item_updated,
        "events": events,
    }


class CountQueryTests(unittest.TestCase):
    def test_queries_per_window(self):
        queries = rs.count_queries("Focus-Bear/Mac-App", [1, 7], NOW)
        self.assertEqual(queries["prs_open"], "repo:Focus-Bear/Mac-App is:pr is:open")
        self.assertEqual(queries["prs_merged_1d"], "repo:Focus-Bear/Mac-App is:pr is:merged merged:>=2026-10-21T12:00:00Z")
        self.assertEqual(queries["bugs_created_7d"], "repo:Focus-Bear/Mac-App is:issue label:bug created:>=2026-10-15T12:00:00Z")
        self.assertEqual(len(queries), 3 + 3 * 2)


class StatusChangeParsingTests(unittest.TestCase):
    def test_keeps_only_this_boards_changes_in_order(self):
        node = {
            "id": "I_1",
            "timelineItems": {
                "pageInfo": {"hasNextPage": False},
                "nodes": [
                    {"createdAt": "2026-10-21T15:00:00Z", "previousStatus": "Ready for QA", "status": "QA Passed/Done", "project": {"number": 1}},
                    {"createdAt": "2026-10-20T15:00:00Z", "previousStatus": "", "status": "Ready for QA", "project": {"number": 1}},
                    {"createdAt": "2026-10-21T16:00:00Z", "previousStatus": "Todo", "status": "Done", "project": {"number": 99}},
                ],
            },
        }
        changes = rs._status_changes(node, 1)
        self.assertEqual([change.current for change in changes], ["Ready for QA", "QA Passed/Done"])
        self.assertIsNone(changes[0].previous)


class ReportRowTests(unittest.TestCase):
    def setUp(self):
        passed = board_item(
            "QA Passed/Done",
            [StatusChange(NOW - timedelta(hours=3), "Ready for QA", "QA Passed/Done")],
            NOW - timedelta(hours=3),
        )
        waiting = board_item(
            "Ready for QA",
            [StatusChange(NOW - timedelta(days=3), "In Progress", "Ready for QA")],
            NOW - timedelta(days=3),
        )
        self.inputs = rs.SummaryInputs(
            fetched_at=NOW,
            items_by_repo={"Mac-App": [passed, waiting], "chrome_extension": []},
            counts_by_repo={
                "Mac-App": {"prs_open": 15, "prs_draft": 2, "prs_approved": 1, "prs_merged_7d": 22,
                            "issues_created_7d": 27, "bugs_created_7d": 19},
                "chrome_extension": {"prs_open": 3},
            },
            releases_by_repo={"Mac-App": Release(NOW - timedelta(days=49, hours=2), "3.35.535", "Sparkle appcast")},
        )

    def test_qa_board_repo(self):
        row = rs.build_repo_row(MAC, 7, self.inputs)
        self.assertEqual(row["issues_ready_for_qa"], 1)
        self.assertEqual(row["ready_for_qa_1d_ago"], 2)
        self.assertEqual(row["ready_for_qa_7d_ago"], 1)
        self.assertEqual(row["issues_qa_completed"], 1)
        self.assertEqual(row["issues_qa_failed"], 0)
        self.assertEqual(row["issues_moved_to_ready_for_qa"], 1)
        self.assertEqual(row["prs_merged"], 22)
        self.assertEqual(row["days_since_last_release"], 49)
        self.assertEqual(row["release_version"], "3.35.535")

    def test_repo_without_qa_board(self):
        row = rs.build_repo_row(EXTENSION, 7, self.inputs)
        self.assertIsNone(row["issues_ready_for_qa"])
        self.assertIsNone(row["issues_qa_completed"])
        self.assertIsNone(row["days_since_last_release"])
        self.assertEqual(row["prs_open"], 3)

    def test_csv_keeps_legacy_columns_first_and_blanks_unknowns(self):
        rows = [rs.build_repo_row(MAC, 7, self.inputs), rs.build_repo_row(EXTENSION, 7, self.inputs)]
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "summary.csv")
            rs.write_csv(rows, path)
            with open(path, encoding="utf-8") as handle:
                header = handle.readline().strip().split(",")
                handle.seek(0)
                written = list(csv.DictReader(handle))
        self.assertEqual(header[:8], rs.CSV_FIELDNAMES[:8])
        self.assertEqual(written[1]["issues_ready_for_qa"], "")
        self.assertEqual(written[0]["ready_for_qa_1d_ago"], "2")


if __name__ == "__main__":
    unittest.main()
