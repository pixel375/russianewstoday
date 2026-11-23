# Russia News Today 🇷🇺🇺🇦

A no-paid-API Russia–Ukraine war news digest for
[@russianewstodayofficial](https://t.me/russianewstodayofficial).

## Current output

**Hourly Brief:** 1–5 distinct important developments from the last
completed UTC hour, each with a headline and 1–3 explanatory sentences.
The scope includes relevant Ukrainian political, corruption,
procurement, energy, financial, sanctions and conscription news that
materially connects to the conflict. Skip the hour if there is
insufficient substantive news.

**Daily Brief:** 10–20 important distinct headlines for the completed
Winnipeg calendar day, published shortly after local midnight the next
day. Each clickable headline points to an earlier hourly message in
our own Telegram channel. Fewer than 10 is fine if the day is quiet.

Both public formats are written in English, including when collected
posts are Russian-language. Longer source posts are preserved up to
4,800 characters. The collector supplies cross-language duplicate
hints for editorial comparison but never merges ambiguous translated
stories based on hints alone.

Neither public format prints original Telegram source links or
source-channel names. A single monitored source may warrant inclusion
of an on-topic new development without independent corroboration.
Use concise natural qualifications such as "reportedly", "officials
said" or "alleged" when the underlying event remains uncertain; do
not add stock "unverified" disclaimers to every report. An allegation
must not be presented as established fact merely because it is posted.
Coverage explicitly includes material critical reporting about
Ukrainian institutions, sanctions, governance, and related Russian
official positions. Do not manufacture a pro-Russian conclusion
from a neutral event or conceal essential contradictory facts.

## NABU and SAPO anti-corruption updates

- The collector watches [NABU](https://t.me/nab_ukraine) and
  [SAPO](https://t.me/sap_gov_ua) with a relaxed, source-specific filter.
  Substantive Ukrainian-language posts are eligible even without an explicit
  reference to Russia, the war or a standard keyword.
- The hourly publisher enforces a **combined maximum of 2 NABU/SAPO-source
  news items per America/Winnipeg calendar news day**, counted from the
  persistent published hourly index. A story citing both sources counts once.
  Over-quota items are suppressed without blocking unrelated news.
- **"NABU reports" and "SAPO reports" are explicitly permitted** in English
  public copy when reporting on the corresponding agency's statements.
  Do not claim an investigation or suspicion is a conviction. Original
  Telegram source links remain internal only.
- For a consistent quota across hourly workflow jobs, the publishing job
  refreshes the latest main branch before reading the daily index.

## Architecture

1. GitHub Actions is scheduled at 09 and 14 minutes past each UTC
   hour on standard ubuntu-latest runners, using the second slot as
   a retry if GitHub drops the first schedule. It collects public
   Telegram pages from 16 monitored channels (listed in
   config/sources.json), including the Ukrainian-language NABU and SAPO
   anti-corruption feeds, Russian-language TASS, RIA Novosti,
   Two Majors, WarGonzo, Colonelcassad and Voenkor Kotenok, as well
   as English-language defence and military-commentary sources.
   Russian and English posts are preserved for ChatGPT summarization.
   The collector must successfully cover at least nine feeds per hour;
   source failures are recorded explicitly in the snapshot.
2. It stores immutable collection archives at
   data/hourly/YYYY-MM-DDTHH.json and data/hourly/latest.json.
3. ChatGPT hourly task runs at minute 25 in America/Winnipeg time,
   reviews the latest hour and creates 1–5 concise items at
   outbox/hourly/YYYY-MM-DDTHH.json. If none are worthwhile, skip.
   If the scheduled collector has not produced a fresh snapshot,
   ChatGPT requests a collector retry via triggers/hourly.json
   and rechecks the snapshot before publishing.
   [Hourly task details](docs/chatgpt-hourly-task.md).
4. On any new hourly outbox push, GitHub Actions validates every
   INTERNAL original source URL against the exact source snapshot.
   These URLs are never printed. The bot sends one or more formatted
   Telegram messages and stores message IDs at published/hourly/.
5. The publisher maintains a per-local-day record of successfully
   published hourly stories and their exact OWN-CHANNEL Telegram
   deep links at published/hourly_index/YYYY-MM-DD.json.
6. At 00:45 Winnipeg time, the daily ChatGPT task selects the previous
   calendar day's 10–20 most important published hourly stories and
   writes outbox/daily/YYYY-MM-DD.json. [Daily task details](docs/chatgpt-daily-task.md).
   The publisher checks those IDs, resolves their original hourly
   headlines and hyperlinks, sends the clickable daily index, and
   stores a receipt at published/daily/.

## GitHub configuration

- Actions secret TELEGRAM_BOT_TOKEN is your BotFather token.
- Actions variable TELEGRAM_CHAT_ID is @russianewstodayofficial.
- No OpenAI API key or paid AI service is used.
- Public publishing is enabled after a successful validation job.

## Tests and manual commands

    python -m pip install -r requirements.txt
    python -m unittest discover -s tests -v
    python -m src.hourly
    python -m src.publish_v2 --path outbox/hourly/2026-11-16T14.json --dry-run

For manual publication, use the GitHub Actions publisher workflow
dispatch and provide the exact new outbox path. Do not post to Telegram
directly from ChatGPT.

## Operational limits

- Collection and ChatGPT runs may be delayed; stale hourly snapshots
  will not publish and hours can be skipped.
- Pure photo and video posts without captions are not collected.
- The original sources are publicly readable in GitHub's archived JSON
  but hidden from the Telegram output. Attribution is removed from the
  public writing, not from internal evidence.
- Posts do not require multiple independent sources, but a source
  reporting an event is not the same as independent confirmation of
  that event. Attribute material allegations briefly when necessary,
  and avoid repetitive verification caveats.
- The daily digest covers the local calendar day, not a rolling
  last-24-hours window. Posting after midnight ensures the final hour
  has time to complete.
- Telegram cannot atomically post multi-message digests; if one part
  fails, manual duplicate cleanup may occasionally be necessary.
- Historical files using the original once-daily outbox and receipts
  remain but are not handled by the new publisher.
