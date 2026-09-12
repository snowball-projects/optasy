# Weekly opponent-injury direction

**Owner decision recorded September 10, 2026.** This document supersedes the
draft-first roadmap and the broader scope of earlier research proposals.

## What happened

The founder reports that optasy did not become a useful draft tool before the
2026 draft and that the draft was completed without it. This was a failure to
deliver useful assistance in time, not evidence that the untested injury
hypothesis succeeded or failed. Do not backfill recommendations or describe
research dry runs as decisions used during the draft.

## Focus

For each player being considered for a weekly starting slot, identify the
scheduled opponent, inspect injuries to that opponent's defense, and explain
whether the affected roles could make the player's matchup easier. Support
comparison among the user's candidates; do not build a general fantasy suite.

Draft assistance, waiver/trade recommendations, independent all-player rankings,
generic matchup scores, betting signals and automated roster changes are out
of scope. Existing projections may supply a named, timestamped reference and
evaluation baseline. optasy's added analysis must remain injury-specific.

## MVP scope

1. Choose a week and a short list of players. Resolve each player's team,
   opponent and kickoff; flag byes, changed schedules and unmatched identities.
2. Show relevant opposing defenders, report source/time, practice and game
   designations, defensive role, recent pre-game workload and likely replacement.
   Distinguish official reports from general news/watchlist statuses.
3. Explain plausible relevance: coverage absences for pass catchers, pass-rush
   absences for quarterbacks, front-seven absences for rushing, and linebacker/
   safety coverage for tight ends and receiving backs. These are hypotheses;
   positional labels alone do not establish a direct individual matchup.
4. Compare candidates in one compact table. Separate known absence, uncertain
   availability, possible matchup opportunity and insufficient evidence. Show
   injury clusters without treating a count or summed snap share as a quality
   score or a probability. Do not assume every injured starter has a weak backup.
5. Preserve the input vintage and comparison before kickoff. Later updates and
   outcomes append to the record. No invented point boost or automatic start/sit
   verdict is needed for the first version.

The owner approved publishing a prototype on September 10, 2026 before deeper
iteration. Version 0.2.0 implements a static comparison with fictional examples
and manual/local JSON inputs. There is no live feed or Python-to-dashboard
exporter yet. See the [dashboard guide](DASHBOARD.md) for the implemented input
contract and limits. Provider refresh and page hosting remain separate concerns;
no server or account system is required for this MVP.

## Reuse and gaps

Keep `injury_snapshot.py`, `injury_signal.py`, the frozen availability model,
calibration tooling and their tests. They already preserve source evidence,
derive defender/unit availability and expose missing inputs. The dashboard
joins manually entered candidate/schedule/report records, but the research
pipeline does not yet provide an integrated current opponent feed, model
offensive usage,
measure starter-versus-replacement quality, or estimate injury-driven fantasy
effects. The snapshot loader currently uses prior-season snap context; weekly
operation needs dated current-season context using only completed prior games.

The [historical availability study](../reports/2021-2024-defender-availability-calibration.md)
measures defender participation/workload, not opposing fantasy outcomes. Its
frozen parameters and artifacts remain unchanged. The older
[injury research proposal](../reports/2026-opponent-injury-signal-proposal.md)
contains possible later evaluation methods; its draft/waiver/trade scope and
model complexity are not requirements for the initial weekly report.

Reliable current injury coverage is the immediate data gap. As checked on
September 10, 2026, [nflverse's availability documentation](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html#injury-data)
still says its injury source stopped after 2024, with no restoration date.
Use roster/depth/snap data for context, not as a substitute for injury reports.
The existing general ESPN watchlist is not an official practice-report feed;
source-neutral CSV imports can support a manually verified first report.
Verify current coverage and permitted use before choosing a recurring provider.
Missing or stale data must remain unknown, not imply that nobody is injured.

## Evidence standard

Keep observations, football hypotheses and measured effects visibly separate.
News may already be reflected in ESPN/FantasyPros projections; do not count it
twice. If numerical adjustments are explored later, test their incremental
performance against a timestamp-matched baseline on later, held-out games and
then prospectively. Weak or unstable results should leave the baseline intact.
The report can be useful for organizing evidence without claiming better
projections or proven start/sit gains.

## Canonical repository and retirement

On September 10, 2026, the owner approved and completed the transfer of the
existing public repository to `snowball-projects/optasy`, preserving history
and releases. The duplicate `adelevski/optasy-private` GitHub repository was
deleted after the reviewed preservation notes were verified. During the
separately authorized September 11 local cleanup, the old local checkout and its
retained private configuration and research/league inputs were preserved in a
private archive before the superseded folder was removed. Those inputs are not
public deployment assets.

optasy is one peer project on snowball's website, opening the deployed prototype.
Historical research and source documentation remain canonical in this repository.
The original draft/league-history utilities remain for reference; they are not
active product directions. MIT continues to cover original software, with
third-party data and private inputs retaining their own terms.
