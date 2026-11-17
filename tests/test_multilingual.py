"""Russian-language filtering, translated repost hints, and English publication."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.collect import parse_page, relevant, event_signals, annotate_possible_translations
from src.hourly import collect_hour
from src.publish_v2 import validate_text


class MultilingualCoverageTests(unittest.TestCase):
    def test_russian_ukraine_corruption_and_defence_procurement(self):
        self.assertTrue(relevant("На Украине расследуют коррупцию при военных закупках в Министерстве обороны."))
        self.assertTrue(relevant("В Киеве начались обыски по делу о взятках при закупке дронов."))
        self.assertTrue(relevant("Ukraine corruption investigation alleges bribery involving military procurement."))
        self.assertTrue(relevant("Ukrainian parliament debates the economic cost of EU sanctions and aid."))
        self.assertFalse(relevant("Russian research team develops a cancer treatment."))
        self.assertFalse(relevant("Just in: India is experiencing a major pollution emergency."))

    def test_preserves_context_of_long_original_posts(self):
        original = "На Украине расследуют коррупцию и закупки. " * 160
        html = ('<div class="tgme_widget_message" data-post="rian_ru/42">'
                '<div class="tgme_widget_message_text">' + original + '</div>'
                '<a class="tgme_widget_message_date"><time datetime="2026-11-17T14:01:00+00:00">'
                'time</time></a></div>')
        post = parse_page(html, "rian_ru", "RIA Novosti")[0]
        self.assertGreater(len(post["text"]), 1100)
        self.assertEqual(len(post["text"]), 4800)
        self.assertTrue(post["text_truncated"])

    def test_cross_language_hints_are_non_destructive(self):
        a = {
            "url": "https://t.me/rian_ru/100",
            "text": "В Киеве коррупционный скандал вокруг закупок и дронов для армии.",
            "published_at": "2026-11-17T12:02:00+00:00",
        }
        b = {
            "url": "https://t.me/rybar_in_english/110",
            "text": "Kyiv corruption scandal involves drone procurement for the army.",
            "published_at": "2026-11-17T12:06:00+00:00",
        }
        self.assertTrue({"kyiv","corruption","drone","procurement"}.issubset(set(event_signals(a["text"]))))
        result = annotate_possible_translations([a, b])
        self.assertEqual(len(result), 2)
        self.assertIn(b["url"], result[0]["possible_duplicate_urls"])
        self.assertIn(a["url"], result[1]["possible_duplicate_urls"])

    def test_mark_unavailable_channel_without_losing_all_sources(self):
        config = {"sources": [{"handle": "first", "name": "First"},
                              {"handle": "broken", "name": "Broken"},
                              {"handle": "third", "name": "Third"}],
                  "min_success_sources": 2}
        now = datetime(2026, 11, 17, 15, 20, tzinfo=timezone.utc)
        def fake_crawl(session, handle, name, start, end, max_pages):
            if handle == "broken":
                raise RuntimeError("Public preview returned HTTP 503")
            return [], {"handle": handle, "name": name, "pages": 1, "raw_count": 0}
        with patch("src.hourly.crawl_source", side_effect=fake_crawl):
            result = collect_hour(config, now=now, session=object())
        self.assertEqual(len(result["sources"]), 2)
        self.assertFalse(result["coverage_complete"])
        self.assertEqual(result["source_failures"][0]["handle"], "broken")
        config["min_success_sources"] = 3
        with patch("src.hourly.crawl_source", side_effect=fake_crawl):
            with self.assertRaisesRegex(RuntimeError, "refusing incomplete collection"):
                collect_hour(config, now=now, session=object())

    def test_only_english_titles_and_summaries_published(self):
        good = {"title": "Corruption inquiry in Ukraine's military procurement",
                "summary": "The inquiry reportedly concerns inflated prices for drones and spare parts."}
        validate_text(good, 1, hourly=True)
        for item in [
            dict(good, title="В Киеве расследуют коррупцию"),
            dict(good, summary="По данным следствия, закупки дронов были завышены."),
            dict(good, summary="Rybar claims this and other officials agree."),
        ]:
            with self.assertRaises(ValueError):
                validate_text(item, 1, hourly=True)


if __name__ == "__main__":
    unittest.main()
