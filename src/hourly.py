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


def collect_hour(config: dict, now: datetime | None = None, session=None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    end = now.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
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
    filtered = [p for p in all_posts if relevant(p["text"])]
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
    # Keep hourly archives immutable once published, avoiding confusing stale digests.
    if archive.exists():
        prior = json.loads(archive.read_text(encoding="utf-8"))
        if prior.get("hour_id") == result["hour_id"]:
            LOG.info("Existing archive for hour %s; keeping prior snapshot", result["hour_id"])
            # A rerun can repair a missing/stale latest pointer without
            # rewriting the immutable per-hour archive.
            if not latest.exists() or json.loads(latest.read_text(encoding="utf-8")).get("hour_id") != result["hour_id"]:
                latest.write_text(archive.read_text(encoding="utf-8"), encoding="utf-8")
            return latest, archive
        raise RuntimeError("Hour archive collision")
    archive.write_text(content, encoding="utf-8")
    latest.write_text(content, encoding="utf-8")
    return latest, archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config/sources.json"))
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    result = collect_hour(config)
    latest, archive = write_snapshot(result, args.root)
    LOG.info("Wrote hour=%s candidates=%d files=%s %s",
             result["hour_id"], len(result["posts"]), latest, archive)


if __name__ == "__main__":
    main()
