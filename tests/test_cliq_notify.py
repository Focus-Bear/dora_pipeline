import unittest
from datetime import datetime

import cliq_notify
from qa_metrics import UTC, BacklogEntry


def row(name, **values):
    base = {
        "display_name": name,
        "prs_open": 0,
        "prs_merged": 0,
        "prs_merged_prev": 0,
        "issues_created": 0,
        "issues_created_prev": 0,
        "bugs_created": 0,
        "issues_ready_for_qa": None,
        "ready_for_qa_7d_ago": None,
        "issues_qa_failed": None,
        "issues_qa_failed_prev": None,
        "issues_qa_tested": None,
        "issues_qa_tested_prev": None,
        "qa_backlog_median_days": None,
        "qa_backlog_oldest_days": None,
        "qa_backlog": [],
        "days_since_last_release": None,
        "release_version": None,
    }
    base.update(values)
    return base


def waiting(number, age_days):
    return BacklogEntry(
        number=number,
        title=f"Issue {number}",
        url=f"https://github.com/Focus-Bear/Mac-App/issues/{number}",
        repository="Focus-Bear/Mac-App",
        status="Ready for QA",
        waiting_since=datetime(2026, 1, 1, tzinfo=UTC),
        age_days=age_days,
    )


MAC = row(
    "Mac", prs_open=12, prs_merged=15, prs_merged_prev=31, issues_created=16, issues_created_prev=33,
    bugs_created=11, issues_ready_for_qa=59, ready_for_qa_7d_ago=48, issues_qa_failed=5,
    issues_qa_failed_prev=1, issues_qa_tested=40, issues_qa_tested_prev=30, qa_backlog_median_days=54,
    qa_backlog_oldest_days=1210, qa_backlog=[waiting(750, 1210), waiting(759, 1204), waiting(776, 1191), waiting(800, 9)],
    days_since_last_release=69, release_version="3.35.535",
)
LINUX = row(
    "Linux", prs_open=4, issues_ready_for_qa=0, ready_for_qa_7d_ago=0, issues_qa_tested=2, issues_qa_tested_prev=0,
    days_since_last_release=95,
)
EXTENSION = row("Browser Extension", prs_open=7, issues_created_prev=1)


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.message = cliq_notify.build_daily_message([MAC, LINUX, EXTENSION], 7)

    def test_sections_in_order(self):
        positions = [self.message.index(heading) for heading in ("*1. Dev velocity*", "*2. Quality*", "*3. QA backlog*", "_Appendix")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('_Last 7 days; "prev" is the 7 days before that._', self.message)
        self.assertNotIn("to QA vs", self.message)

    def test_dev_velocity(self):
        self.assertIn("*1. Dev velocity* — 15 PRs merged (prev 31, ↓16) · 23 PRs open", self.message)
        self.assertIn("• *Mac* — 15 merged (prev 31) · 12 open", self.message)
        self.assertIn("• *Browser Extension* — 0 merged (prev 0) · 7 open", self.message)

    def test_quality(self):
        # Linux has no QA Failed column, so its tested issues stay out of the failure rate.
        self.assertIn(
            "*2. Quality* — 16 new issues (prev 34, ↓18), 11 labelled bug · QA failed 5 of 40 tested (12%) (prev 1 of 30)",
            self.message,
        )
        self.assertIn("• *Mac* — 16 new issues (prev 33) · QA failed 5 of 40 tested (12%) (prev 1 of 30)", self.message)
        self.assertIn("• *Linux* — 0 new issues (prev 0) · no QA Failed column", self.message)
        self.assertIn("• *Browser Extension* — 0 new issues (prev 1)", self.message)

    def test_qa_backlog_lists_oldest_first(self):
        self.assertIn("*3. QA backlog* — 59 issues in Ready for QA (↑11 vs 7d ago) · oldest waiting 1210d", self.message)
        self.assertIn(
            "• *Mac* — 59 waiting (↑11 vs 7d ago) · median wait 54d · oldest "
            "[#750](https://github.com/Focus-Bear/Mac-App/issues/750) 1210d, "
            "[#759](https://github.com/Focus-Bear/Mac-App/issues/759) 1204d, "
            "[#776](https://github.com/Focus-Bear/Mac-App/issues/776) 1191d",
            self.message,
        )
        self.assertNotIn("#800", self.message)
        self.assertIn("• *Linux* — 0 waiting (→ vs 7d ago)\n", self.message)
        self.assertNotIn("*Browser Extension* — 0 waiting", self.message)

    def test_release_appendix(self):
        self.assertIn("_Appendix — days since last release:_ Mac 69d (3.35.535) · Linux 95d", self.message)

    def test_no_qa_boards(self):
        message = cliq_notify.build_daily_message([EXTENSION], 7)
        self.assertNotIn("QA backlog", message)
        self.assertNotIn("Appendix", message)
        self.assertIn("0 labelled bug · no QA Failed column", message)


if __name__ == "__main__":
    unittest.main()
