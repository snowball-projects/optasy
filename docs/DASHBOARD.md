# Dashboard

Version 0.4.0 · [Open optasy](https://snowball-projects.github.io/optasy/)

## Use

Use the compact top toolbar to search by player name, team abbreviation or
position. It also holds the week selector and an `i` information button. There
is no sidebar or explanatory hero. Choose up to six players; the board starts
with two equal vertical spaces and adds narrower equal columns as selections
grow. Tile contents adapt to their width. On small screens, scroll the board
horizontally; long injury lists scroll within their tiles.

Each tile shows the player, current team and position, then the scheduled
opponent and **all available injury entries** for that team/game. Offense,
defense and special teams stay together. Remove a selection with its × button.
Injured, inactive and reserve roster members are included independently of game
participation. Twelve reviewed primary team logos are served locally; other
teams have typographic abbreviations. Player photos are omitted. See
[MEDIA.md](MEDIA.md) for asset provenance and limitations.

Injury rows keep the name, position, injury and concise game/practice badges
visible. Hover, keyboard-focus or tap a row to open a popup with the full
designations, availability explanation, source notes and supported role context.
The popup overlays the board rather than expanding a row. Information buttons
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

All matching source rows are displayed, including rows without modeled
defensive relevance. A row count is only a count. Source coverage remains
`partial` because independent completeness against original team reports has
not been established. No record for a team/game produces “coverage unknown,”
never a fabricated empty report.

Report publication time, source file modification and optasy collection time
are separate fields. The current nflverse injury CSV supplies **no report date
or time**. Information and injury popups explicitly leave that vintage unknown,
even when the file was freshly updated or retrieved. An undated Out designation
retains the need to confirm current availability in its popup details.

The UI flags a source file or collection older than 24 hours. If a future source
provides exact report timestamps, report age over 48 hours is flagged; date-only
vintage is conservatively flagged after more than three UTC calendar days.
Roster/schedule source vintages use a 24-hour policy when supplied. These are
operating reminders, not calibrated confidence thresholds.

Started games remain readable as context, not preserved pre-game advice. An
explicit report timestamp at/after kickoff is labelled. A report with unknown
vintage cannot establish when the underlying information became known. Local
clock checks update kickoff, current-week and age labels every minute without
calling a provider.

## Source collection

[DATA_SOURCES.md](DATA_SOURCES.md) records the permission basis, observed
coverage, upstream provenance limits and source/free-service schedules.

`scripts/refresh-data.mjs` downloads exactly three approved nflverse-data release
CSVs, with no key or account. The roster normalizer excludes cut/retired records
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
Provider CSVs are not saved to the repository.

There is no persistent raw-source cache or database. The published Pages
artifact is the shared cache: one hourly source collection serves every visitor.
Browsers conditionally recheck that same-origin JSON at most once per five
minutes while visible, and on return after that interval. Browser checks do
not alter source vintage or provider retrieval timestamps. Provider requests
do not increase with visitor count.

## Feed contract

`web/feed.mjs` owns the strict v2 contract; `web/example.json` is a wholly
synthetic fixture. The format is for the collector, not manual user maintenance.
It is separate from the historical Python snapshot schema.

| Field | Meaning |
| --- | --- |
| `schema_version`, `mode`, `label`, `generated_at` | Version 2, `live` or `example`, label and assembly timestamp |
| `sources` | Stable ID, publisher label, HTTPS asset/license URLs and reviewed permission note |
| `roster`, `schedule` | Source ID, original vintage or null, optional source file update, retrieval and coverage |
| `weeks` | Stable phase/season/week key, label, time window and explicitly confirmed bye teams |
| `players` | Stable source ID, name, current team, position and roster status |
| `games` | Stable game ID, week key, teams, kickoff or null, schedule/game status |
| `reports` | Exact game/week/team, source metadata and all matching injury `entries` |
| `entries` | Stable ID, name, position, injury, separate game/practice/roster statuses, status source and optional note |

Only HTTPS links without embedded credentials are accepted. IDs and enums are
validated; unknown fields, ambiguous duplicate joins, malformed timestamps,
future live inputs and unbounded lists fail. Parsing is capped at 5 MB, 6,000
players, 800 games, 1,600 reports and 250 entries per team report. Provider text
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
allowlist from `web/`, LICENSE and NOTICE to ignored `dist/`. This includes the
media manifest and only its reviewed local SVG paths; the build checks their
provenance fields and SHA-256 digests. They never package private research
inputs, league configuration or arbitrary local files.

[The existing workflow](../.github/workflows/tests.yml) checks Node and Python
on source changes, then collects/validates data and publishes main using GitHub
Pages. Hourly scheduled runs at minute 23 skip historical Python tests but run
the Node suite, collector and build. All deployments share one concurrency
group and use standard public `ubuntu-latest` runners. Pages artifact retention
is one day. There are no data commits or scheduled private-input uploads.

Collection/build failure stops publication, leaving the previous deployed site
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
membership, transfers, exact-game joins, all-position report coverage, explicit
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
