import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from src.hourly import collect_hour, hour_start, write_snapshot, health_report

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
