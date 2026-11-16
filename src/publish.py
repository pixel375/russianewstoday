"""Validate ChatGPT-prepared digests and post them to Telegram in safe chunks."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = {
    "frontline": "⚔️ Frontline developments",
    "strikes": "🚀 Strikes and military operations",
    "equipment": "🛡️ Air defense and military equipment",
    "international": "🌍 International support and sanctions",
    "diplomacy": "🤝 Diplomacy and negotiations",
    "other": "📌 Other important developments",
}
SAFE_POST = re.compile(r"^https://t\.me/([A-Za-z0-9_]+)/(\d+)$")
MAX_UNITS = 3400


def load_digest(path: Path, snapshot_path: Path, now: datetime | None = None) -> dict:
    digest = json.loads(path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
        raise ValueError("Outbox filename must be YYYY-MM-DD.json")
    if digest.get("date") != path.stem or digest["date"] != snapshot.get("snapshot_date"):
        raise ValueError("Digest date must match filename and latest collection")
    if digest.get("snapshot_generated_at_utc") != snapshot.get("generated_at_utc"):
        raise ValueError("Digest must reference exactly the latest collection")
    generated = datetime.fromisoformat(snapshot["generated_at_utc"])
    if generated.tzinfo is None or not (0 <= (now - generated).total_seconds() <= 48 * 3600):
        raise ValueError("Collection is missing, future-dated, or older than 48 hours")
    items = digest.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 35:
        raise ValueError("Expected between 1 and 35 verified news points")
    known_urls = set()
    for post in snapshot.get("posts", []):
        known_urls.add(post["url"])
        known_urls.update(post.get("related_urls", []))
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict) or item.get("category") not in SECTIONS:
            raise ValueError(f"Item {idx}: invalid category")
        if (not isinstance(item.get("title"), str) or
                not 5 <= len(item["title"]) <= 180):
            raise ValueError(f"Item {idx}: title must be 5-180 characters")
        if (not isinstance(item.get("summary"), str) or
                not 12 <= len(item["summary"]) <= 700):
            raise ValueError(f"Item {idx}: summary must be 12-700 characters")
        urls = item.get("source_urls")
        if not isinstance(urls, list) or not 1 <= len(urls) <= 4:
            raise ValueError(f"Item {idx}: provide 1-4 source links")
        for u in urls:
            if not isinstance(u, str) or not SAFE_POST.fullmatch(u) or u not in known_urls:
                raise ValueError(f"Item {idx}: source URL is not from collected posts: {u}")
    return digest


def units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def render_messages(digest: dict) -> list[str]:
    items = digest["items"]
    title = "🇷🇺🇺🇦 <b>Russia–Ukraine War | Daily Brief</b>\n"
    title += "<b>" + escape(digest["date"]) + "</b> · previous 24 hours\n"
    title += "<i>Reported claims are attributed; not independently verified unless stated.</i>\n"
    chunks: list[str] = []
    current = title
    current_section = None
    for n, item in enumerate(items, 1):
        category = item["category"]
        section = "\n<b>" + escape(SECTIONS[category]) + "</b>\n" if category != current_section else ""
        links = " · ".join(
            '<a href="' + escape(u, quote=True) + '">source ' + str(i) + "</a>"
            for i, u in enumerate(item["source_urls"], 1)
        )
        point = ("\n<b>" + str(n) + ". " + escape(item["title"]) + "</b>\n" +
                 escape(item["summary"]) + "\n" + links + "\n")
        if units(current + section + point) > MAX_UNITS:
            if current == title:
                raise ValueError(f"Item {n} too long for one Telegram message")
            chunks.append(current)
            current = ("🇷🇺🇺🇦 <b>Russia–Ukraine War | " +
                       escape(digest["date"]) + " (continued)</b>\n")
            section = "\n<b>" + escape(SECTIONS[category]) + "</b>\n"
        if units(current + section + point) > MAX_UNITS:
            raise ValueError(f"Item {n} too long for one Telegram message")
        current += section + point
        current_section = category
    if current.strip():
        chunks.append(current)
    return [
        chunk + "\n<i>Part " + str(i) + "/" + str(len(chunks)) + "</i>"
        for i, chunk in enumerate(chunks, 1)
    ]


def send_messages(messages: list[str], token: str, chat_id: str) -> list[int]:
    ids = []
    for index, content in enumerate(messages, 1):
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": content,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        r.raise_for_status()
        payload = r.json()
        if not payload.get("ok") or not payload.get("result", {}).get("message_id"):
            raise RuntimeError(f"Telegram refused message {index}: {payload.get('description', '')}")
        ids.append(int(payload["result"]["message_id"]))
        if index < len(messages):
            time.sleep(1.0)
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD; defaults to latest snapshot date")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    snapshot_path = ROOT / "data/latest.json"
    if not snapshot_path.exists():
        raise SystemExit("data/latest.json does not exist; run collector first")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    date = args.date or snapshot["snapshot_date"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise SystemExit("Invalid digest date")
    outbox = ROOT / "outbox" / (date + ".json")
    receipt = ROOT / "published" / (date + ".json")
    if receipt.exists():
        print(f"Already published {date}; refusing duplicate")
        return
    digest = load_digest(outbox, snapshot_path)
    messages = render_messages(digest)
    print(f"Validated {len(digest['items'])} points; {len(messages)} messages")
    if args.dry_run:
        for i, msg in enumerate(messages, 1):
            print(f"\n--- Preview {i}/{len(messages)} ---\n{msg}")
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        raise SystemExit("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    message_ids = send_messages(messages, token, chat)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({
        "date": date,
        "snapshot_generated_at_utc": digest["snapshot_generated_at_utc"],
        "message_ids": message_ids,
        "channel": chat,
        "published_at_utc": datetime.now(timezone.utc).isoformat()
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Successfully posted {len(message_ids)} Telegram messages")


if __name__ == "__main__":
    main()
