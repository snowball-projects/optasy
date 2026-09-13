# Player-to-opponent injury reports

**Founder decision: September 13, 2026.** This is the current narrow scope and
supersedes earlier dashboard and fantasy-product proposals.

## The product

A search box finds any player in the current NFL roster source. Users select a
handful; each player appears with that week's opponent and the opponent's full
available injury report. Players can be removed. The current regular-season
week is selected automatically when covered by the schedule.

Injured current roster members must not disappear because they are not
game-active. Stable source identities and the latest available team membership
drive joins. Transfers appear after the source refreshes; do not claim an
instant transaction feed. Reports retain offensive, defensive and special-teams
entries. Counts describe rows, never an advantage score.

There are no league settings, roster construction, roster imports, league
accounts, ESPN Fantasy connections or multi-league management. These were
removed from the proposed direction, not deferred requirements. There is no
draft, waiver, trade, general ranking or start/sit engine.

## Implemented behavior

Version 0.3.0 is a static search-and-report dashboard using the approved
nflverse-data release files. It supports six selected players, automatic
opponents, explicit byes, source-relative completeness, missing-report states,
unknown kickoff, started games and source/collection age warnings. Selections
are local browser IDs, not a league roster.

Report entries show separate game designation and practice participation.
Expandable context explains plausible defensive-role relevance where supported
by positional labels. No direct individual coverage assignment, replacement
quality, numerical boost or demonstrated fantasy effect is inferred.

The source review found current 2026 injuries despite older documentation
claiming the feed ended after 2024. The current CSV omits report publication
dates: the UI says so. File update and collection times do not replace report
vintage. Source coverage is partial until independently established; every
available matching row is displayed. A missing team/week never becomes an
assertion that nobody is injured.

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
