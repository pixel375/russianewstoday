# ChatGPT hourly summarization task

Read pixel375/russianewstoday/data/hourly/latest.json from main.

The snapshot must cover the most recently completed UTC hour exactly:
hour_id is YYYY-MM-DDTHH (UTC start); window_end_utc is the start of the
current UTC hour; generated_at_utc must be no more than 45 minutes old.
If missing or stale, first use the GitHub tools to request ONE recovery
collection: check triggers/hourly.json, and create/update it on main with
{"hour_id":"<required previous UTC hour>","requested_at_utc":"<current UTC ISO time>","reason":"stale_snapshot_recovery"}
only if that exact hour has not already been requested. That monitored
file triggers the collection workflow on push. Check the resulting GitHub
Actions collector run, waiting until it COMPLETES, and reread the latest
snapshot. The collector normally needs 5–20 seconds after triggering.
IMPORTANT: do not stop after only 1–3 rapid polls; continue checking
the actual job state and refreshed snapshot for up to roughly 60 seconds.
A previous ChatGPT task stopped only 2 seconds before the collector
finished, causing an avoidable missed hourly brief. Only if the job
fails or the snapshot still cannot be verified after recovery should
you STOP without creating an outbox file. Do not reuse stale news.

If there are no important new war events, SKIP the hour. Never pad.
Select 1–5 distinct significant developments. Headline should be short
and informative, and summary 1–3 sentences with somewhat more detail
than the former daily digest.

Do not include the original channel names, original Telegram post links,
or phrases such as "DD Geopolitics reports" in PUBLIC copy. When events
are disputed, retain words such as reportedly, may, appears or unverified.
Never convert a channel allegation into a confirmed fact. Avoid repeating
the same news from prior hours unless there is a substantive development;
review today's and yesterday's published/hourly_index files when practical.

In INTERNAL JSON only, source_urls must contain 1–4 EXACT post URLs
from the hourly source snapshot (posts.url or posts.related_urls). The
publisher validates them but does not display them.

Check outbox/hourly/<hour_id>.json and published/hourly/<hour_id>.json
for duplicates before writing. Commit ONLY a new file at
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
