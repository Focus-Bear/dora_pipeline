import unittest

import cliq_notify


def row(name, **values):
    base = {
        "display_name": name,
        "prs_open": 0,
        "prs_draft": 0,
        "prs_approved": 0,
        "prs_merged": 0,
        "issues_ready_for_qa": None,
        "ready_for_qa_1d_ago": None,
        "ready_for_qa_7d_ago": None,
        "issues_qa_completed": None,
        "issues_qa_failed": None,
        "issues_moved_to_ready_for_qa": None,
        "issues_created": 0,
        "bugs_created": 0,
        "days_since_last_release": None,
        "release_version": None,
    }
    base.update(values)
    return base


MAC = row(
    "Mac", prs_open=15, prs_draft=2, prs_approved=1, prs_merged=3, issues_ready_for_qa=66,
    ready_for_qa_1d_ago=70, ready_for_qa_7d_ago=83, issues_qa_completed=4, issues_qa_failed=1,
    issues_moved_to_ready_for_qa=2, issues_created=8, bugs_created=5, days_since_last_release=49,
    release_version="3.35.535",
)
BACKEND = row(
    "Backend", prs_open=22, prs_merged=5, issues_ready_for_qa=167, ready_for_qa_1d_ago=160,
    ready_for_qa_7d_ago=152, issues_qa_completed=0, issues_moved_to_ready_for_qa=6, issues_created=3,
    days_since_last_release=0, release_version="181691f",
)
EXTENSION = row("Browser Extension", prs_open=3)


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.message = cliq_notify.build_daily_message([(1, [MAC, BACKEND, EXTENSION])])

    def test_window_totals(self):
        self.assertIn("*Last 24h* — *PRs merged:* 8", self.message)
        self.assertIn("*QA:* ✅ 4 passed / ❌ 1 failed", self.message)
        self.assertIn("*Roadmap:* 8 to QA vs 11 new (5 bugs) ⚠️ 0.73×", self.message)

    def test_per_repo_lines(self):
        self.assertIn("• *Mac* — 3 PRs merged · QA ✅ 4 ❌ 1 · 2 to QA vs 8 new ⚠️", self.message)
        self.assertIn("• *Backend* — 5 PRs merged · QA ✅ 0 ❌ – · 6 to QA vs 3 new ✅", self.message)
        self.assertNotIn("• *Browser Extension* —", self.message)

    def test_ready_for_qa_trend(self):
        self.assertIn("*📥 Ready for QA:* 233 (↑3 vs 24h · ↓2 vs 7d)", self.message)
        self.assertIn("• *Mac* 66 (↓4 vs 24h · ↓17 vs 7d)", self.message)
        self.assertNotIn("• *Browser Extension* 0", self.message)

    def test_open_prs_and_releases(self):
        self.assertIn("*🔀 Open PRs:* 40 (2 draft · 1 approved)", self.message)
        self.assertIn("Backend 22 · Mac 15 · Browser Extension 3", self.message)
        self.assertIn("Backend 0d (181691f) · Mac 49d (3.35.535)", self.message)

    def test_quiet_window(self):
        quiet = cliq_notify.build_daily_message([(7, [EXTENSION])])
        self.assertIn("_No PRs merged, QA moves or new issues._", quiet)
        self.assertNotIn("Ready for QA:", quiet)
        self.assertNotIn("Days since last release", quiet)


if __name__ == "__main__":
    unittest.main()
