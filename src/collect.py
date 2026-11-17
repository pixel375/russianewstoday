"""Collect public Telegram channel posts without a Telegram account or bot-token access."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import json
import logging
from pathlib import Path
import re
import time
from urllib.parse import quote
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOG = logging.getLogger("russianewstoday.collect")
ROOT = Path(__file__).resolve().parents[1]

# Keep this filter intentionally permissive: ChatGPT makes the final relevance decision.
UKRAINE = re.compile(
    r"\bukrain(?:e|ian|ians)?\b|\bkyiv\b|\bkiev\b|\bzelensk\w*|"
    r"\bукраин\w*|\bкиев\w*|\bкиїв\w*|\bзеленськ\w*|\bзеленск\w*|\bзсу\b|\bвсу\b",
    re.I,
)
WAR = re.compile(
    r"\bwar\b|\bwarfare\b|\bfront(?:line)?s?\b|\bcombat\b|\bbattle\b|"
    r"\bstrike[sd]?\b|\battack(?:ed|s)?\b|\bmissile[sd]?\b|\bdrone[sd]?\b|"
    r"\bbomb(?:ing|ed|s)?\b|\bair.?defen[sc]e\b|\bartillery\b|\btroop[sd]?\b|"
    r"\bceasefire\b|\bnegotiat(?:ion|ions|e|es|ed|ing)\b|\bsanction[sd]?\b|"
    r"\bweapons?\b|\bmilitary\b|\barmed forces\b|\bNATO\b|\bprisoner(?:s)?\b|"
    r"\bпво\b|\bракет\w*|\bдрон\w*|\bудар\w*|\bфронт\w*|\bвойн\w*|\bбоев\w*|\bатак\w*",
    re.I,
)
THEATER = re.compile(
    r"\bdonetsk\b|\bluhansk\b|\blugansk\b|\bkherson\b|\bzaporizh\w*|\bzaporozh\w*|"
    r"\bkharkiv\b|\bkharkov\b|\bpokrovsk\b|\bkursk\b|\bodessa\b|\bodesa\b|"
    r"\bdonbas\w*|\bдоне\w*|\bлуган\w*|\bхерсон\w*|\bзапорож\w*|\bхарьков\w*|\bодесс\w*",
    re.I,
)
RUSSIA = re.compile(r"\brussia(?:n|ns)?\b|\bmoscow\b|\bkremlin\b|\bputin\b|\bросси\w*|\bрусск\w*", re.I)
NOISE = re.compile(r"\bcasino\b|\bsportsbook\b|\bgiveaway\b|\bpromo code\b", re.I)
TOKEN = re.compile(r"[a-zа-яёіїєґ0-9]{3,}", re.I)

# Broad contextual signals in both languages. These help retain war-adjacent
# Ukraine stories (corruption, procurement, conscription, aid, sanctions, etc.).
# They are DISCOVERY signals only, not assertions of truth or political valence.
POLICY = re.compile(
    r"\bcorrupt\w*|\bbrib\w*|\bembezzl\w*|\bfraud\w*|\bscandal\w*|"
    r"\binvestigat\w*|\bprosecut\w*|\bresign\w*|\bprocure\w*|"
    r"\bconscrip\w*|\bmobiliz\w*|\bdesert\w*|\beconom\w*|"
    r"\bdebt\b|\bbudget\b|\belection\w*|\bparliament\b|"
    r"\bpolitic\w*|\brefugee\w*|\benergy\b|\bpower grid\b|"
    r"\bEU\b|\bNATO\b|\bpeace\b|\bdiplomac\w*|\bnegotiat\w*|"
    r"\bmilitary aid\b|\bforeign aid\b|\bfinance\w*|\bsanction\w*|"
    r"\bкоррупц\w*|\bвзятк\w*|\bхищен\w*|\bрастрат\w*|"
    r"\bмошенн\w*|\bскандал\w*|\bрасследован\w*|\bобыск\w*|"
    r"\bзадержан\w*|\bарест\w*|\bотставк\w*|\bзакупк\w*|"
    r"\bмобилизац\w*|\bдезертир\w*|\bуклонист\w*|"
    r"\bэкономик\w*|\bбюджет\w*|\bдолг\w*|\bвыбор\w*|"
    r"\bпарламент\w*|\bрад\w*|\bпомощ\w*|\bэнергетик\w*|"
    r"\bэлектроснабжен\w*|\bпереговор\w*|\bдипломат\w*|"
    r"\bсанкц\w*|\bевросоюз\w*|\bнато\b",
    re.I,
)
UKRAINE_EXT = re.compile(
    r"\bукраїн\w*|\bкиїв\w*|\bзеленськ\w*|\bзеленск\w*|"
    r"\bзеленск\w*|\bзеленськ\w*|\bзеленск\w*|\bвсу\b|"
    r"\bзсу\b|\bкиев\w*|\bукраин\w*|\bukrain\w*|"
    r"\bzelensk\w*|\bkyiv\b|\bkiev\b|\bukrainian\w*",
    re.I,
)

# Non-destructive multilingual hints. Only human/LLM review can determine
# that two translated stories truly describe the same incident.
EVENT_PATTERNS = {
    "kyiv": r"\bkyiv\b|\bkiev\b|\bкиев\w*|\bкиїв\w*",
    "odesa": r"\bodesa\b|\bodessa\b|\bодесс\w*|\bодес\w*",
    "kharkiv": r"\bkharkiv\b|\bkharkov\b|\bхарьков\w*|\bхарків\w*",
    "zaporizhzhia": r"\bzaporizh\w*|\bzaporozh\w*|\bзапорож\w*|\bзапоріж\w*",
    "donetsk": r"\bdonetsk\b|\bдонецк\w*|\bдонецьк\w*",
    "kursk": r"\bkursk\b|\bкурск\w*",
    "moscow": r"\bmoscow\b|\bмоскв\w*",
    "crimea": r"\bcrimea\b|\bкрым\w*|\bкрим\w*",
    "corruption": r"\bcorrupt\w*|\bbrib\w*|\bвзятк\w*|\bкоррупц\w*|\bкорупц\w*",
    "procurement": r"\bprocure\w*|\bзакупк\w*|\bзакупівл\w*",
    "drone": r"\bdrone\w*|\buav\b|\bбпла\b|\bбпілот\w*|\bдрон\w*",
    "missile": r"\bmissile\w*|\bракет\w*",
    "strike": r"\bstrike\w*|\battack\w*|\bудар\w*|\bатак\w*",
    "sanctions": r"\bsanction\w*|\bсанкц\w*",
    "negotiation": r"\bnegotiat\w*|\bpeace talk\w*|\bпереговор\w*",
    "energy": r"\benergy\b|\bpower grid\b|\bэнерг\w*|\bелектро\w*",
    "mobilization": r"\bmobiliz\w*|\bconscrip\w*|\bмобилизац\w*|\bмобілізац\w*",
}
EVENT_REGEX = {key: re.compile(expr, re.I) for key, expr in EVENT_PATTERNS.items()}
LOCATION_SIGNALS = frozenset(("kyiv", "odesa", "kharkiv", "zaporizhzhia",
                              "donetsk", "kursk", "moscow", "crimea"))


def relevant(text: str) -> bool:
    if not text or len(text.strip()) < 28:
        return False
    if NOISE.search(text) and not UKRAINE.search(text):
        return False
    context = bool(UKRAINE.search(text) or UKRAINE_EXT.search(text))
    war = bool(WAR.search(text))
    related = bool(POLICY.search(text))
    return bool((context and (war or related)) or
                (THEATER.search(text) and (war or related)) or
                (RUSSIA.search(text) and (war or related)))


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1.0,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; RussiaNewsTodayDigest/1.0; public channel reader)",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


def parse_page(html: str, handle: str, name: str) -> list[dict]:
    """Use canonical Telegram message wrappers; timestamps come from <time datetime>."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for node in soup.select(".tgme_widget_message[data-post]"):
        post_id = node.get("data-post", "")
        if not re.fullmatch(r"[\w]+/\d+", post_id):
            continue
        time_node = node.select_one("time[datetime]")
        if not time_node:
            continue
        try:
            dt = datetime.fromisoformat(time_node["datetime"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                continue
        except (ValueError, TypeError):
            continue
        text_node = node.select_one(".tgme_widget_message_text")
        if text_node is None:
            text_node = node.select_one(".tgme_widget_message_caption")
        if text_node is None:
            continue
        # Avoid pulling UI elements, reaction counts, view counts, or external embeds.
        text = text_node.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        found.append({
            "id": post_id,
            "channel": handle,
            "source": name,
            "url": "https://t.me/" + post_id,
            "published_at": dt.astimezone(timezone.utc).isoformat(),
            "text": text[:4800],
            "text_truncated": len(text) > 4800,
            "related_urls": [],
        })
    return found


def crawl_source(session: requests.Session, handle: str, name: str,
                 start: datetime, end: datetime, max_pages: int) -> tuple[list[dict], dict]:
    out: dict[str, dict] = {}
    before = None
    seen_page_ids: set[int] = set()
    reached_start = False
    pages = 0
    for page in range(max_pages):
        url = "https://t.me/s/" + quote(handle)
        if before:
            url += "?before=" + str(before)
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        items = parse_page(resp.text, handle, name)
        pages += 1
        if not items:
            # An empty public page is not proof that the history was exhausted.
            raise RuntimeError(f"{handle}: empty/unparseable public Telegram page {url}")
        ids = [int(p["id"].rsplit("/", 1)[-1]) for p in items]
        oldest = min(ids)
        if oldest in seen_page_ids or (before is not None and oldest >= before):
            raise RuntimeError(f"{handle}: Telegram pagination stopped advancing")
        seen_page_ids.add(oldest)
        before = oldest
        oldest_dt = min(datetime.fromisoformat(p["published_at"]) for p in items)
        for post in items:
            dt = datetime.fromisoformat(post["published_at"])
            if start <= dt < end:
                out[post["id"]] = post
        if oldest_dt <= start:
            reached_start = True
            break
        if page < max_pages - 1:
            time.sleep(0.6)
    if not reached_start:
        raise RuntimeError(
            f"{handle}: {max_pages} pages did not reach requested time cutoff; "
            "refusing an incomplete digest"
        )
    values = sorted(out.values(), key=lambda x: x["published_at"], reverse=True)
    return values, {"handle": handle, "name": name, "pages": pages, "raw_count": len(values)}


def similar(a: dict, b: dict) -> bool:
    atext = a["text"].casefold()
    btext = b["text"].casefold()
    if abs(len(atext) - len(btext)) > max(len(atext), len(btext)) * 0.65:
        return False
    if SequenceMatcher(None, atext[:650], btext[:650]).ratio() >= 0.84:
        return True
    at = set(TOKEN.findall(atext))
    bt = set(TOKEN.findall(btext))
    if not at or not bt:
        return False
    overlap = len(at & bt) / len(at | bt)
    return overlap >= 0.77 and len(at & bt) >= 9


def dedupe(posts: list[dict]) -> list[dict]:
    result: list[dict] = []
    for p in sorted(posts, key=lambda x: x["published_at"], reverse=True):
        merged = False
        for prior in result:
            if abs((datetime.fromisoformat(p["published_at"]) -
                    datetime.fromisoformat(prior["published_at"])).total_seconds()) > 18 * 3600:
                continue
            if similar(p, prior):
                links = [prior["url"], *prior["related_urls"], p["url"], *p["related_urls"]]
                prior["related_urls"] = list(dict.fromkeys(u for u in links if u != prior["url"]))[:5]
                if len(p["text"]) > len(prior["text"]):
                    prior["text"] = p["text"]
                merged = True
                break
        if not merged:
            result.append(p.copy())
    return result


def event_signals(text: str) -> list[str]:
    """Language-agnostic event markers, for AI-assisted semantic deduping."""
    return sorted(key for key, rx in EVENT_REGEX.items() if rx.search(text))


def annotate_possible_translations(posts: list[dict]) -> list[dict]:
    """Flag possible translated repeats; NEVER collapse on ambiguous clues."""
    for post in posts:
        post["event_signals"] = event_signals(post["text"])
        post["possible_duplicate_urls"] = []
    for i, a in enumerate(posts):
        aset = set(a["event_signals"])
        for b in posts[i + 1:]:
            bset = set(b["event_signals"])
            shared = aset & bset
            if not (shared & LOCATION_SIGNALS) or len(shared) < 3:
                continue
            ta = datetime.fromisoformat(a["published_at"])
            tb = datetime.fromisoformat(b["published_at"])
            if abs((ta - tb).total_seconds()) > 45 * 60:
                continue
            a["possible_duplicate_urls"].append(b["url"])
            b["possible_duplicate_urls"].append(a["url"])
    return posts


def quality_score(p: dict) -> float:
    s = p["text"]
    context = bool(UKRAINE.search(s) or UKRAINE_EXT.search(s))
    return (3 * context + 2 * bool(THEATER.search(s)) +
            2 * bool(WAR.search(s)) + 2 * bool(POLICY.search(s)) +
            min(len(s) / 350, 2))


def pick_candidates(posts: list[dict], limit: int) -> list[dict]:
    # Prefer context-rich reports, then newest posts; preserve a breadth of sources.
    ranked = sorted(posts, key=lambda p: (quality_score(p), p["published_at"]), reverse=True)
    return sorted(ranked[:limit], key=lambda p: p["published_at"], reverse=True)


def collect(config: dict, now: datetime | None = None,
            session: requests.Session | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = now - timedelta(hours=int(config.get("hours_back", 24)))
    session = session or make_session()
    all_posts = []
    stats = []
    for source in config["sources"]:
        posts, stat = crawl_source(
            session, source["handle"], source["name"], start, now,
            int(config.get("max_pages_per_source", 40))
        )
        LOG.info("%s: %s posts from %s pages", source["handle"], len(posts), stat["pages"])
        stats.append(stat)
        all_posts.extend(posts)
    if not all_posts:
        raise RuntimeError("No recent posts were collected from any source")
    filtered = [p for p in all_posts if relevant(p["text"])]
    unique = dedupe(filtered)
    selected = annotate_possible_translations(
        pick_candidates(unique, int(config.get("max_candidates", 150))))
    if not selected:
        raise RuntimeError("No war-related candidate posts; declining to overwrite last snapshot")
    return {
        "schema_version": 1,
        "snapshot_date": now.astimezone(ZoneInfo(config["timezone"])).date().isoformat(),
        "generated_at_utc": now.isoformat(),
        "window_start_utc": start.isoformat(),
        "window_end_utc": now.isoformat(),
        "sources": stats,
        "stats": {
            "raw_posts": len(all_posts),
            "relevant_posts": len(filtered),
            "deduplicated_posts": len(unique),
            "candidate_posts": len(selected),
        },
        "posts": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config/sources.json"))
    parser.add_argument("--output", default=str(ROOT / "data/latest.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    result = collect(cfg)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG.info("Saved %s candidates to %s", len(result["posts"]), target)


if __name__ == "__main__":
    main()
