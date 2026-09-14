# Defender contribution source review

Research observation: September 14, 2026. This review supports the bounded historical-event presentation in v0.8.0. The founder has
approved defender contribution and conditional offensive relevance analysis.
No composite quality score or numerical injury benefit has been validated.

## Recommendation

Use separately labelled **recorded defensive production** from nflverse's
`stats_player` release, with exact season/week windows and source coverage. Keep
sacks, quarterback hits, passes defended and interceptions separate. These can
identify leaders in a particular recorded activity, injured or not; they cannot
identify the best defender overall. Existing depth groups describe a reported
role, not measured workload. Neither source establishes replacement quality.

The initially useful presentation is a compact historical stat line in each
defender's details and, if space permits, clearly named production leaders in
the opposing tile. Use the same disclosed window for everyone being compared;
do not sort by an unlabelled weighted total. An unavailable leader merits
attention, but should not acquire an invented advantage score.

For a selected quarterback, sacks and quarterback hits describe recorded passing
disruption. For a receiver or tight end, passes defended and interceptions
describe coverage events without identifying who will cover that receiver.
For a running back, total tackles or tackles for loss do not isolate run defense;
do not relabel them run stops. These are product interpretations of the event
definitions, not validated effect estimates. Useful absence wording is:
“If unavailable, this recorded contribution must be replaced. The effect on
your player is unmeasured.” A Questionable designation is not a confirmed absence.

## Obtainable release files

The current [nflreadr loader](https://github.com/nflverse/nflreadr/blob/main/R/load_stats.R)
uses the `stats_player` tag, not the legacy `player_stats` tag. Direct unauthenticated
downloads succeeded during this review:

| Asset                                                                                                                                 |   Observed size | Observed coverage                                                                     | Release update, UTC |
| ------------------------------------------------------------------------------------------------------------------------------------- | --------------: | ------------------------------------------------------------------------------------- | ------------------- |
| [2026 weekly stats, gzip CSV](https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.csv.gz) |    68,465 bytes | 1,041 total rows; 575 DL/LB/DB rows, week 1, 15 games and 30 teams; KC and DEN absent | 2026-09-14 04:47:59 |
| [2025 weekly stats, gzip CSV](https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv.gz) | 1,262,421 bytes | 19,422 total rows; 10,404 regular-season DL/LB/DB rows across all 32 teams            | 2026-08-13 16:51:22 |

The inspected files have direct GSIS `player_id`, `game_id`, `team`,
`opponent_team`, `season`, `week`, `season_type`, `position` and `position_group`.
No duplicate `(player_id, team, game_id)` was observed among defensive rows;
the five inspected defensive measures had no blank values. These are observed
facts, not future integrity guarantees. Validate every subsequent input and
retain source update and retrieval times. A fresh file may still lack a game.

Join by stable identity; never by display name. Keep historic team identity in
details. A player's 2025 production for another team must not be presented as
2025 production for their current opponent. Missing rookies, missing identities,
missing games and a genuine reported zero are different cases.

## Definitions, windows and denominators

The [defensive dictionary](https://nflreadr.nflverse.com/articles/dictionary_player_stats_def.html)
defines `def_sacks`, `def_qb_hits`, `def_pass_defended`, `def_interceptions` and
`def_tackles_for_loss`. The [calculation code](https://github.com/nflverse/nflfastR/blob/master/R/calculate_stats.R)
derives these from individual play-stat credits and play-by-play context.
Sacks preserve half credits; quarterback hits are a separate field, not total
pressures. Do not sum overlapping event types into a value score. A pass defended
count is not coverage efficiency, and low counts need not imply poor coverage.

Use a fixed prior regular-season window, explicitly “2025 regular season”, for
an immediate baseline; show current-season results separately, filtered strictly
before the selected game/week. Never include the selected game's eventual
statistics in its pregame context. Do not blend seasons or silently swap one
player's missing current-season window for another season while comparing them.

These are counts, with units of credited events, no normalization and no snap,
rush or target denominator. Distinct games with a stat row measure **recorded
game coverage**, not games played: this source is built from stat events rather
than complete participation. Never invent zero rows or divide by games played
without an independently established participation source. A seasonal total can
be useful history while being unsuitable for efficiency or causal comparison.

For selected QB/WR/TE players, broad linebacker roster positions do not justify
choosing coverage-only events. Their compact row shows sacks and passes defended
together, with all four counts in details and no inferred current assignment.
Defensive-line rows retain sacks/QB hits and defensive-back rows retain PD/INT.
This mixed display describes separate recorded events, not a combined score.

## Rights decision and provenance limit

The [nflverse-data license](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md)
was retrieved again and remains CC BY 4.0. It grants sharing and adaptation of
material the publisher has authority to license. The `stats_player` release has
no observed dataset-specific exclusion. Extending optasy's existing publisher-grant
basis to this nflverse-calculated output is the narrow recommendation: retain
publisher credit, source/license links, modifications and the warranty disclaimer.
This is a data license separate from optasy's MIT software license, not a claim
of an independently verified NFL agreement. Do not directly collect NFL APIs,
add photographs, or import source code under this data decision. Review any
later restriction or rights-holder objection.

## Participation and advanced alternatives

[PFR snap counts](https://nflreadr.nflverse.com/articles/dictionary_snap_counts.html)
are game-level records with PFR player IDs, defensive snaps and defensive snap
fractions. Observed `snap_counts_2026.csv` contains 187 all-position rows across
NE, SEA, SF and LA only, updated September 11 at 16:10:08 UTC. The 2025 asset is
2,401,193 bytes. A defensible future workload view would show the source-reported
fraction for an exact game, not estimate a team denominator by summing eleven
players' snaps or averaging percentages without disclosure. The PFR-to-GSIS
mapping would need a separately reviewed identity source and ambiguity checks.

[PFR advanced stats](https://github.com/nflverse/nflverse-data/releases/tag/pfr_advstats)
include defensive targets, allowed completions/yards, blitzes, hurries, hits,
sacks, pressures and missed tackles. The 2026 weekly defensive CSV is 6,176 bytes,
50 rows, the same four teams, updated September 13 at 11:30:20 UTC. No current
pass-rush snap denominator was established. The [upstream builder](https://github.com/nflverse/nflverse-pfr)
identifies these and snap counts as PFR-derived. Its GPL code license is not a
data redistribution grant.

Do not ship the PFR family in this initial iteration. Sports Reference's
[data-use guidance](https://www.sports-reference.com/data_use.html) and
[terms](https://www.sports-reference.com/termsofuse.html) impose restrictions on
competing data services and AI/model uses; this review did not establish a
dataset-specific sublicensing arrangement that resolves those restrictions.
The public nflverse copy alone is insufficient to assert that the upstream
rights issue is resolved. This is a bounded source-selection decision, not a
claim that every reuse of an individual sports fact is prohibited.

The [availability schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
says modern FTN participation arrives after the postseason, so it cannot support
current-week workload. It describes four daily PFR snap refreshes and nightly
player-stat updates, with later statistical corrections. Actual new coverage
depends on upstream delivery; the page also has a demonstrably outdated injury
availability statement, so release content must be inspected rather than assumed.

## Implementation boundaries

Collect centrally on the existing bounded full-source refresh, never from each
visitor. Use compressed inputs with byte/expansion/row caps; retain only the
necessary defensive fields. Prior-season data need not be downloaded on every
lightweight game-state/browser check. Missing optional contribution data must
not block the existing roster, injury or freshness view.

Regression checks should cover exact-ID/team joins, transfers, half sacks,
duplicate/conflicting rows, missing versus zero, absent teams, postseason
exclusion, selected-game exclusion, equal comparison windows and honest labels.
Prediction would require a separate prospective/out-of-time evaluation against
simple baselines, controlling leakage and available-as-of evidence. This review
provides neither that validation nor an individual matchup/point-boost model.
