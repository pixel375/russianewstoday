"""Publish evidence-checked hourly briefs and linked daily highlight indexes.

Telegram sees no original source names or source links. The original Telegram
post URLs remain in the outbox JSON and are checked against the source archive.
Daily links point only to our own earlier hourly messages.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from html import escape
import json
import os
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo

import requests
import subprocess

from .collect import ROOT

HOUR_PATH = re.compile(r"^outbox/hourly/(\d{4}-\d{2}-\d{2}T\d{2})\.json$")
DAY_PATH = re.compile(r"^outbox/daily/(\d{4}-\d{2}-\d{2})\.json$")
ORIGINAL_LINK = re.compile(r"^https://t\.me/[A-Za-z0-9_]+/\d+$")
DESTINATION = "russianewstodayofficial"
MAX_UNITS = 3300
FORBIDDEN_ORIGINAL_NAMES = re.compile(
    r"\b(?:DD\s*Geopolitics|Intel\s*Slava|BRICS\s*News|"
    r"Aussie\s*Cossack|TASS|RIA\s*Novosti|Rybar(?:\s*in\s*English)?|"
    r"Two\s*Majors|WarGonzo|Colonelcassad|Voenkor\s*Kotenok)\b", re.I)
CYRILLIC = re.compile(r"[\u0400-\u052F]")
LOCAL_TZ = ZoneInfo("America/Winnipeg")
# Maximum combined number of NABU/SAPO items per Winnipeg news day.
ANTI_CORRUPTION_HANDLES = frozenset(("nab_ukraine", "sap_gov_ua"))
ANTI_CORRUPTION_DAILY_MAX = 2



def units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def utc(iso: str) -> datetime:
    result = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"Missing timezone in {iso}")
    return result.astimezone(timezone.utc)


def validate_text(item: dict, n: int, hourly: bool) -> None:
    title = item.get("title")
    if not isinstance(title, str) or not 5 <= len(title) <= 180:
        raise ValueError(f"Item {n}: title must be 5–180 characters")
    if FORBIDDEN_ORIGINAL_NAMES.search(title):
        raise ValueError(f"Item {n}: do not mention original source channel in headline")
    if CYRILLIC.search(title):
        raise ValueError(f"Item {n}: write title in English, transliterating Russian names")
    if hourly:
        summary = item.get("summary")
        if not isinstance(summary, str) or not 16 <= len(summary) <= 800:
            raise ValueError(f"Item {n}: summary must be 16–800 characters")
        if FORBIDDEN_ORIGINAL_NAMES.search(summary):
            raise ValueError(f"Item {n}: do not mention original source channel in summary")
        if CYRILLIC.search(summary):
            raise ValueError(f"Item {n}: write summary in English, transliterating Russian names")


def validate_hourly(path: Path, root: Path, now: datetime) -> tuple[dict, dict]:
    match = HOUR_PATH.fullmatch(path.as_posix())
    if not match:
        raise ValueError(f"Invalid hourly outbox path: {path}")
    hour_id = match[1]
    digest = read_json(root / path)
    snapshot = read_json(root / "data/hourly" / (hour_id + ".json"))
    if digest.get("type") != "hourly" or digest.get("hour_id") != hour_id:
        raise ValueError("Hourly type/hour ID mismatch")
    if snapshot.get("hour_id") != hour_id or digest.get("snapshot_generated_at_utc") != snapshot.get("generated_at_utc"):
        raise ValueError("Hourly digest must reference the exact archived snapshot")
    if not 0 <= (now - utc(snapshot["generated_at_utc"])).total_seconds() < 2 * 3600:
        raise ValueError("Hourly source archive is stale or from the future")
    if utc(snapshot["window_end_utc"]) - utc(snapshot["window_start_utc"]) != timedelta(hours=1):
        raise ValueError("Source snapshot is not an exact one-hour window")
    if utc(snapshot["window_start_utc"]).strftime("%Y-%m-%dT%H") != hour_id:
        raise ValueError("Source start time does not match hour ID")
    items = digest.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 5:
        raise ValueError("Hourly digest requires 1–5 substantive points")
    originals = set()
    for post in snapshot.get("posts", []):
        originals.add(post["url"])
        originals.update(post.get("related_urls", []))
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Item {n}: not an object")
        validate_text(item, n, hourly=True)
        links = item.get("source_urls")
        if not isinstance(links, list) or not 1 <= len(links) <= 4:
            raise ValueError(f"Item {n}: 1–4 internal source URLs required")
        if any(not isinstance(link, str) or not ORIGINAL_LINK.fullmatch(link) or link not in originals for link in links):
            raise ValueError(f"Item {n}: original source URL missing from source snapshot")
    return digest, snapshot


def validate_daily(path: Path, root: Path, now: datetime) -> tuple[dict, dict]:
    match = DAY_PATH.fullmatch(path.as_posix())
    if not match:
        raise ValueError(f"Invalid daily outbox path: {path}")
    date = match[1]
    digest = read_json(root / path)
    index = read_json(root / "published/hourly_index" / (date + ".json"))
    if digest.get("type") != "daily" or digest.get("date") != date or index.get("date") != date:
        raise ValueError("Daily digest/index date or type mismatch")
    if (root / "published" / (date + ".json")).exists():
        raise ValueError("Legacy daily digest was already published for this date")
    # Daily indices describe a completed Winnipeg calendar day, including DST.
    local_now = now.astimezone(LOCAL_TZ).date()
    daily_date = datetime.strptime(date, "%Y-%m-%d").date()
    if not (timedelta(days=1) <= local_now - daily_date <= timedelta(days=3)):
        raise ValueError("Daily digest must summarize a recent completed local day")
    items = digest.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise ValueError("Daily highlights must contain 1–20 items")
    known = {item["item_id"]: item for item in index.get("items", [])}
    selected = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"item_id"} or item["item_id"] not in known:
            raise ValueError("Daily highlight points to an unknown or invalid hourly item ID")
        selected.append(known[item["item_id"]])
    if len({item["item_id"] for item in selected}) != len(selected):
        raise ValueError("Daily highlights include duplicate hourly item IDs")
    for n, item in enumerate(selected, 1):
        validate_text(item, n, hourly=True)
        if not re.fullmatch(r"https://t\.me/" + DESTINATION + r"/\d+", item["post_url"]):
            raise ValueError("Daily item link must point to our own earlier hourly message")
    return digest, {"selected": selected, "index": index}


def split_entries(header: str, continuation: str, entries: list[str]) -> tuple[list[str], list[int]]:
    messages = []
    indexes = []
    current = header
    for entry in entries:
        if units(current + entry) > MAX_UNITS:
            if current == header:
                raise ValueError("Individual point exceeds Telegram message budget")
            messages.append(current)
            current = continuation
        if units(current + entry) > MAX_UNITS:
            raise ValueError("Individual point exceeds Telegram message budget")
        indexes.append(len(messages))
        current += entry
    messages.append(current)
    count = len(messages)
    if count == 1:
        return messages, indexes
    return [s + "\n<i>Part " + str(i + 1) + "/" + str(count) + "</i>"
            for i, s in enumerate(messages)], indexes


def render_hourly(digest: dict, snapshot: dict) -> tuple[list[str], list[int]]:
    end = utc(snapshot["window_end_utc"]).strftime("%Y-%m-%d %H:%M UTC")
    header = "🇷🇺🇺🇦 <b>Russia–Ukraine War | Hourly Brief</b>\n" + end + " · previous hour\n"
    more = "🇷🇺🇺🇦 <b>Russia–Ukraine War | Hourly Brief (continued)</b>\n" + end + "\n"
    entries = []
    for item in digest["items"]:
        entries.append("\n• <b>" + escape(item["title"]) + "</b>\n" + escape(item["summary"]) + "\n")
    return split_entries(header, more, entries)


def render_daily(digest: dict, data: dict) -> tuple[list[str], list[int]]:
    header = "🇷🇺🇺🇦 <b>Russia–Ukraine War | Daily Brief</b>\n" + escape(digest["date"]) + " · daily highlights\n"
    more = "🇷🇺🇺🇦 <b>Russia–Ukraine War | Daily Brief (continued)</b>\n" + escape(digest["date"]) + "\n"
    entries = []
    for item in data["selected"]:
        entries.append("\n• <a href=\"" + escape(item["post_url"], quote=True) + "\">" +
                       escape(item["title"]) + "</a>\n")
    return split_entries(header, more, entries)


def safe_outbox(value: str) -> Path:
    if not (HOUR_PATH.fullmatch(value) or DAY_PATH.fullmatch(value)):
        raise ValueError(f"Not a supported digest path: {value}")
    return Path(value)


def path_from_github_event(event: Path) -> Path:
    payload = read_json(event)
    candidates = set()
    commits = payload.get("commits") or []
    if not commits and payload.get("head_commit"):
        commits = [payload["head_commit"]]
    for commit in commits:
        for name in commit.get("added", []) + commit.get("modified", []):
            if HOUR_PATH.fullmatch(name) or DAY_PATH.fullmatch(name):
                candidates.add(name)
    if not candidates:
        # Some GitHub-created commits arrive with no file list in the push
        # payload. Inspect the checked-out commit as a reliable fallback.
        # actions/checkout uses fetch-depth: 2 to include its parent.
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        candidates.update(
            name for name in result.stdout.splitlines()
            if HOUR_PATH.fullmatch(name) or DAY_PATH.fullmatch(name)
        )
    if len(candidates) != 1:
        raise ValueError(f"Push must change exactly one supported outbox JSON (found {len(candidates)})")
    return safe_outbox(next(iter(candidates)))


def send_messages(messages: list[str], token: str, chat_id: str) -> list[int]:
    ids = []
    for i, message in enumerate(messages, 1):
        response = requests.post(
            "https://api.telegram.org/bot" + token + "/sendMessage",
            json={
                "chat_id": chat_id, "text": message, "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok") or "message_id" not in result.get("result", {}):
            raise RuntimeError(f"Telegram rejected message part {i}: {result.get('description')}")
        ids.append(int(result["result"]["message_id"]))
        if i < len(messages):
            time.sleep(1)
    return ids


def item_source_handles(item: dict) -> list[str]:
    """Exact source handles from validator-approved, internal source URLs."""
    return sorted({url.split("/")[3].casefold()
                   for url in item.get("source_urls", [])
                   if ORIGINAL_LINK.fullmatch(url)})


def is_anticorruption_item(item: dict) -> bool:
    return bool(set(item_source_handles(item)) & ANTI_CORRUPTION_HANDLES)


def apply_anticorruption_daily_cap(root: Path, digest: dict,
                                   snapshot: dict) -> tuple[dict, int]:
    """Keep at most two official NABU/SAPO stories per Winnipeg news date.

    The publication index persists across hourly workflows. Only genuinely
    published entries count; one story citing both agencies counts as one.
    Rejected overflow does not block unrelated war news in the same hour.
    """
    local_date = utc(snapshot["window_start_utc"]).astimezone(LOCAL_TZ).date().isoformat()
    file = root / "published/hourly_index" / (local_date + ".json")
    previous = read_json(file) if file.exists() else {"items": []}
    used = sum(bool(set(entry.get("source_handles", [])) &
                    ANTI_CORRUPTION_HANDLES) for entry in previous["items"])
    remaining = max(0, ANTI_CORRUPTION_DAILY_MAX - used)
    kept = []
    skipped = 0
    for item in digest["items"]:
        if is_anticorruption_item(item):
            if not remaining:
                skipped += 1
                continue
            remaining -= 1
        kept.append(item)
    return {**digest, "items": kept}, skipped


def update_hourly_index(root: Path, digest: dict, snapshot: dict,
                        item_parts: list[int], message_ids: list[int]) -> tuple[dict, dict]:
    hour_id = digest["hour_id"]
    local_date = utc(snapshot["window_start_utc"]).astimezone(LOCAL_TZ).date().isoformat()
    file = root / "published/hourly_index" / (local_date + ".json")
    existing = read_json(file) if file.exists() else {"date": local_date, "items": []}
    all_items = existing["items"]
    receipts = []
    for n, (item, part) in enumerate(zip(digest["items"], item_parts), 1):
        message_id = message_ids[part]
        entry = {
            "item_id": f"{hour_id}:{n}",
            "title": item["title"],
            "summary": item["summary"],
            "post_url": f"https://t.me/{DESTINATION}/{message_id}",
            "category": item.get("category", "other"),
            "hour_id": hour_id,
            "source_handles": item_source_handles(item),
        }
        receipts.append(entry)
        if not any(x["item_id"] == entry["item_id"] for x in all_items):
            all_items.append(entry)
    return {"date": local_date, "items": all_items}, {"type": "hourly", "hour_id": hour_id, "items": receipts}


def publish(path: Path, root: Path, dry_run: bool = False,
            now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    path = safe_outbox(path.as_posix())
    kind = "hourly" if HOUR_PATH.fullmatch(path.as_posix()) else "daily"
    identifier = path.stem
    receipt_path = root / "published" / kind / (identifier + ".json")
    if receipt_path.exists():
        print("Already published:", receipt_path)
        return {"already_published": True}
    skipped_by_quota = 0
    if kind == "hourly":
        digest, data = validate_hourly(path, root, now)
        digest, skipped_by_quota = apply_anticorruption_daily_cap(root, digest, data)
        if not digest["items"]:
            # Mark an all-quota-capped hour as handled, without contacting
            # Telegram and without inserting it into the published index.
            if dry_run:
                print(f"All {skipped_by_quota} NABU/SAPO stories exceed the daily cap; nothing to publish.")
                return {"dry_run": True, "message_count": 0, "skipped_by_quota": skipped_by_quota}
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt = {"type": "hourly", "hour_id": identifier,
                       "status": "skipped_source_quota", "message_ids": [],
                       "items": [], "skipped_by_quota": skipped_by_quota}
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
            print("No Telegram post: all official anti-corruption items exceeded the daily cap.")
            return receipt
        messages, part_indexes = render_hourly(digest, data)
    else:
        digest, data = validate_daily(path, root, now)
        messages, part_indexes = render_daily(digest, data)
    print(f"Validated {kind} digest {identifier}: {len(digest['items'])} points, {len(messages)} Telegram messages"
          f"; NABU/SAPO quota-skipped={skipped_by_quota}")
    if dry_run:
        for i, msg in enumerate(messages, 1):
            print(f"\n--- Preview {i}/{len(messages)} ---\n{msg}")
        return {"dry_run": True, "message_count": len(messages)}
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or chat != "@" + DESTINATION:
        raise RuntimeError("Missing bot token or mismatched destination channel")
    message_ids = send_messages(messages, token, chat)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "type": kind, "message_ids": message_ids,
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
        "channel": chat,
    }
    if kind == "hourly":
        index, detail = update_hourly_index(root, digest, data, part_indexes, message_ids)
        receipt.update(detail)
        receipt["skipped_by_quota"] = skipped_by_quota
        date = index["date"]
        index_path = root / "published/hourly_index" / (date + ".json")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        receipt["date"] = identifier
        receipt["hourly_item_ids"] = [it["item_id"] for it in digest["items"]]
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Telegram post successful; receipt:", receipt_path)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--path", help="outbox/hourly/ID.json or outbox/daily/DATE.json")
    group.add_argument("--event", type=Path, help="GitHub push event JSON")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    publish(safe_outbox(args.path) if args.path else path_from_github_event(args.event),
            ROOT, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
