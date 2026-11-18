# Strong EPG v2 — roster-first staging test

**Your existing public `Strong-EPG-with-logos.xml.gz` and its recurring `update.yml` workflow stay unchanged.** This test only creates `Strong-EPG-v2-preview.xml.gz` after all input and validation steps succeed.

## What it does

1. Reads the **Strong M3U playlist** as the authoritative channel list, including channels missing from Strong's original EPG XML. This is a playlist *roster*, not a request to redistribute streams.
2. Loads Strong's original XMLTV guide plus publicly accessible secondary listings (Ganjarelease, Canada, US locals, UK, Portugal, Brazil). Extra EPG sources contribute schedules **only when mapped to Strong's roster**.
3. Prioritizes **Canada/US first**, then **UK and all sports/PPV**, then **Portugal/Brazil**, then the remaining Strong channels. Those groups affect matching priority, not the channels' right to be included.
4. Matches verified exact IDs and curated regional aliases, then unique name/event aliases. It refuses to guess ambiguous sports-event assignments.
5. Preserves clean public channel logos and channel metadata and fills genuine unknown schedules with **channel-name placeholders**, clearly marked in the audit. Unassigned streams get stable IDs but may require manual player mapping.
6. Checks every output channel for complete seven-day *populated* coverage (which includes placeholders), no overlapping programmes, and no extra IDs originating solely from a third-party guide. Populated does **not** mean accurate real schedules are present everywhere.

The existing bulk `mapping.csv` is **not** reused in this test because many historical aliases were not independently verified. Curated aliases live in `v2/verified-aliases.csv`.

## Install and run safely

1. In your repository, upload the package's `v2/` folder and `.github/workflows/preview-v2.yml` file, **preserving those exact paths**. Do not replace the existing `build.py`, `mapping.csv`, `update.yml` or live `.xml.gz` file.
2. In **Settings → Secrets and variables → Actions**, keep `STRONG_EPG_URL` and add `STRONG_M3U_URL` if it is missing. Use a **personal Strong playlist URL** for one subscription, **not the reseller/admin panel account**. Never paste credentials in your repo files or screenshots. Although the earlier EPG.xml file was provided, it is **not** an M3U roster.
3. Go to **Actions → Test Strong EPG v2 (staging only) → Run workflow**. It runs on demand only; it is not scheduled.
4. On success, a separate staging file will be published at:
   `https://raw.githubusercontent.com/JoaoCagao7/Strong-EPG/main/Strong-EPG-v2-preview.xml.gz`
   This URL won't work until the first successful staging run.
5. Open the latest Actions run, download the **Strong-EPG-v2-reports** artifact and inspect:
   - `Strong-v2-coverage.csv`: each channel's programme hours, fallback hours and matching source
   - `Strong-v2-streams.csv`: every Strong playlist stream, any missing `tvg-id`, and IDs reused across streams
6. Test the **staging link as a separate EPG source in UHF or TiviMate**. Keep the existing working source active for your customers. If a channel still says "No information," use its `epg_id` from the stream report to investigate playlist-to-guide assignment.

## Caveats

- A complete roster-first build needs M3U. Strong's XMLTV snapshot contains only a portion of the streams, especially sports-event streams. The available earlier files are stale snapshots and can't establish today's coverage.
- Schedule sources change over time; every upstream site remains a dependency even though the published channel list is yours.
- An exact `tvg-id` that Strong applies to two **different** streams cannot automatically yield two distinct schedules in XMLTV. Inspect `streams_sharing_epg_id` in the audit.
- Ganjarelease's dummy sports programmes may contain outdated event labels; event names are never independently guaranteed without unambiguous broadcaster/provider assignment.
- Only republish third-party listing data when permitted under the source's license or terms.
- The preview is tested locally for XML validity and roster filtering. It is **not a certified accuracy guarantee** and should not replace your live guide until you verify it.

## Local smoke test (XML-only; *not for deployment*)

```shell
python v2/build.py --strong EPG.xml --ganjarelease epg6.xml.gz --canada '' --us-local '' --uk '' --portugal '' --brazil '' --mapping v2/verified-aliases.csv --output test.xml.gz
```
