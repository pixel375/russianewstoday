# Russia News Today 🇷🇺🇺🇦

A no-paid-API daily Telegram digest pipeline for
[@russianewstodayofficial](https://t.me/russianewstodayofficial).

**Status: collector and publishing code installed; live posting intentionally
disabled until the ChatGPT/GitHub handoff is verified.**

## Architecture

1. **GitHub Actions** crawls public web previews of
   [DD Geopolitics](https://t.me/s/DDGeopolitics),
   [Intel Slava](https://t.me/s/intelslava), and
   [BRICS News](https://t.me/s/bricsnews), paginating until it reaches
   the preceding 24 hours.
2. Python removes obviously unrelated reports and near-exact duplicates,
   retains links and timestamps, and commits **data/latest.json**.
3. A separately configured **ChatGPT scheduled task** reads
   the JSON via the connected GitHub integration, filters it further,
   and writes **outbox/YYYY-MM-DD.json**, with 20–30 substantial items
   when warranted. See [task instructions](docs/chatgpt-task-prompt.md).
4. A GitHub Actions publisher validates every source URL against the
   collection, splits digest content into safe Telegram chunks, and
   posts to the configured bot's channel. It records a daily receipt
   under **published/** so completed digests cannot be reposted.

### Credentials and configuration

In **Settings → Secrets and variables → Actions**:

| Type | Key | Value |
|---|---|---|
| Secret | TELEGRAM_BOT_TOKEN | BotFather token, never commit it |
| Variable | TELEGRAM_CHAT_ID | @russianewstodayofficial |
| Variable | ENABLE_PUBLISH | **Not set / false** initially; set to true only after a safe test |

No OpenAI API key, Cloudflare subscription, paid inference, or Telegram
user login is required.

### Schedule

Collection runs every day at **15:30 UTC** (09:30 winter / 10:30 summer
in Winnipeg) and on source-code pushes or manual dispatch.
Recommended ChatGPT scheduled task time: **11:30 AM America/Winnipeg**.
After ChatGPT commits the outbox file, publishing runs on the push
event *only if* ENABLE_PUBLISH=true. Publication time is not guaranteed
exactly at noon because GitHub schedules and ChatGPT tasks can be delayed.

### Local usage

    python -m pip install -r requirements.txt
    python -m unittest discover -s tests -v
    python -m src.collect
    python -m src.publish --dry-run

The collector requires internet access. --dry-run requires a matching
outbox digest. Live publishing also needs TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID in the environment. Never run it live until ready.

### Important limits

- The public Telegram HTML preview can change, throttle or block crawlers.
  This build checks pagination progression and fails closed if the last
  24 hours cannot be reached. No silent partial-window publication.
- Pure photo/video posts without meaningful captions are omitted.
- Heuristic filtering only prepares candidates; ChatGPT must still
  remove unrelated reports, duplicates, unverifiable allegations,
  and propaganda-style phrasing. Telegram source links are not
  independent verification.
- The public repo holds excerpts from public posts; review privacy and
  redistribution considerations before adding private or restricted sources.
- If Telegram accepts some parts but a later send fails, a rerun can
  repost earlier parts because Telegram lacks transactional multi-send.
  Check the channel before manually rerunning a failed publication.

### Roadmap

- [x] Public Telegram collection with cutoff and pagination safeguards
- [x] Relevance filtering and preliminary deduplication
- [x] Telegram HTML split rendering and source URL validation
- [x] GitHub Actions collection and guarded publishing workflows
- [x] Unit tests
- [ ] Verify real production collection run
- [ ] Verify scheduled ChatGPT read/write of latest.json to outbox
- [ ] Test output format in dry-run and authorize live publication
