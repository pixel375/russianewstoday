import unittest
from datetime import datetime, timedelta, timezone

from src.collect import parse_page, relevant, dedupe, crawl_source


class CollectionTests(unittest.TestCase):
    def sample(self, n, stamp, text):
        return (
            '<div class="tgme_widget_message" data-post="intelslava/' + str(n) + '">'
            '<div class="tgme_widget_message_text">' + text + '</div>'
            '<a class="tgme_widget_message_date"><time datetime="' + stamp + '">time</time></a>'
            '</div>'
        )

    def test_parse_canonical_post_and_time(self):
        stamp = "2026-11-16T13:45:00+00:00"
        page = self.sample(12, stamp, "Ukraine reports a drone attack on a military site.")
        entries = parse_page(page, "intelslava", "Intel Slava")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["url"], "https://t.me/intelslava/12")
        self.assertEqual(entries[0]["published_at"], stamp)

    def test_relevance(self):
        self.assertTrue(relevant("Ukraine officials report a drone strike against an air defense system."))
        self.assertTrue(relevant("Russian forces report a missile attack on military positions."))
        self.assertFalse(relevant("Russian research team develops a new cancer treatment."))
        self.assertFalse(relevant("Just in: India is experiencing a major pollution emergency."))

    def test_duplicate_sources_are_preserved(self):
        msg = "Ukraine's authorities reported a major drone attack on a weapons depot near the border."
        a = {"id": "intelslava/1", "url": "https://t.me/intelslava/1",
             "published_at": "2026-11-16T12:00:00+00:00", "text": msg, "related_urls": []}
        b = {"id": "DDGeopolitics/2", "url": "https://t.me/DDGeopolitics/2",
             "published_at": "2026-11-16T12:01:00+00:00", "text": msg, "related_urls": []}
        entries = dedupe([a, b])
        self.assertEqual(len(entries), 1)
        self.assertEqual(set([entries[0]["url"], *entries[0]["related_urls"]]), {"https://t.me/DDGeopolitics/2", "https://t.me/intelslava/1"})

    def test_crawl_pages_until_cutoff(self):
        now = datetime(2026, 11, 16, 16, tzinfo=timezone.utc)
        fresh = self.sample(51, (now - timedelta(hours=3)).isoformat(),
                            "Ukraine's defense ministry reported overnight missile strikes on the front.")
        old = self.sample(42, (now - timedelta(hours=25)).isoformat(),
                          "Ukraine and Russia held negotiations last week.")
        class FakeResponse:
            def __init__(self, text):
                self.text = text
            def raise_for_status(self):
                return None
        class FakeSession:
            def __init__(self):
                self.urls = []
            def get(self, url, timeout):
                self.urls.append(url)
                return FakeResponse(fresh if "before=" not in url else old)
        s = FakeSession()
        results, stats = crawl_source(s, "intelslava", "Intel Slava",
                                      now - timedelta(hours=24), now, 3)
        self.assertEqual(len(results), 1)
        self.assertEqual(stats["pages"], 2)
        self.assertTrue(s.urls[-1].endswith("?before=51"))


if __name__ == "__main__":
    unittest.main()
