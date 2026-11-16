import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from src.hourly import collect_hour
from src.publish_v2 import (
    HOUR_PATH, DAY_PATH, validate_hourly, validate_daily, render_hourly,
    render_daily, path_from_github_event, split_entries, units,
    MAX_UNITS, update_hourly_index,
)


class HourlyTests(TestCase):
    def test_completed_hour_window(self):
        now = datetime(2026, 11, 17, 15, 19, tzinfo=timezone.utc)
        calls = []
        def fake_crawl(session, handle, name, start, end, max_pages):
            calls.append((start, end))
            return [], {"handle": handle, "pages": 2, "raw_count": 0}
        with patch("src.hourly.crawl_source", side_effect=fake_crawl):
            data = collect_hour({"sources": [{"handle": "x", "name": "X"}]},
                                now=now, session=object())
        self.assertEqual(data["hour_id"], "2026-11-17T14")
        self.assertEqual(calls[0], (datetime(2026, 11, 17, 14, tzinfo=timezone.utc),
                                    datetime(2026, 11, 17, 15, tzinfo=timezone.utc)))
        self.assertEqual(data["posts"], [])

    def test_hourly_sources_internal_only(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "outbox/hourly").mkdir(parents=True)
            (root / "data/hourly").mkdir(parents=True)
            key = "2026-11-16T14"
            time = "2026-11-16T15:05:00+00:00"
            snapshot = {"hour_id": key, "generated_at_utc": time,
                        "window_start_utc": "2026-11-16T14:00:00+00:00",
                        "window_end_utc": "2026-11-16T15:00:00+00:00",
                        "posts": [{"url": "https://t.me/DDGeopolitics/999", "related_urls": []}]}
            digest = {"type": "hourly", "hour_id": key,
                      "snapshot_generated_at_utc": time, "items": [{
                          "title": "Diplomatic discussion expected",
                          "summary": "A diplomatic meeting may include the Ukraine conflict as a discussion topic.",
                          "source_urls": ["https://t.me/DDGeopolitics/999"]
                      }]}
            (root / "data/hourly" / (key + ".json")).write_text(json.dumps(snapshot))
            path = Path("outbox/hourly") / (key + ".json")
            (root / path).write_text(json.dumps(digest))
            actual, source = validate_hourly(path, root, datetime(2026, 11, 16, 16, tzinfo=timezone.utc))
            messages, parts = render_hourly(actual, source)
            self.assertEqual(parts, [0])
            self.assertIn("Diplomatic discussion expected", messages[0])
            self.assertNotIn("DDGeopolitics", messages[0])
            self.assertNotIn("https://t.me/", messages[0])
            self.assertTrue(all(units(m) < MAX_UNITS + 100 for m in messages))
            index, receipt = update_hourly_index(root, actual, source, parts, [123])
            self.assertEqual(index["items"][0]["post_url"], "https://t.me/russianewstodayofficial/123")
            self.assertEqual(receipt["items"][0]["item_id"], key + ":1")
            actual["items"][0]["summary"] = "DD Geopolitics reports this with no evidence."
            (root / path).write_text(json.dumps(actual))
            with self.assertRaisesRegex(ValueError, "original source channel"):
                validate_hourly(path, root, datetime(2026, 11, 16, 16, tzinfo=timezone.utc))

    def test_long_points_split(self):
        msgs, positions = split_entries("Header\n", "More\n", ["hi\n" * 700] * 3)
        self.assertEqual(positions, [0, 1, 2])
        self.assertEqual(len(msgs), 3)

    def test_push_event_selects_file(self):
        with TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({"commits": [{"added": [
                "README.md", "outbox/hourly/2026-11-16T14.json"
            ], "modified": []}]}))
            self.assertEqual(str(path_from_github_event(event)),
                             "outbox/hourly/2026-11-16T14.json")


class DailyTests(TestCase):
    def test_daily_links_only_to_hourly_messages(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "outbox/daily").mkdir(parents=True)
            (root / "published/hourly_index").mkdir(parents=True)
            date = "2026-11-16"
            item = {"item_id": "2026-11-16T14:1", "title": "Expected diplomatic meeting",
                    "summary": "A scheduled meeting may cover Ukraine and other matters.",
                    "category": "diplomacy",
                    "post_url": "https://t.me/russianewstodayofficial/777"}
            (root / "published/hourly_index" / (date + ".json")).write_text(
                json.dumps({"date": date, "items": [item]}))
            path = Path("outbox/daily") / (date + ".json")
            (root / path).write_text(json.dumps({"type": "daily", "date": date, "items": [
                {"item_id": item["item_id"]}
            ]}))
            digest, index = validate_daily(path, root, datetime(2026, 11, 17, 7, tzinfo=timezone.utc))
            rendered, _ = render_daily(digest, index)
            self.assertIn("https://t.me/russianewstodayofficial/777", rendered[0])
            self.assertNotIn("DDGeopolitics", rendered[0])
            self.assertNotIn("source 1", rendered[0])

    def test_expected_paths(self):
        self.assertIsNotNone(HOUR_PATH.fullmatch("outbox/hourly/2026-11-16T14.json"))
        self.assertIsNotNone(DAY_PATH.fullmatch("outbox/daily/2026-11-16.json"))
        self.assertIsNone(HOUR_PATH.fullmatch("outbox/2026-11-16.json"))
