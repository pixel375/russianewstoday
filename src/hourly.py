"""Collect the *last completed UTC hour* from public Telegram HTML previews.

On any failure to cover the full hour, fail closed rather than publish a partial
brief. Empty or irrelevant hours are stored as valid empty snapshots.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import math
from pathlib import Path

from .collect import make_session, crawl_source, relevant, dedupe, pick_candidates, annotate_possible_translations, ROOT

LOG = logging.getLogger("russianewstoday.hourly")


def hour_start(hour_id: str, now: datetime) -> datetime:
    start = datetime.strptime(hour_id, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
    if start.strftime("%Y-%m-%dT%H") != hour_id or start + timedelta(hours=1) > now:
        raise ValueError("Requested hour must be an exact completed UTC hour")
    return start


def collect_hour(config: dict, now: datetime | None = None, session=None,
                 hour_id: str | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    end = now.replace(minute=0, second=0, microsecond=0)
    start = hour_start(hour_id, now) if hour_id else end - timedelta(hours=1)
    end = start + timedelta(hours=1)
    hour_id = start.strftime("%Y-%m-%dT%H")
    session = session or make_session()
    all_posts: list[dict] = []
    stats: list[dict] = []
    failed = []
    for source in config["sources"]:
        try:
            posts, stat = crawl_source(
                session, source["handle"], source["name"],
                start, end, int(config.get("max_pages_per_source", 40)),
            )
        except Exception as exc:
            # More sources must not let one unavailable public preview shut
            # down the entire hourly channel. Mark the gap explicitly.
            LOG.warning("Source %s unavailable: %s", source["handle"], exc)
            failed.append({"handle": source["handle"], "reason": str(exc)[:180]})
            continue
        all_posts.extend(posts)
        stats.append(stat)
        LOG.info("%s: %d posts from %d pages", stat["handle"], stat["raw_count"], stat["pages"])
    min_sources = int(config.get("min_success_sources", 1))
    if len(stats) < min_sources:
        raise RuntimeError(f"Only {len(stats)}/{len(config['sources'])} sources complete; "
                           f"need at least {min_sources}; refusing incomplete collection")
    filtered = [p for p in all_posts if relevant(p["text"], p.get("channel", ""))]
    unique = dedupe(filtered)
    candidates = annotate_possible_translations(
        pick_candidates(unique, int(config.get("max_candidates", 150))))
    return {
        "schema_version": 2,
        "hour_id": hour_id,
        "generated_at_utc": now.isoformat(),
        "window_start_utc": start.isoformat(),
        "window_end_utc": end.isoformat(),
        "sources": stats,
        "source_failures": failed,
        "coverage_complete": not failed,
        "stats": {
            "raw_posts": len(all_posts),
            "relevant_posts": len(filtered),
            "deduplicated_posts": len(unique),
            "candidate_posts": len(candidates),
        },
        "posts": candidates,
    }


def write_snapshot(result: dict, root: Path = ROOT) -> tuple[Path, Path]:
    folder = root / "data/hourly"
    folder.mkdir(parents=True, exist_ok=True)
    latest = folder / "latest.json"
    archive = folder / (result["hour_id"] + ".json")
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    latest_hour = json.loads(latest.read_text(encoding="utf-8")).get("hour_id", "") if latest.exists() else ""
    advance_latest = result["hour_id"] >= latest_hour
    # Keep archives immutable and never rewind latest.
    if archive.exists():
        prior = json.loads(archive.read_text(encoding="utf-8"))
        if prior.get("hour_id") == result["hour_id"]:
            LOG.info("Existing archive for hour %s; keeping prior snapshot", result["hour_id"])
            # A rerun can repair a missing/stale latest pointer without
            # rewriting the immutable per-hour archive.
            if advance_latest and latest_hour != result["hour_id"]:
                latest.write_text(archive.read_text(encoding="utf-8"), encoding="utf-8")
            return latest, archive
        raise RuntimeError("Hour archive collision")
    archive.write_text(content, encoding="utf-8")
    if advance_latest:
        latest.write_text(content, encoding="utf-8")
    return latest, archive


def recent_hours(now: datetime, count: int = 3) -> list[str]:
    end = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [(end - timedelta(hours=i)).strftime("%Y-%m-%dT%H") for i in range(1, count + 1)]


def health_report(root: Path, now: datetime) -> dict:
    rows = []
    for key in recent_hours(now, 24):
        archive = root / "data/hourly" / (key + ".json")
        candidates = len(json.loads(archive.read_text(encoding="utf-8")).get("posts", [])) if archive.exists() else None
        if (root / "published/hourly" / (key + ".json")).exists():
            status = "published_or_quota_handled"
        elif (root / "outbox/hourly" / (key + ".json")).exists():
            status = "queued_without_receipt"
        elif (root / "status/hourly" / (key + ".json")).exists():
            status = "editorially_skipped"
        elif candidates is None:
            status = "missing_snapshot"
        elif candidates == 0:
            status = "no_candidates"
        else:
            status = "awaiting_summary"
        rows.append({"hour_id": key, "status": status, "candidates": candidates})
    return {"checked_at_utc": now.isoformat(), "hours": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config/sources.json"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--hour", help="Exact completed UTC hour (YYYY-MM-DDTHH)")
    parser.add_argument("--repair-recent", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    targets = [args.hour] if args.hour else recent_hours(now, 1)
    if args.repair_recent:
        targets = list(dict.fromkeys(targets + recent_hours(now)))
    failures = []
    for key in targets:
        hour_start(key, now)
        archive = args.root / "data/hourly" / (key + ".json")
        if archive.exists():
            LOG.info("Already collected %s", key)
            # Repair a missing or lagging latest pointer from the immutable archive.
            existing = json.loads(archive.read_text(encoding="utf-8"))
            write_snapshot(existing, args.root)
            continue
        try:
            result = collect_hour(config, now=datetime.now(timezone.utc), hour_id=key)
            write_snapshot(result, args.root)
            LOG.info("Wrote hour=%s candidates=%d", key, len(result["posts"]))
        except Exception:
            LOG.exception("Collection failed for %s", key)
            failures.append(key)
    health = args.root / "data/hourly/health.json"
    health.parent.mkdir(parents=True, exist_ok=True)
    health.write_text(json.dumps(health_report(args.root, datetime.now(timezone.utc)), indent=2) + "\n", encoding="utf-8")
    if failures:
        raise RuntimeError("Failed collection: " + ", ".join(failures))


if __name__ == "__main__":
    main()
