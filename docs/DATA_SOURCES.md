# Data sources

Reviewed September 13, 2026. This is the source decision for the player-search
dashboard; historical research inputs retain their own provenance.

## Selected integration

Use the current-season injury and roster CSVs, compressed depth-chart CSV, and schedule CSV published
in **nflverse-data releases**. Access is public, requires no API key or account,
and uses the data repository's explicit
[CC BY 4.0 license](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md).
The license permits sharing and adaptation with attribution. Retain nflverse
credit, source and license links, the warranty disclaimer, and a description
of optasy's filtering, normalization and joins. The data do not inherit optasy's
MIT software license.

This decision relies on the publisher's affirmative data license, rather than
the mere availability of a URL. The current license is standard CC BY 4.0 with
no injury, roster or schedule exclusion; its GitHub blob is
`0fb847eb09afc05734c2f1aa34bc3ebd995a072a`.

The separate [nflverse umbrella package](https://nflverse.nflverse.com/)
distinguishes its software license from underlying owners' data terms. That
general caution is not a dataset-specific revocation of the release license.
The published [injury builder](https://github.com/nflverse/nflverse-rosters/blob/main/exec/update-injuries.R)
calls `nflapi::nflapi_injuries`; the `nflapi` repository was unavailable for
independent inspection during this review. Do not claim that optasy has an
NFL contract, official endorsement or a separately verified upstream agreement.
Reassess if the publisher adds a restriction or a rights holder disputes the
grant. Do not expand this decision to photographs, logos, news text, unreviewed
datasets or direct NFL website/API collection.

## Verified coverage

These are observations of files retrieved September 13, 2026 at approximately
05:57 UTC, not promises about later coverage.

| Release asset                                                                                               | Observed coverage                                                    | Asset last modified (UTC) |
| ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------- |
| [injuries_2026.csv](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2026.csv) | 182 regular-season week 1 rows, all 32 teams, all reported positions | September 12, 11:35:55    |
| [roster_2026.csv](https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2026.csv)      | 2,963 records, all 32 teams, latest available week 1                 | September 12, 11:37:40    |
| [games.csv](https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv)                | 272 regular-season 2026 games, weeks 1–18                            | September 13, 05:06:24    |

The [injury release](https://github.com/nflverse/nflverse-data/releases/tag/injuries)
also contains 2025 data, updated September 7, 2026. The older
[availability page](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html#injury-data)
still says the feed ended after 2024. Current release contents supersede that
statement as evidence of availability. They do not establish uninterrupted
operation or complete reporting at every future refresh.

The injury CSV contains game designation, practice participation, and primary
and secondary injury descriptions. Blank game designation is retained as
unreported, never changed to “healthy.” In this observation 123 rows had no
game designation; 27 were Out, 26 Questionable and six Doubtful. Offensive and
special-teams entries remain in the opponent report. “All available entries”
means all matching rows in the supplied file, not independently certified
completeness against each team's original report. An absent team or week is
unknown coverage, never an empty injury report.

No report publication date or practice-day date is present in the current CSV.
The week is known, but report vintage is unavailable. HTTP `Last-Modified`
describes the published file, and retrieval time describes optasy's request;
neither may be relabelled as the original report date. A newly retrieved file
can still contain old evidence. Started games cannot be described as a verified
pre-game snapshot when the underlying report vintage is unknown.

## Identity and schedule joins

The [roster builder](https://github.com/nflverse/nflverse-rosters/blob/main/R/rosters.R)
uses weekly NGS data for modern seasons, supplemented by Shield/player identity
data, with a Shield fallback. Its
[season conversion](https://github.com/nflverse/nflverse-rosters/blob/main/R/utils_rosters_weekly_to_season.R)
selects each identity's latest available week. This is periodic source context,
not a guarantee that a transaction is reflected immediately.

The observed roster includes active, inactive, reserve, practice-squad, exempt,
cut and retired records. An `ACT`-only filter would lose current injured or
inactive roster members. Exclude departed/retired statuses while retaining
current roster membership independently of game availability. Preserve stable
source identifiers and reject ambiguous current-team joins rather than choosing
a team by name. This observation had no duplicate GSIS IDs and one absent GSIS
ID; that player's `gsis_it_id` was present and supports a namespaced fallback.

The [schedule dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html)
defines `gametime` in Eastern time regardless of venue. Combine it with
`gameday` using `America/New_York`, including daylight-saving changes, then
display the user's local time. Missing kickoff time remains unknown. A bye
requires adequate schedule coverage; a missing or conflicting schedule is not
proof of a bye. Match the exact season, week and current team. Future schedule
changes replace the current view on a later successful refresh.

## Defensive roster and first-string context

The September 13 follow-up adds the current opponent roster and color-coded
status borders, plus the fourth release asset:
[depth_charts_2026.csv.gz](https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv.gz).
The same affirmative nflverse-data CC BY 4.0 grant was rechecked for this
specific dataset; it has no dataset-specific exclusion. The publisher's
[release notes](https://github.com/nflverse/nflreadr/releases) identify ESPN as
the post-2024 depth-chart source. As with injuries, this relies on the publisher's
data grant and does not assert an independently verified upstream agreement or
authorize direct ESPN collection.

The [availability documentation](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html#depth-chart-data)
says these observations update daily and have timestamps rather than NFL weeks.
The September 13 file contains a season of observations (about 49.1 MB expanded,
10.1 MB compressed), with the latest snapshot covering all 32 teams. optasy
retains 2,222 position assignments from each team's latest available timestamp.
`dt` is an observation timestamp, not confirmation of a game lineup. Rank 1
means first string at that chart position. Multiple assignments are preserved;
no name-based identity joins or game-start guarantees are introduced.

The collector reads bounded gzip input (20 MiB) and rejects expansion above
160 MiB or two million CSV rows. CSV rows are consumed as parsed, keeping only
the latest snapshot per team in memory. Downloaded season history is neither
committed nor sent to visitors. Source limits fail clearly as the archive grows.
Browser first-string labels require exact player/team matches, the current
schedule week, and depth observation, source update and retrieval within 24 hours.
Older, future, missing or transferred-player chart evidence cannot create a
current first-string label. Current rosters are not historical game rosters.

The UI starts with every current defensive roster member of the opponent, including
reserves and practice squad, then merges injuries by stable ID. It additionally
retains report-only defensive identities, since roster/report updates need not agree.
A player absent from the injury file has no matching injury entry, not confirmed
health. Reported Out, Doubtful and Questionable override first-string colors;
reserve status, practice status and missing evidence remain separate. Offensive, special-teams and unclassified positions are excluded from the
tiles following the founder's latest correction. The collector preserves
all-position source records. First-string labels require a defensive chart
position; returner or other special-teams assignments do not establish a
defensive starting role. The
legend and full explanations are in information and player popups.

## Refresh and zero-cost operation

Upstream's [injury workflow](https://github.com/nflverse/nflverse-rosters/blob/main/.github/workflows/update_injuries.yaml)
runs at 07:07 UTC daily September–February. The
[roster workflow](https://github.com/nflverse/nflverse-rosters/blob/main/.github/workflows/update_rosters.yaml)
runs at 07:07 UTC daily year-round. These are schedules, not completion-time
guarantees. The [availability documentation](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html#nflverse-gameschedule-data)
describes schedule updates every five minutes during the season. Rechecking
more often cannot create newer injury reports than the upstream publishes.

optasy collects centrally once an hour at minute 23 and publishes one compact
static dataset through the existing GitHub Pages build. Each scheduled run makes
one download attempt per source: 96 source downloads per scheduled day,
approximately 317 MB/day at the September 13 observed sizes, plus the HTTPS requests needed
to follow release redirects. Each download permits at most three redirects and
no immediate retries. Manual/deployment runs add four download attempts.
Visitors read the same artifact and never multiply provider requests. Hourly
checks improve schedule freshness and catch delayed upstream runs; they do not
turn daily injury collection into live reporting.

The refresh workflow runs the Node adapter, tests and build; the historical
Python research suite remains part of source-change verification. A failed
collection leaves the previous published artifact unchanged and ageing. Neither
raw downloads nor the generated dataset are committed to Git. Deployment
artifacts expire after one day. See [DASHBOARD.md](DASHBOARD.md) and the checked-in
workflow for the operating commands. Source vintage, retrieval time, incomplete
coverage and stale states remain visible after successful retrieval. Requests
are bounded; rate limits fail the run without a tight retry loop.

GitHub documents [scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
as best effort: runs can be delayed or dropped under load, and schedules in
public repositories can be disabled after 60 days without repository activity.
The off-hour minute reduces contention; it cannot guarantee execution. Revive
the schedule explicitly if GitHub disables it, and verify a fresh deployment
before claiming that refresh has resumed.

The four observed downloads total approximately 13.2 MB, including a 10.1 MB
gzip depth-chart archive. GitHub's
[release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas)
specify no release bandwidth quota; they permit up to 1,000 assets per release
and require each asset to be below 2 GiB. This is not an availability guarantee
or permission to ignore abuse controls. Direct asset downloads do not require
the REST metadata API. If metadata calls are added, the
[REST limit](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
is 60 unauthenticated requests per hour per originating IP; authenticated
workflow tokens have a separate 1,000-per-hour repository allowance. Do not add
an account, paid runner, paid API, metered service or browser credential.

[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
is available for public repositories on GitHub Free, including organizations.
Its published-site limit is 1 GB, soft bandwidth limit is 100 GB/month, and
deployment timeout is ten minutes. The ten-builds-per-hour soft limit does not
apply to custom Actions publishing. Rate limiting or quota exhaustion can still
make the site unavailable; do not solve this by enabling a paid service.

[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
makes standard GitHub-hosted runners free for public repositories and Pages.
Use standard `ubuntu-latest`; larger runners are charged even for public repos.
Storage is not an unlimited allowance: GitHub Free for organizations includes
500 MB of shared artifact/Packages storage and 10 GB of cache per repository.
Keep this small site's deployment artifacts at one-day retention, avoid raw
data/cache archives, and monitor aggregate organization storage before expanding
retention. No billing settings or paid capacity are part of this integration.

## Alternatives reviewed

| Candidate                                                                                                             | Current findings and reason not selected                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Sleeper API](https://docs.sleeper.com/)                                                                              | Free noncommercial read API, no token; suggested ceiling below 1,000 calls/minute. The player map is intended to be cached and requested at most daily. It supplies player status fields, not a documented complete weekly practice/game report or NFL schedule endpoint. Its [general terms](https://support.sleeper.com/en/articles/5486620-general-terms-of-use) restrict automated extraction outside authorization; API access alone is not an unrestricted redistribution license. |
| ESPN                                                                                                                  | No current public redistribution grant or supported quota for the unofficial injury endpoint was established. The [Disney terms applying to ESPN](https://disneytermsofuse.com/english/) restrict automated extraction and public distribution without permission. Do not treat the retained historical watchlist collector as an authorized dashboard feed.                                                                                                                             |
| Official NFL/team pages                                                                                               | [NFL terms](https://www.nfl.com/legal/terms/) require consent for systematic collection. Direct scraping is not selected.                                                                                                                                                                                                                                                                                                                                                                |
| [API-Sports NFL](https://www.api-football.com/news/post/how-to-get-started-with-api-nfl-the-complete-beginners-guide) | Its August 2026 guide lists a free 100 requests/day, 10/minute plan, no card, with all endpoints; actual injury coverage requires a season coverage check. Its [terms](https://api-sports.io/terms) explicitly withhold a publication license and direct users to rights holders. No account was created.                                                                                                                                                                                |
| [BALLDONTLIE NFL](https://nfl.balldontlie.io/)                                                                        | Free access is five requests/minute for teams, players and games. Injuries and active players require the $9.99/month ALL-STAR tier; a temporary trial is not zero-cost ongoing operation.                                                                                                                                                                                                                                                                                               |
| [MySportsFeeds](https://www.mysportsfeeds.com/)                                                                       | Advertises free personal/private access; [current-season discounts](https://www.mysportsfeeds.com/register) require contacting the provider. No zero-cost public-display permission was established.                                                                                                                                                                                                                                                                                     |
| [NFLMeta](https://nflmeta.org/pricing)                                                                                | Free is 5,000 requests/month, 20/minute and 25,000 rows/month, with card verification. [Terms](https://nflmeta.org/terms) restrict Free to personal research/private evaluation and restrict dataset redistribution. No account or billing change was made.                                                                                                                                                                                                                              |

The selected integration supplies injury context, not evidence of fantasy-point
effects. Positional relevance is a qualified football hypothesis. Counts,
practice participation and game designations do not measure advantage, assign
individual coverage or justify numerical player boosts.
