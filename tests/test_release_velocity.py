import unittest
from datetime import datetime

import release_velocity as rv
from qa_metrics import UTC

APPCAST = """<?xml version="1.0" standalone="yes"?>
<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle" version="2.0">
  <channel>
    <title>Focus Bear</title>
    <item>
      <title>3.35.535</title>
      <pubDate>Wed, 02 Sep 2026 10:19:53 +0530</pubDate>
      <sparkle:version>535</sparkle:version>
    </item>
    <item>
      <title>3.34.500</title>
      <pubDate>Mon, 03 Aug 2026 09:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

UPDATE_INI = """[application]
program_version=3.0.248.1
program_url=https://downloads.focusbear.io/FocusBearSetupWindows3.0.248.exe
program_size=
"""


class ParserTests(unittest.TestCase):
    def test_sparkle_newest_item(self):
        release = rv.parse_sparkle_appcast(APPCAST)
        self.assertEqual(release.version, "3.35.535")
        self.assertEqual(release.released_at, datetime(2026, 9, 2, 4, 49, 53, tzinfo=UTC))

    def test_sparkle_without_items(self):
        self.assertIsNone(rv.parse_sparkle_appcast("<rss><channel></channel></rss>"))

    def test_update_ini_version(self):
        self.assertEqual(rv.parse_update_ini_version(UPDATE_INI), "3.0.248.1")
        self.assertEqual(rv.parse_update_ini_version("[application]\n"), "")

    def test_app_store_lookup(self):
        release = rv.parse_app_store_lookup(
            {"results": [{"version": "1.24.2", "currentVersionReleaseDate": "2026-10-19T05:07:46Z"}]}
        )
        self.assertEqual(release.version, "1.24.2")
        self.assertEqual(release.released_at, datetime(2026, 10, 19, 5, 7, 46, tzinfo=UTC))
        self.assertIsNone(rv.parse_app_store_lookup({"results": []}))


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.original = dict(rv.FETCHERS)
        self.original_github = rv.fetch_github_release

    def tearDown(self):
        rv.FETCHERS.clear()
        rv.FETCHERS.update(self.original)
        rv.fetch_github_release = self.original_github

    def test_falls_back_to_github_when_the_signal_is_missing(self):
        fallback = rv.Release(datetime(2026, 1, 1, tzinfo=UTC), "v1", "GitHub release")
        rv.FETCHERS[rv.SOURCE_SPARKLE] = lambda source, repo: None
        rv.fetch_github_release = lambda source, repo: fallback
        self.assertEqual(rv.fetch_last_release("Focus-Bear/Mac-App", {"kind": rv.SOURCE_SPARKLE}), fallback)

    def test_errors_fall_back_too(self):
        def broken(source, repo):
            raise ValueError("bad feed")

        fallback = rv.Release(datetime(2026, 1, 1, tzinfo=UTC), "v1", "GitHub release")
        rv.FETCHERS[rv.SOURCE_UPDATE_INI] = broken
        rv.fetch_github_release = lambda source, repo: fallback
        self.assertEqual(rv.fetch_last_release("Focus-Bear/windows-app-v2", {"kind": rv.SOURCE_UPDATE_INI}), fallback)


if __name__ == "__main__":
    unittest.main()
