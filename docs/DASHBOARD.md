# Dashboard

Prepared local version 0.8.0, unpublished · [Open live sideline (0.7.0)](https://snowball-projects.github.io/sideline/)

## Use

Use the compact top toolbar to search by player name, team abbreviation or
position. It also holds the week selector and an `i` information button. There
is no sidebar or explanatory hero. Choose up to six players; the board starts
with two equal vertical spaces and adds narrower equal columns as selections
grow. Tile contents adapt to their width. On small screens, scroll the board
horizontally; long injury lists scroll within their tiles.

Each tile shows the player, current team and position, then the scheduled
opponent, **every available defensive roster member**, and defensive injury entries
for that team/game. Offensive and special-teams positions are excluded. Remove a selection with its × button.
Injured, inactive and reserve roster members are included independently of game
participation. All 32 team logos are served locally with source and use records. Player photos are omitted. See
[MEDIA.md](MEDIA.md) for asset provenance and limitations.

Section headings and subtle dividers group source-backed depth levels, unknown
depth, reserves, inactive/suspended players, practice squad and unknown roster
context. The lowest current defensive depth rank determines an active player's
section when multiple assignments exist. First string is chart context, not a
confirmed game starter. Reserve and unknown roster status take precedence over
depth for grouping.

Uniform 68px rows put position immediately to the right of the name, as plain
identity text. Only reported body-part injuries and meaningful game/practice
statuses get highlighted pills. No per-row depth, reserve, active or healthy
badges appear. A row without pills does not establish health. Missing report
coverage remains visible; source vintage and freshness stay in information.
Long injury descriptions are abbreviated in pills and retained fully in details.
Tiles retain a 300px minimum width and scroll horizontally. Click, tap or press
Enter/Space on a row to open a popup with full
designations, availability explanation, source notes and supported role context.
Hover and focus alone never open details. Escape, outside click and moving
focus away dismiss the popup, which overlays the board without expanding a row. Information buttons
hold source links, separate report/file/collection timestamps, refresh limits,
privacy, licenses, image credits and snowball/Operations links. Compact visible
states remain for missing coverage, byes, changed game status and data failures.

The week defaults from the current schedule window, with an optional week
selector. A confirmed bye differs from a missing schedule. Kickoffs display
in the user's local timezone. New schedules replace old opponents/kickoffs
after the next successful collection. Selections use stable player IDs, so
transfers follow current source team membership. A saved player absent from the
latest roster gets an explicit missing-identity card.

Selections persist only in this browser's local storage, as at most six IDs;
removing a player updates that list. Storage failure does not prevent use.
Search, selection and role context do not contact providers. There are no
accounts, league settings/imports, manual report forms or roster management.

The labelled fictional example is an explicit fallback when current data cannot
load. It never silently replaces current data. A failed attempt to return to NFL
players keeps the fictional warning. It does not replace saved NFL selections.

## Report interpretation

Game designation and practice participation are separate. Full practice is not
a guarantee of playing; a blank source game designation is not “healthy.”
Popup role context describes broad football possibilities, not individual
coverage, replacement quality, proven fantasy effects or a start/sit decision.

Matching defensive rows are displayed, including defenders without modeled
positional relevance. Offensive, special-teams and unclassified positions are
excluded from the tiles by the founder's latest instruction. The collector
still preserves all source report rows. A row count is only a count. Source coverage remains
`partial` because independent completeness against original team reports has
not been established. No record for a team/game produces “coverage unknown,”
never a fabricated empty report.

Report publication time, source file modification and sideline collection time
are separate fields. The current nflverse injury CSV supplies **no report date
or time**. Information and injury popups explicitly leave that vintage unknown,
even when the file was freshly updated or retrieved. An undated Out designation
retains the need to confirm current availability in its popup details.

The UI flags a source file or collection older than 24 hours. If a future source
provides exact report timestamps, report age over 48 hours is flagged; date-only
vintage is conservatively flagged after more than three UTC calendar days.
Roster/schedule source vintages use a 24-hour policy when supplied. These are
operating reminders, not calibrated confidence thresholds.

Elapsed kickoff reads “Start passed · status unconfirmed”, not live or final.
The current schedule has no status field; score presence cannot prove final.
Explicit source states remain supported by the schema but cannot be inferred
from this CSV. See [GAME_STATUS_REVIEW.md](GAME_STATUS_REVIEW.md). An
explicit report timestamp at/after kickoff is labelled. A report with unknown
vintage cannot establish when the underlying information became known. Local
clock checks update kickoff, current-week and age labels every minute without
calling a provider.

## Historical defender signals

The second row line is fixed **2025 regular-season recorded production** for
its named historical team(s), including players now on different teams. For
selected QB/WR/TE players, defensive-line passing disruption uses sacks and QB
hits; defensive-back coverage uses passes defended and interceptions. Linebacker
rows show sacks and passes defended together because the coarse roster position
does not establish a current rush/coverage assignment. RB/other selections receive
broad role context and full historical counts in details, without an invented
rushing-efficiency/benefit metric. All units are credited events; no snap,
pass-rush or target denominator is available. Half sacks are preserved.

Bold event lines contain at least one highest available displayed-event total
among the current opposing roster's historical records; positive ties count,
missing records do not become zero, and there is no composite ranking. The
popup names the leading measure, all four counts, historical team subtotals,
stat-game record count (not games played), source/file/retrieval times, role
relevance and conditional absence limits. Reported Out/Q does not by itself
confirm current participation. [CONTRIBUTION_REVIEW.md](CONTRIBUTION_REVIEW.md)
owns the source and metric decision.

`web/contributions.json` is a separate optional browser artifact with strict
schema/provenance/size validation in `web/contribution.mjs`. Its version 1 schema
contains season 2025/REG, source metadata, partial-coverage team/game/stat-row/
player counts and GSIS-keyed per-player records with historical-team subtotals.
A missing record is unknown history. Optional history failure preserves the core
injury view and any previously validated historical data, with a detail notice.

## Source collection

[DATA_SOURCES.md](DATA_SOURCES.md) records the permission basis, observed
coverage, upstream provenance limits and source/free-service schedules.

`scripts/refresh-data.mjs` downloads exactly four approved nflverse-data release
files (three CSVs and one gzip CSV), with no key or account. The roster normalizer excludes cut/retired records
while retaining current reserve, inactive, practice-squad and exempt membership.
Ambiguous identities fail instead of guessing teams. `gsis_id` is primary;
`gsis_it_id` provides a namespaced fallback when necessary.

The schedule normalizer uses documented Eastern local kickoff time with daylight
saving. It derives Tuesday-to-Tuesday NFL week windows from dated games and
extends them for delayed games; overlapping windows fail clearly. Byes require
a complete regular-season schedule. Current observation contains the regular
season; postseason phases are supported only when supplied by the source.
Unknown kickoff remains unknown. Current opponent joins always use exact
season/week/game/team, never a player-name match or a report from another week.

Downloads use a 30-second deadline, a 20 MiB per-source bound, at most three
HTTPS redirects on the release-host allowlist, and no automatic retry loop.
HTTP 429 reports Retry-After when present and fails the run. One failed source,
invalid payload or ambiguous join rejects the whole update. Unrecognized game
or practice statuses remain unknown with their raw source value in a note.
Only a validated feed is atomically written to ignored `web/current.json`.
Provider CSVs are not saved to the repository. Depth history is gzip-decoded
with a 160 MiB expansion cap and a two-million-row limit; only each team's
latest snapshot is retained. See DATA_SOURCES.md for observation semantics.

The same `npm run refresh` also runs `scripts/contribution-data.mjs --optional`, collecting
one fixed 2025 `stats_player` gzip CSV under the separately reviewed CC BY 4.0
basis. It caps compressed input at 4 MiB, expansion at 20 MiB, 40,000 source rows,
and the browser artifact at 1.5 MB. Only REG defensive records and four event
counts survive; duplicates/invalid identities fail. The validated artifact is
atomically written to ignored `web/contributions.json`. Historical collection
failure is nonfatal: a previously written local artifact is retained only after
revalidation; otherwise it is removed. A fresh checkout may have no prior history.
Live builds omit missing or invalid historical data while still requiring the
validated core feed. Core collection/validation failure retains the prior Pages
deployment. No upstream request is delegated to visitors.

There is no persistent raw-source cache or database. The published Pages
artifact is the shared cache: one hourly source collection serves every visitor.
Browsers recheck the two same-origin JSON artifacts every five minutes while
visible, and on return after that interval. Failures back off to 10/20/40/60
minutes; manual Refresh bypasses the cadence, never an active request. It shows
loading, changed, unchanged or error status with browser check time. Data waits
while details/search/week/row interaction is active, then updates with selections
and scroll preserved. Clock-derived depth/freshness expiration also waits safely
while showing an updates-ready notice. Unchanged status controls retain focus. Browser checks do
not alter source vintage or provider retrieval timestamps. Provider requests
do not increase with visitor count.

## Feed contract

`web/feed.mjs` owns the strict v2 contract; `web/example.json` is a wholly
synthetic fixture. The format is for the collector, not manual user maintenance.
It is separate from the historical Python snapshot schema.

| Field                                             | Meaning                                                                                                        |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `schema_version`, `mode`, `label`, `generated_at` | Version 2, `live` or `example`, label and assembly timestamp                                                   |
| `sources`                                         | Stable ID, publisher label, HTTPS asset/license URLs and reviewed permission note                              |
| `roster`, `schedule`                              | Source ID, original vintage or null, optional source file update, retrieval and coverage                       |
| `weeks`                                           | Stable phase/season/week key, label, time window and explicitly confirmed bye teams                            |
| `players`                                         | Stable source ID, name, current team, position and roster status                                               |
| `games`                                           | Stable game ID, week key, teams, kickoff or null, schedule/game status                                         |
| `depth` (optional for older/fictional feeds)      | Source metadata and latest team observations: stable player ID, team, position, rank and observation timestamp |
| `reports`                                         | Exact game/week/team, source metadata and all matching injury `entries`                                        |
| `entries`                                         | Stable ID, name, position, injury, separate game/practice/roster statuses, status source and optional note     |

Only HTTPS links without embedded credentials are accepted. IDs and enums are
validated; unknown fields, ambiguous duplicate joins, malformed timestamps,
future live inputs and unbounded lists fail. Parsing is capped at 5 MB, 6,000
players, 800 games, 1,600 reports, 250 entries per team report and 12,000 depth
assignments. Provider text
is rendered as text, never HTML. No credentials are accepted by the schema.

## Build, deploy and revive

Use Node 24 and Python 3.12; see [README.md](../README.md) for setup.

```sh
npm ci
npm test
node --check web/app.mjs
npm run build
npm run dev
```

An offline build contains the labelled fictional fallback. To prepare the
published current-data artifact:

```sh
npm run refresh
npm run build:live
```

`build:live` requires validated live data whose source IDs, asset URLs and license
URLs match the reviewed collector definitions. Both build paths copy a fixed
allowlist from `web/`, LICENSE and THIRD-PARTY-NOTICES.md to ignored `dist/`. This includes the
media manifest and only its reviewed local SVG/PNG paths; the build checks their
provenance fields and SHA-256 digests. They never package private research
inputs, league configuration or arbitrary local files.

[The existing workflow](../.github/workflows/tests.yml) checks Node and Python
on source changes, then collects/validates data and publishes main using GitHub
Pages. Hourly scheduled runs at minute 23 skip historical Python tests but run
the Node suite, collector and build. All deployments share one concurrency
group and use standard public `ubuntu-latest` runners. Pages artifact retention
is one day. There are no data commits or scheduled private-input uploads.

Core collection or required build validation failure stops publication, leaving the previous deployed site
unchanged. Its timestamps age naturally. GitHub schedules are best effort and
can be disabled after 60 days of repository inactivity. To revive, enable the
existing workflow in Actions if disabled, dispatch it manually and verify the
successful deployment and its `current.json` timestamps. Investigate failed
source formats/permissions before changing the adapter; do not retimestamp
an old report or enable paid capacity to hide failure.

The app's no-data state offers retry and a fictional example. Runtime refresh
failure retains the last loaded data with a visible warning until success.
To relocate, build and serve `dist/`, update canonical/source links and arrange
one free shared collection with the same guards. Git history preserves the
previous manual prototype at `ba7bdc8`; Python research and frozen artifacts
remain in their canonical locations.

## Verification

Offline Node tests cover source-shaped CSV parsing, injured/current identity
membership, transfers, exact-game joins, all-position source preservation, defense-only display, explicit
byes, schedule changes and timezone transitions, stale/unknown vintage,
publication provenance, bounded downloads and failure behavior. The 44-test
Python research suite remains credential-free.

Before claiming delivery, also check desktop, narrow mobile and keyboard
search/add/remove flows; persistent selections; missing reports; labelled
fictional fallback after a failed return; source links; live workflow completion;
and the deployed version/data counts. Check two through six columns, narrow
board scrolling, every injury row's keyboard/touch details, popup dismissal and
focus handling, and logo/fallback rendering. Do not equate a local build with a
live deployment.

Browser module and stylesheet URLs carry the release version. When releasing
changes, bump the package version and the `v=` URLs in index/app/model together
so cached earlier modules cannot be combined with a newer feed contract.
