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

## Implemented behavior

Version 0.6.0 is a static search-and-report dashboard using the approved
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
practice-squad members, plus unmatched defensive injury entries. Rows show the name,
three equal position/injury/status pills and depth on the right, all on one
uniform-height row. Tiles stop narrowing at 300px and scroll horizontally.
First-string defenders form a separate group above the other defenders.
Current depth rank 1 at a defensive chart position is labeled first string, not a confirmed game starter.
Reported injury designations override depth colors. Reserve, practice and
unknown statuses remain distinct; the color legend is behind information. Only clicking, tapping or pressing Enter/Space on a row opens a popup with
full statuses, source notes, availability limits and plausible defensive-role
relevance where supported. Details do not expand the page. No direct individual
coverage assignment, replacement quality, numerical boost or demonstrated
fantasy effect is inferred.

Source attribution, report/file/collection timestamps, refresh limits, privacy
and licensing live behind information buttons. Missing data, byes, started
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
Upstream injury and roster updates are normally daily. No per-visitor provider
requests, account system, paid APIs, metered service or browser credentials.
GitHub schedules can be delayed or dormant. Failure retains the previous
published artifact; ageing and absent coverage remain visible.

The [source decision](DATA_SOURCES.md) records current coverage, explicit public
data licensing, limits and provenance uncertainty. The [dashboard guide](DASHBOARD.md)
owns the schema, commands, deployment and recovery. Do not require users to
maintain reports or opponents manually.

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
