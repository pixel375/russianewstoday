# ChatGPT scheduled task — Russia News Today

Use this text when scheduling the ChatGPT summarization step. The GitHub connection
must have access to read and write to pixel375/russianewstoday.

> Read pixel375/russianewstoday/data/latest.json using GitHub. Do not use
> arbitrary live Telegram content as a substitute for this collection.
> Confirm the snapshot was produced today in the America/Winnipeg timezone,
> within the previous 3 hours, and contains candidate posts. If not, explain
> why and stop without publishing or creating a digest.
>
> Produce 20–30 distinct, important factual Russia–Ukraine war news points,
> only when there is enough substantive material. Fewer is acceptable.
> Remove cross-channel duplicates and irrelevant material. Organize points
> under the allowed categories: frontline, strikes, equipment,
> international, diplomacy, other.
>
> Treat Telegram reports as unverified assertions unless there is
> independent corroboration. State who claims what; avoid false certainty,
> invented numbers, embellished battlefield advances, and editorializing.
> Cover important opposing accounts if present in the collection. Do not
> treat multiple Telegram reposts of one claim as independent confirmation.
>
> Each point must be a distinct event/update, with title (5–180 chars),
> summary (12–700 chars), category, and source_urls (1–4 URLs).
> Every source URL must be an EXACT url or related_url in the latest.json
> candidate posts; never fabricate links. Draft original summaries, not
> verbatim reproductions.
>
> Before writing, check whether published/<snapshot_date>.json already
> exists; if it exists, do nothing. If an outbox digest for the same
> snapshot already exists, do not create duplicates.
>
> Commit ONLY outbox/<snapshot_date>.json to the main branch with this shape:
> {
>   "date": "<snapshot_date from latest.json>",
>   "snapshot_generated_at_utc": "<generated_at_utc from latest.json>",
>   "items": [
>     {
>       "category": "frontline",
>       "title": "Brief neutral headline",
>       "summary": "One or two fact-focused sentences, clearly attributed.",
>       "source_urls": ["https://t.me/actualchannel/12345"]
>     }
>   ]
> }
>
> The outbox commit will trigger GitHub Actions, but publishing is disabled
> until the owner sets ENABLE_PUBLISH=true in Actions repository variables.
> Do not try to send Telegram messages directly. If GitHub read/write tools
> are unavailable, report the limitation instead of claiming success.
