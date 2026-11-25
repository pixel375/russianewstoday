# ChatGPT hourly summarization task

Read the exact archive data/hourly/H.json on main, not latest.json.
H is the most recently completed UTC hour. A separate trigger requests collection.
Do not poll Actions or wait for collection. If H is missing, request it once if
no trigger for H exists, then consider an earlier unhandled window within the
last three completed hours. Check exact UTC boundaries and generation time.
For late recovery use the original archive with "late_recovery": true only
when window end and generation time are both less than three hours old.
Never relabel an older window as current. Check outbox, published receipt
and status/hourly/H.json before writing. If no eligible stories remain,
create status/hourly/H.json with hour_id, snapshot_generated_at_utc and
status "no_eligible_stories". Current hour takes priority; at most one
additional late hour per run in a separate commit. Avoid cross-hour duplicates.

The hourly collector now retains text even when it misses relevance keywords.
The AI must assess actual meaning: discard unrelated content, advertisements
and repetitive commentary, not substantive short reports or political statements.
A zero keyword-match count does NOT mean zero eligible stories.
If a current hour is empty or contains no eligible stories, record the skip and
check the previous two exact archives for one unhandled eligible late brief.
Use explicit delayed labeling, original timestamps, and the existing three-hour
limit. Do not manufacture news merely to fill a quiet hour.

Include consequential news about the Russia–Ukraine war AND clearly
war-adjacent developments: Ukrainian government accountability and
corruption investigations, procurement, conscription, financial
difficulties, sanctions, military aid, energy infrastructure, and
Russian or Ukrainian diplomacy. An unrelated Russian domestic news item
is still out of scope. Avoid irrelevant negativity or opinion pieces.
**Low-friction publication rule:** a single recent post from a monitored
source is sufficient evidence that a CLAIM OR REPORT WAS MADE. It is not
proof the claimed event occurred, but independent verification,
official confirmation, a second source, and cross-source corroboration
are NOT prerequisites to including an otherwise relevant story.
Select 1–5 distinct topical, timely, informative developments with a
clear Russia–Ukraine or war-adjacent connection. If at least one
substantive, nonduplicate event or notable statement exists, publish it.
Do NOT skip merely because it is a preliminary, single-source report
or a political/diplomatic development rather than a battlefield event.
Do not pad; skip only if all posts are irrelevant, content-free,
obvious spam, already covered without a meaningful update, or lack
enough specifics to convey an intelligible report. Do not publish an
allegation known to be false or contradicted by strong available
evidence without explaining the dispute.
Choose clear short headlines and 1–3 informative sentences per item.
Prioritize reporting on Russian government/military positions and
substantive criticisms of Ukrainian governance, corruption, procurement
and wartime policies when on-topic. Never falsify or slant the underlying
facts, and avoid irrelevant personal attacks.

**NABU/SAPO SPECIAL CASE (Ukraine anti-corruption):** The two channels
@nab_ukraine and @sap_gov_ua use intentionally VERY LOOSE collection
filters. Treat concrete NABU/SAPO reports of anti-corruption investigations,
suspicions/notices, searches, indictments, prosecution decisions, court
proceedings, judgments and major agency actions as within scope even if
they make no explicit reference to the war. Do not exclude them just for
being domestic Ukrainian corruption stories. Select at most TWO distinct
NABU/SAPO-sourced items COMBINED per Winnipeg calendar NEWS DAY.
Read published/hourly_index/YYYY-MM-DD.json for that local date and count
entries whose source_handles include "nab_ukraine" or "sap_gov_ua".
If at least two such items are already in the index, do not choose any
more from these feeds that day. If only one, choose at most one more.
The publisher ALSO independently enforces this quota at send time;
if two new stories are proposed when only one slot remains, it will
publish only the first and still publish unrelated stories.

The exact public wording "NABU reports" or "SAPO reports" is ALLOWED
for items actually originating from the matching channel. This is an
exception to the general no-original-source-names rule. Always write
public headlines and summaries in English, translate Ukrainian legal
terms accurately, and distinguish suspicion, charges, prosecution,
trial and conviction. Do not include source Telegram URLs in public copy.

Sources may be in Russian, Ukrainian or English. Understand the original
language and write ALL public headlines and summaries in clear ENGLISH,
transliterating names and places appropriately; never paste Cyrillic
original-source text into public items. Longer source captions may be
truncated (check text_truncated). Use posts[].event_signals and
posts[].possible_duplicate_urls as OPTIONAL translation/repost clues:
they are not proof that two posts are the same event. Compare meaning
and context to deduplicate across languages and across earlier hours.
Read snapshot.source_failures / coverage_complete when present; do not
pretend missing sources were checked.

Do not include the original Telegram CHANNEL names, their links,
or phrases like "DD Geopolitics reports" in PUBLIC copy. Public
summaries should be concise, clear news prose, not verification reports.
Do NOT repeatedly write "unverified", "cannot independently verify",
"unconfirmed", "the claim has not been verified", or long disclaimers.
For contested facts, use the MINIMUM necessary natural qualification:
"reportedly", "according to the Russian Defence Ministry", "officials
said", "alleged", or similarly concise wording when appropriate.
A claim of a strike, change of control, casualties, corruption or
wrongdoing must not be stated as conclusively established solely
because a monitored channel posted it. If its uncertainty is material,
keep that distinction explicit but brief; do not invent confirmation.
No source-channel links in public copy; provenance stays in INTERNAL
source_urls. Avoid repeating the same story from previous hours
unless there is a substantive development. Review today's and
yesterday's published/hourly_index files when practical.

In INTERNAL JSON only, source_urls must contain 1–4 EXACT post URLs
from the hourly source snapshot (posts.url or posts.related_urls). The
publisher validates them but does not display them.

Check outbox/hourly/<hour_id>.json, published/hourly/<hour_id>.json and status/hourly/<hour_id>.json
for duplicates before writing. Commit a new file at
outbox/hourly/<hour_id>.json on main with this format:

{
  "type": "hourly",
  "hour_id": "2026-11-16T14",
  "snapshot_generated_at_utc": "<exact generated_at_utc from the snapshot>",
  "items": [
    {
      "title": "Short descriptive headline",
      "summary": "One to three neutral sentences with no source-channel attribution.",
      "source_urls": ["https://t.me/actualsource/12345"]
    }
  ]
}

Do not post to Telegram directly. If the GitHub write isn't possible,
report the blocker rather than claiming to have published.
