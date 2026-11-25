import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from src.hourly import collect_hour, hour_start, write_snapshot, health_report
from src.publish_v2 import validate_hourly, render_hourly

class RecoveryTests(TestCase):
    def test_explicit_hour(self):
        now = datetime(2026, 11, 24, 23, 5, tzinfo=timezone.utc)
        with patch("src.hourly.crawl_source", return_value=([], {"handle": "x", "raw_count": 0, "pages": 1})) as crawl:
            result = collect_hour({"sources": [{"handle": "x", "name": "X"}]}, now=now,
                                  session=object(), hour_id="2026-11-24T21")
        self.assertEqual(result["hour_id"], "2026-11-24T21")
        self.assertEqual(result["generated_at_utc"], now.isoformat())
        self.assertEqual(crawl.call_args.args[3].hour, 21)
        with self.assertRaises(ValueError):
            hour_start("2026-11-24T23", now)

    def test_backfill_does_not_rewind_latest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for key in ["2026-11-24T22", "2026-11-24T21"]:
                write_snapshot({"hour_id": key, "posts": [{"url": "x"}]}, root)
            self.assertEqual(json.loads((root / "data/hourly/latest.json").read_text())["hour_id"], "2026-11-24T22")
            report = health_report(root, datetime(2026, 11, 24, 23, 5, tzinfo=timezone.utc))
            self.assertEqual(report["hours"][0]["status"], "awaiting_summary")
            self.assertEqual(report["hours"][2]["status"], "missing_snapshot")

    def test_repair_latest_without_rewriting_archive(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = {"hour_id": "2026-11-24T22", "posts": []}
            latest, archive = write_snapshot(snapshot, root)
            original = archive.read_bytes()
            latest.unlink()
            write_snapshot(snapshot, root)
            self.assertEqual(latest.read_bytes(), original)
            self.assertEqual(archive.read_bytes(), original)

    def test_delayed_brief_bounded_and_labeled(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = "2026-11-24T20"
            stamp = "2026-11-24T21:05:00+00:00"
            snapshot = {"hour_id": key, "generated_at_utc": stamp,
                        "window_start_utc": "2026-11-24T20:00:00+00:00",
                        "window_end_utc": "2026-11-24T21:00:00+00:00",
                        "posts": [{"url": "https://t.me/example/1"}]}
            write_snapshot(snapshot, root)
            path = Path("outbox/hourly") / (key + ".json")
            (root / path).parent.mkdir(parents=True)
            digest = {"type": "hourly", "hour_id": key, "snapshot_generated_at_utc": stamp,
                      "late_recovery": True, "items": [{"title": "Diplomatic meeting planned",
                      "summary": "Officials discussed preparations for a diplomatic meeting.",
                      "source_urls": ["https://t.me/example/1"]}]}
            (root / path).write_text(json.dumps(digest))
            now = datetime(2026, 11, 24, 23, 25, tzinfo=timezone.utc)
            valid, source = validate_hourly(path, root, now)
            self.assertIn("delayed hourly brief", render_hourly(valid, source)[0][0])
            with self.assertRaises(ValueError):
                validate_hourly(path, root, datetime(2026, 11, 25, 0, 1, tzinfo=timezone.utc))
            digest.pop("late_recovery")
            (root / path).write_text(json.dumps(digest))
            with self.assertRaises(ValueError):
                validate_hourly(path, root, now)

    def test_keyword_misses_reach_editorial_review(self):
        now = datetime(2026, 11, 25, 5, 5, tzinfo=timezone.utc)
        posts = [
            {"id": "x/1", "channel": "x", "url": "https://t.me/x/1",
             "text": "President announces a date for the next summit.",
             "published_at": "2026-11-25T04:05:00+00:00", "related_urls": []},
            {"id": "x/2", "channel": "x", "url": "https://t.me/x/2",
             "text": "Ukraine officials announce new military aid.",
             "published_at": "2026-11-25T04:10:00+00:00", "related_urls": []}
        ]
        config = {"sources": [{"handle": "x", "name": "X"}], "max_candidates": 10}
        with patch("src.hourly.crawl_source", return_value=(posts, {"handle": "x", "raw_count": 2, "pages": 1})):
            result = collect_hour(config, now=now, session=object())
            self.assertEqual(result["stats"]["relevant_posts"], 1)
            self.assertEqual(result["stats"]["retained_without_keyword_match"], 1)
            self.assertEqual(len(result["posts"]), 2)
            config["max_candidates"] = 1
            result = collect_hour(config, now=now, session=object())
            self.assertEqual(result["posts"][0]["id"], "x/2")
            self.assertEqual(result["stats"]["excluded_by_candidate_cap"], 1)
