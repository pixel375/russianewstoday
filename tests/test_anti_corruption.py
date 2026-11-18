"""NABU and SAPO source-specific discovery and combined daily publishing cap."""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from src.collect import relevant, quality_score
from src.hourly import collect_hour
from src.publish_v2 import (
    apply_anticorruption_daily_cap, is_anticorruption_item,
    item_source_handles, update_hourly_index, validate_text, publish
)
from unittest.mock import patch


NABU = "https://t.me/nab_ukraine/1234"
SAPO = "https://t.me/sap_gov_ua/7890"
OTHER = "https://t.me/rian_ru/111"


def story(url, title):
    return {
        "title": title,
        "summary": "Officials announced developments involving a Ukrainian public corruption inquiry.",
        "source_urls": [url]
    }


class AntiCorruptionSourceTests(unittest.TestCase):
    def test_permissive_source_specific_ukrainian_filter(self):
        text = "Оголошено про підозру високопосадовцю"  # No explicit Ukraine/war term
        self.assertFalse(relevant(text))
        self.assertTrue(relevant(text, "nab_ukraine"))
        self.assertTrue(relevant(text, "SAP_GOV_UA"))
        self.assertFalse(relevant("Ні", "nab_ukraine"))
        self.assertFalse(relevant("win a casino jackpot here", "nab_ukraine"))

    def test_official_post_ranked_higher(self):
        post = {"text": "Оголошено про підозру високопосадовцю", "channel": "nab_ukraine"}
        ordinary = dict(post, channel="other")
        self.assertGreater(quality_score(post), quality_score(ordinary))

    def test_direct_official_attribution_is_allowed(self):
        validate_text({"title": "NABU reports corruption investigation",
                       "summary": "SAPO reports prosecutors have taken a procedural step in the case."},
                      1, hourly=True)

    def test_two_per_day_across_both_sources_preserves_other_items(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "published/hourly_index").mkdir(parents=True)
            date = "2026-11-18"
            existing = {"date": date, "items": [
                {"item_id": "old:1", "source_handles": ["nab_ukraine"]},
            ]}
            (root / "published/hourly_index" / (date + ".json")).write_text(json.dumps(existing))
            snapshot = {"window_start_utc": "2026-11-18T15:00:00+00:00"}
            digest = {"hour_id": "2026-11-18T15", "items": [
                story(NABU, "NABU inquiry A"),
                story(SAPO, "SAPO inquiry B"),
                story(OTHER, "Other political development")
            ]}
            updated, skipped = apply_anticorruption_daily_cap(root, digest, snapshot)
            self.assertEqual(skipped, 1)
            self.assertEqual([x["title"] for x in updated["items"]],
                             ["NABU inquiry A", "Other political development"])
            self.assertEqual(len(digest["items"]), 3)  # Input left intact

            # Follow-on hour: there are now two counted official stories.
            existing["items"].append({"item_id": "new:1",
                                      "source_handles": ["sap_gov_ua"]})
            (root / "published/hourly_index" / (date + ".json")).write_text(json.dumps(existing))
            updated, skipped = apply_anticorruption_daily_cap(root, digest, snapshot)
            self.assertEqual(skipped, 2)
            self.assertEqual([x["title"] for x in updated["items"]],
                             ["Other political development"])

    def test_two_sources_on_one_article_count_as_one_story(self):
        item = story(NABU, "Shared investigation")
        item["source_urls"].append(SAPO)
        self.assertEqual(set(item_source_handles(item)), {"nab_ukraine", "sap_gov_ua"})
        self.assertTrue(is_anticorruption_item(item))
        self.assertFalse(is_anticorruption_item(story(OTHER, "Other event")))

    def test_new_calendar_day_resets_limit(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "published/hourly_index").mkdir(parents=True)
            (root / "published/hourly_index/2026-11-18.json").write_text(
                json.dumps({"date": "2026-11-18", "items": [
                    {"source_handles": ["nab_ukraine"]},
                    {"source_handles": ["sap_gov_ua"]}
                ]}))
            digest = {"items": [story(NABU, "New-day investigation")]}
            snapshot = {"window_start_utc": "2026-11-19T16:00:00+00:00"}
            updated, skipped = apply_anticorruption_daily_cap(root, digest, snapshot)
            self.assertEqual(skipped, 0)
            self.assertEqual(len(updated["items"]), 1)

    def test_published_index_records_internal_handles_only(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest = {"hour_id": "2026-11-18T16", "items": [
                story(NABU, "NABU publishes investigation update")
            ]}
            snap = {"window_start_utc": "2026-11-18T16:00:00+00:00"}
            index, receipt = update_hourly_index(root, digest, snap, [0], [456])
            self.assertEqual(index["items"][0]["source_handles"], ["nab_ukraine"])
            self.assertEqual(index["items"][0]["post_url"],
                             "https://t.me/russianewstodayofficial/456")
            self.assertEqual(receipt["items"][0]["source_handles"], ["nab_ukraine"])

    def test_quota_only_hour_writes_skip_receipt_without_telegram(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/hourly").mkdir(parents=True)
            (root / "outbox/hourly").mkdir(parents=True)
            (root / "published/hourly_index").mkdir(parents=True)
            hr = "2026-11-18T16"
            tm = "2026-11-18T17:20:00+00:00"
            snapshot = {
                "hour_id": hr, "generated_at_utc": tm,
                "window_start_utc": "2026-11-18T16:00:00+00:00",
                "window_end_utc": "2026-11-18T17:00:00+00:00",
                "posts": [{"url": NABU, "related_urls": []}]
            }
            (root / "data/hourly" / (hr+".json")).write_text(json.dumps(snapshot))
            index = {"date": "2026-11-18", "items": [
                {"source_handles": ["nab_ukraine"]},
                {"source_handles": ["sap_gov_ua"]}
            ]}
            (root / "published/hourly_index/2026-11-18.json").write_text(json.dumps(index))
            outbox = Path("outbox/hourly") / (hr+".json")
            (root / outbox).write_text(json.dumps({
                "type": "hourly", "hour_id": hr,
                "snapshot_generated_at_utc": tm,
                "items": [story(NABU, "NABU inquiry update")]
            }))
            with patch("src.publish_v2.send_messages", side_effect=AssertionError("No Telegram send")):
                receipt = publish(outbox, root, dry_run=False,
                                  now=datetime(2026, 11, 18, 17, 23, tzinfo=timezone.utc))
            self.assertEqual(receipt["status"], "skipped_source_quota")
            self.assertEqual(receipt["message_ids"], [])
            self.assertTrue((root / "published/hourly" / (hr+".json")).exists())


if __name__ == "__main__":
    unittest.main()
