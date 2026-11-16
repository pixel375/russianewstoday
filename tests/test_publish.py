import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timezone

from src.publish import load_digest, render_messages, units, MAX_UNITS


class PublisherTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        stamp = "2026-11-16T16:00:00+00:00"
        snapshot = {
            "snapshot_date": "2026-11-16", "generated_at_utc": stamp,
            "posts": [{"url": "https://t.me/intelslava/123", "related_urls": []}]
        }
        digest = {
            "date": "2026-11-16", "snapshot_generated_at_utc": stamp,
            "items": [{"category": "frontline", "title": "Reported front-line changes",
                       "summary": "A report said positions changed in one sector; independent verification remains pending.",
                       "source_urls": ["https://t.me/intelslava/123"]}]
        }
        sp = root / "latest.json"
        dp = root / "2026-11-16.json"
        sp.write_text(json.dumps(snapshot))
        dp.write_text(json.dumps(digest))
        return dp, sp, digest

    def test_valid_and_safe_render(self):
        with TemporaryDirectory() as d:
            dp, sp, _ = self.fixture(d)
            result = load_digest(dp, sp, datetime(2026, 11, 16, 17, tzinfo=timezone.utc))
            rendered = render_messages(result)
            self.assertEqual(len(rendered), 1)
            self.assertIn('href="https://t.me/intelslava/123"', rendered[0])
            self.assertLess(units(rendered[0]), MAX_UNITS + 80)

    def test_reject_fabricated_link(self):
        with TemporaryDirectory() as d:
            dp, sp, digest = self.fixture(d)
            digest["items"][0]["source_urls"] = ["https://t.me/fakechannel/456"]
            dp.write_text(json.dumps(digest))
            with self.assertRaisesRegex(ValueError, "not from collected"):
                load_digest(dp, sp, datetime(2026, 11, 16, 17, tzinfo=timezone.utc))

    def test_reject_stale_snapshot(self):
        with TemporaryDirectory() as d:
            dp, sp, _ = self.fixture(d)
            with self.assertRaisesRegex(ValueError, "older than"):
                load_digest(dp, sp, datetime(2026, 11, 20, tzinfo=timezone.utc))

    def test_long_digest_is_split(self):
        items = []
        for i in range(30):
            items.append({"category": "frontline", "title": f"Development {i} in the field",
                          "summary": "A detailed report about a specific war-related event. " * 8,
                          "source_urls": ["https://t.me/intelslava/123"]})
        digest = {"date": "2026-11-16", "items": items}
        chunks = render_messages(digest)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(units(c) <= MAX_UNITS + 90 for c in chunks))


if __name__ == "__main__":
    unittest.main()
