import unittest
from datetime import datetime

import cliq_notify
from qa_metrics import UTC, BacklogEntry


def row(name, **values):
    base = {
        "repo_name": f"Focus-Bear/{name}",
        "display_name": name,
        "prs_open": 0,
        "prs_merged": 0,
        "issues_created": 0,
        "issues_new": 0,
        "issues_found_by_qa": None,
        "issues_moved_to_ready_for_qa": None,
        "issues_ready_for_qa": None,
        "ready_for_qa_1d_ago": None,
        "ready_for_qa_7d_ago": None,
        "issues_qa_completed": None,
        "issues_qa_failed": None,
        "issues_qa_tested": None,
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


BACKLOG = dict(
    issues_ready_for_qa=59, ready_for_qa_1d_ago=61, ready_for_qa_7d_ago=48, qa_backlog_median_days=54,
    qa_backlog_oldest_days=1210, qa_backlog=[waiting(750, 1210), waiting(759, 1204), waiting(776, 1191), waiting(800, 9)],
    days_since_last_release=69, release_version="3.35.535",
)
MAC_WEEK = row(
    "Mac", prs_open=12, prs_merged=15, issues_created=16, issues_new=13, issues_found_by_qa=3,
    issues_moved_to_ready_for_qa=9, issues_qa_completed=35, issues_qa_failed=5, issues_qa_tested=40, **BACKLOG,
)
MAC_DAY = row(
    "Mac", prs_open=12, prs_merged=2, issues_created=1, issues_new=1, issues_found_by_qa=0,
    issues_moved_to_ready_for_qa=1, issues_qa_completed=4, issues_qa_failed=1, issues_qa_tested=5, **BACKLOG,
)
# Most of the web board's new issues are bugs QA filed straight into QA Failed.
WEB_WEEK = row(
    "Web Dashboard", prs_open=136, prs_merged=51, issues_created=60, issues_new=4, issues_found_by_qa=56,
    issues_moved_to_ready_for_qa=20, issues_qa_completed=60, issues_qa_failed=19, issues_qa_tested=79,
    issues_ready_for_qa=82, ready_for_qa_1d_ago=80, ready_for_qa_7d_ago=146, qa_backlog_oldest_days=957,
)
WEB_DAY = row(
    "Web Dashboard", prs_open=136, prs_merged=3, issues_created=2, issues_new=0, issues_found_by_qa=2,
    issues_moved_to_ready_for_qa=0, issues_qa_completed=0, issues_qa_failed=0, issues_qa_tested=0,
    issues_ready_for_qa=82, ready_for_qa_1d_ago=80, ready_for_qa_7d_ago=146, qa_backlog_oldest_days=957,
)
LINUX_WEEK = row(
    "Linux", prs_open=4, issues_ready_for_qa=0, ready_for_qa_1d_ago=0, ready_for_qa_7d_ago=0,
    issues_moved_to_ready_for_qa=0, issues_qa_completed=2, issues_qa_tested=2, days_since_last_release=95,
)
LINUX_DAY = row(
    "Linux", prs_open=4, issues_ready_for_qa=0, ready_for_qa_1d_ago=0, ready_for_qa_7d_ago=0,
    issues_moved_to_ready_for_qa=0, issues_qa_completed=0, issues_qa_tested=0, days_since_last_release=95,
)
EXTENSION_WEEK = row("Browser Extension", prs_open=7, issues_created=1, issues_new=1)
EXTENSION_DAY = row("Browser Extension", prs_open=7)

WEEK = [WEB_WEEK, MAC_WEEK, LINUX_WEEK, EXTENSION_WEEK]
DAY = [WEB_DAY, MAC_DAY, LINUX_DAY, EXTENSION_DAY]


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.message = cliq_notify.build_daily_message(DAY, WEEK, 7)

    def test_sections_in_order(self):
        headings = ("*1. Dev velocity*", "*2. QA velocity*", "*3. New issues vs QA failed*", "*4. QA backlog*", "_Appendix")
        positions = [self.message.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("prev", self.message)

    def test_legend_explains_every_figure(self):
        self.assertIn("_Each figure is *last 24 hours / last 7 days*._", self.message)
        for term in ("*merged*", "*to QA*", "*tested*", "*new issues*", "*QA failed*", "*waiting*"):
            self.assertIn(term + " = ", self.message)

    def test_dev_velocity_shows_24_hours_and_7_days(self):
        self.assertIn("*1. Dev velocity* — merged 5 / 66 · to QA 1 / 29 · 159 PRs open now", self.message)
        self.assertIn("• *Mac* — merged 2 / 15 · to QA 1 / 9 · 12 open", self.message)
        # No QA board, so no "to QA".
        self.assertIn("• *Browser Extension* — merged 0 / 0 · 7 open", self.message)

    def test_qa_velocity_shows_24_hours_and_7_days(self):
        self.assertIn("*2. QA velocity* — tested 5 / 121 · passed 4 / 97 · failed 1 / 24", self.message)
        self.assertIn("• *Web Dashboard* — tested 0 / 79 · passed 0 / 60 · failed 0 / 19", self.message)
        self.assertIn("• *Linux* — tested 0 / 2 · passed 0 / 2 · no QA Failed column", self.message)
        self.assertNotIn("*Browser Extension* — tested", self.message)

    def test_new_issues_are_separate_from_qa_failed(self):
        self.assertIn(
            "*3. New issues vs QA failed* — new issues 1 / 18 · QA failed 3 / 83 (7d: 24 failed re-test, 59 found by QA)",
            self.message,
        )
        self.assertIn(
            "• *Web Dashboard* — new issues 0 / 4 · QA failed 2 / 75 (7d: 19 failed re-test, 56 found by QA)",
            self.message,
        )
        self.assertIn("• *Mac* — new issues 1 / 13 · QA failed 1 / 8 (7d: 5 failed re-test, 3 found by QA)", self.message)
        self.assertIn("• *Browser Extension* — new issues 0 / 1\n", self.message)
        self.assertNotIn("*Linux* — new issues", self.message)

    def test_qa_backlog_compares_with_24_hours_and_7_days_ago(self):
        self.assertIn(
            "*4. QA backlog* — 141 waiting in Ready for QA (→ vs 24h ago, ↓53 vs 7d ago) · oldest waiting 1210d",
            self.message,
        )
        self.assertIn(
            "• *Mac* — 59 waiting (↓2 vs 24h ago, ↑11 vs 7d ago) · median wait 54d · oldest "
            "[#750](https://github.com/Focus-Bear/Mac-App/issues/750) 1210d, "
            "[#759](https://github.com/Focus-Bear/Mac-App/issues/759) 1204d, "
            "[#776](https://github.com/Focus-Bear/Mac-App/issues/776) 1191d",
            self.message,
        )
        self.assertNotIn("#800", self.message)
        self.assertIn("• *Linux* — 0 waiting (→ vs 24h ago, → vs 7d ago)\n", self.message)
        self.assertNotIn("*Browser Extension* — 0 waiting", self.message)

    def test_repos_keep_the_same_order_in_every_section(self):
        for section in self.message.split("\n\n"):
            names = [name for name in ("*Web Dashboard*", "*Mac*", "*Linux*", "*Browser Extension*") if name in section]
            self.assertEqual(names, sorted(names, key=section.index))

    def test_release_appendix(self):
        self.assertIn("_Appendix — days since last release:_ Mac 69d (3.35.535) · Linux 95d", self.message)

    def test_no_qa_boards(self):
        message = cliq_notify.build_daily_message([EXTENSION_DAY], [EXTENSION_WEEK], 7)
        self.assertNotIn("QA velocity", message)
        self.assertNotIn("QA backlog", message)
        self.assertNotIn("Appendix", message)
        self.assertIn("*3. New issues vs QA failed* — new issues 0 / 1 · QA failed – / –", message)

    def test_missing_24_hour_row_shows_unknown(self):
        message = cliq_notify.build_daily_message([], [MAC_WEEK], 7)
        self.assertIn("• *Mac* — merged – / 15", message)


class QaFailedCountTests(unittest.TestCase):
    def test_adds_retest_failures_and_bugs_found_by_qa(self):
        self.assertEqual(cliq_notify.qa_failed_count(MAC_WEEK), 8)
        self.assertEqual(cliq_notify.qa_failed_count(row("x", issues_qa_failed=2)), 2)
        self.assertIsNone(cliq_notify.qa_failed_count(EXTENSION_WEEK))


if __name__ == "__main__":
    unittest.main()
