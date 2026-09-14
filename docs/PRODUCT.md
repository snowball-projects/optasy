# Player-to-opponent injury reports

**Founder decision: September 13, 2026.** This is the current narrow scope and
supersedes earlier dashboard and fantasy-product proposals.

## The product

A search box finds any player in the current NFL roster source. Users select a
handful; each player appears with that week's opponent and the opponent's available
defensive roster and defensive injuries. Players can be removed. The current regular-season
week is selected automatically when covered by the schedule.

Injured current roster members must not disappear because they are not
game-active. Stable source identities and the latest available team membership
drive joins. Transfers appear after the source refreshes; do not claim an
instant transaction feed. The latest founder correction limits opponent tiles to defensive players,
including defenders without reported injuries. Offense and special teams are
excluded. Collection still preserves the source reports; display filtering is
explicit. Counts describe rows, never an advantage score.

There are no league settings, roster construction, roster imports, league
accounts, ESPN Fantasy connections or multi-league management. These were
removed from the proposed direction, not deferred requirements. There is no
draft, waiver, trade, general ranking or start/sit engine.

## Contribution scope approved September 14, 2026

The founder approved defender importance (participation/performance evidence),
selected-player relevance and availability, for injured and uninjured defenders.
This supersedes earlier exclusions against contribution analysis, without
reopening leagues, roster imports, broad start/sit or fantasy-suite features.
Use traceable, separately named signals. Workload is not quality; role relevance
is not a causal benefit. No arbitrary composite, injury-count advantage,
replacement-quality assumption or point/probability boost is approved without
credible out-of-time validation and simple baselines.

The initial implementation supplies current source-backed depth context and
separate **2025 regular-season recorded events**, visibly naming historical
teams. Passing disruption uses sacks/QB hits; coverage uses passes defended and
interceptions. Bold event lines include a highest available displayed-measure
total among that opposing roster, including ties and injured players. These
are specific production comparisons, not an overall defender ranking. Missing
history is not zero; previous teams/roles may differ. Details explain broad
positional relevance and conditional absence effects. No favorable effect or
confirmed absence is inferred from an undated Out/Q report.

Current snap share was not approved because the obtainable PFR-derived family
has unresolved upstream redistribution restrictions. Modern FTN participation
is postseason-only. Recorded stat-game rows are not games played. No validated
current defensive-quality or rushing-benefit metric is available in this
release. The fixed historical baseline is deliberately not presented as current
form; adding a separate current-season, pre-match window remains future work.
See [CONTRIBUTION_REVIEW.md](CONTRIBUTION_REVIEW.md) for inputs, definitions,
rights, sample, coverage, interpretations and limitations.

## Implemented behavior

Version 0.8.0 is prepared locally and unpublished; the live site remains on 0.7.0.
The prepared version is a static search-and-report dashboard using the approved
nflverse-data release files. It supports six selected players, automatic
opponents, explicit byes, source-relative completeness, missing-report states,
unknown kickoff, started games and source/collection age warnings. Selections
are local browser IDs, not a league roster.

The founder's latest visual direction uses one compact top toolbar for search,
week selection and an information button. There is no sidebar, hero copy,
visible page heading or instructional block. Keep accessible names and
screen-reader guidance. The rest of the viewport belongs to one board of equal
vertical player tiles: at least two spaces, narrowing as selections grow to six.
Tile contents adapt to width; narrow screens scroll horizontally instead of
making the data unreadable. Each tile shows player name, current team, position,
team mark, opponent and the opponent's available defensive roster with matching injury data.

The board includes every current opponent defensive roster member, including reserve and
practice-squad members, plus unmatched defensive injury entries. Uniform-height
rows pair each name with plain position text immediately on its right. Only
reported injury and relevant availability get highlighted pills. Depth and
reserve labels belong to section headings, never repeated row badges.
Current active defenders group by their lowest supported defensive depth rank;
reserves, inactive/suspended players, practice squad, unknown depth and unknown
roster context remain separate. Missing depth cannot create a first-string
assignment. First string is not a confirmed game starter. A badge-free row
means no matching injury entry, not healthy or available. Tiles retain a 300px
minimum and scroll horizontally. Only click, tap or Enter/Space opens a popup with
full statuses, source notes, availability limits and plausible defensive-role
relevance where supported. Details do not expand the page. No direct individual
coverage assignment, replacement quality, numerical boost or demonstrated
fantasy effect is inferred.

Injury-file age and unknown report time are visible beside the matchup. Full
source attribution, separate report/file/collection/browser-check timestamps,
refresh limits, privacy and licensing live behind information buttons. Missing data, byes, started
games, fictional mode and failures retain concise visible states. Reducing copy
does not remove these distinctions or silently hide missing coverage.

All 32 team logos are hosted locally: twelve public-domain SVGs and twenty
small copyrighted thumbnails for editorial team identification. Image failure
uses ordinary team abbreviations. Portraits are omitted until a practical
licensed source is established. [MEDIA.md](MEDIA.md) owns asset provenance and
the limits of the selected public-domain determinations.

The source review found current 2026 injuries despite older documentation
claiming the feed ended after 2024. The current CSV omits report publication
dates: information details say so. File update and collection times do not
replace report vintage. Source coverage is partial until independently
established; every available matching defensive row is displayed. A missing team/week
never becomes an assertion that nobody is injured.

## Operating boundary

Use the existing public GitHub Pages deployment and one shared hourly collection.
Upstream injury and roster updates are normally daily. The Refresh button checks
the same-origin current and historical artifacts; it cannot force an upstream
update. Visible tabs check every five minutes with failure backoff up to an hour.
No overlapping requests; failed checks keep prior data. New data waits until
open details, search or focused roster/week interactions finish. No per-visitor provider
requests, account system, paid APIs, metered service or browser credentials.
GitHub schedules can be delayed or dormant. Failure retains the previous
published artifact; ageing and absent coverage remain visible.

The [source decision](DATA_SOURCES.md) records current coverage, explicit public
data licensing, limits and provenance uncertainty. The [dashboard guide](DASHBOARD.md)
owns the schema, commands, deployment and recovery. Do not require users to
maintain reports or opponents manually.

Elapsed kickoff is labelled “Start passed · status unconfirmed.” The source has
no explicit live/final status; scores never manufacture it. Browser clocks
update minute labels without downloading upstream archives. See
[GAME_STATUS_REVIEW.md](GAME_STATUS_REVIEW.md).

Outside the available schedule, the UI does not guess the NFL week or reuse an
old opponent. The current source observation covers the regular season.
Postseason phases are supported only when supplied by the source.

## Evidence and history

Distinguish reported availability, uncertain participation, plausible role
relevance and measured fantasy effects. Practice participation is not a game
guarantee; an injured defender is not proof of a weak replacement. Historical
availability calibration is not evidence of improved opposing fantasy outcomes.

Keep Python research, append-only frozen inputs, calibration and historical
draft/league utilities intact and out of the main flow. The founder reported
that the 2026 draft passed without useful optasy assistance. Do not rewrite
that history, backfill recommendations or reintroduce its scope.

The canonical repository is `snowball-projects/optasy`. optasy remains one
peer snowball project. Original software is MIT; third-party data and private
inputs retain their terms. No further repository retirement is authorized here.
