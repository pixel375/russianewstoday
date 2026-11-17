# ChatGPT end-of-day highlights task

Run after the local Winnipeg calendar day has ended, so that the final
hourly brief of that day has already had a chance to publish.

Read pixel375/russianewstoday/published/hourly_index/YYYY-MM-DD.json
from main, where YYYY-MM-DD is YESTERDAY in America/Winnipeg timezone.
This index contains successfully published hourly items, including
links into the channel's own Telegram messages.

If there is no index or zero items, SKIP the daily digest. Choose the
10–20 most significant distinct events from that day's published
hourly items; choose fewer if there isn't enough substantive material.
Prioritize major battlefield and civilian developments, diplomacy,
military equipment, international policy actions, and consequential
war-adjacent events such as Ukrainian corruption, procurement,
government accountability, conscription, sanctions and aid.
Russian-language original sources are supported; the hourly publisher
already stores English titles. Keep daily posts in English. Do not
exaggerate or rewrite neutral facts into partisan conclusions.

Do not add original Telegram source names, original-source links,
unverified events, or "X reports / X claims" phrases. Do not invent
new headlines or links: the publisher renders clickable headlines
directly from its verified hourly index.

Check both outbox/daily/<date>.json and published/daily/<date>.json
to prevent duplicate publication. For historical days also check
the legacy published/<date>.json before creating a new daily item.

Create exactly ONE new file on main at outbox/daily/YYYY-MM-DD.json:

{
  "type": "daily",
  "date": "YYYY-MM-DD",
  "items": [
    {"item_id": "2026-11-16T14:1"},
    {"item_id": "2026-11-16T17:2"}
  ]
}

Every item_id MUST exist in the actual published hourly index for
that date. Do not include separate title, summary, URL, category or
other fields in the daily outbox items.

The publisher resolves item_id into the existing headline and
a clickable direct link to @russianewstodayofficial's earlier hourly
message. Do not send Telegram messages yourself. If GitHub write
fails or requires approval, report the limitation honestly.
