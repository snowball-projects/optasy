# 2021–2024 defender-availability calibration

**Status:** Historical v0 accepted as an experimental availability prior; no fantasy-point adjustment activated  
**Prepared:** August 25, 2026  
**Source snapshot:** `20260825T183952Z`  
**Decision owner:** Human project owner

## Decision

Game designations contain strong held-out information about whether an
injury-listed defender participates on defense. Practice status does not show a
clear incremental improvement for the binary participation target, but it does
show a small held-out improvement for expected defensive-snap retention.

Accordingly, the eligible 2026 experimental feature is:

- report-status-only probability for whether a listed defender takes any
  defensive snap;
- report-plus-practice expected defensive-snap retention; and
- a deterministic zero participation/retention override for an official `Out`
  designation.

These estimates may quantify expected lost defensive snap capacity. They may
not change an offensive player's projection or rank until the separate
opponent-injury residual model passes its own out-of-sample and prospective
gates.

## Hypotheses and population

The data-generating population is defensive player-weeks appearing on an NFL
injury or practice report during the 2021–2024 regular seasons. It is not a
sample of all defenders; unlisted healthy players are deliberately absent.

- H1: final game-report status improves defensive-participation and
  snap-retention forecasts over a constant rate for injury-listed defenders.
- H2: final practice status adds information beyond game-report status.
- Null for each comparison: paired held-out loss improvement is zero.

The availability question is upstream of the fantasy question. This experiment
does not test whether an absent cornerback, safety, linebacker, or pass rusher
causes additional fantasy points for an opponent.

## Targets and prediction-time information

For defender `d` and game `g`:

```text
participated_dg = 1(defensive_snaps_dg > 0)

retention_dg = min(
  defense_snap_share_dg / mean(last four strictly prior defensive appearances),
  1
)
```

Retention is evaluated only with at least two prior defensive appearances.
The cap at one prevents expanded roles from being interpreted as negative lost
capacity.

Allowed predictors are the latest report status and practice status timestamped
before scheduled kickoff. Current-game snap counts are targets only. The player
ID crosswalk captured in 2026 is used only to join historical reports to target
snap counts; it is not a predictor.

## Split, model, and baselines

- Train: 2021–2023, 7,922 defender-weeks.
- Temporal test: 2024, 3,039 defender-weeks.
- Retention test subset: 2,898 defender-weeks with a prior baseline.
- Constant baseline: training-set mean.
- Intermediate baseline: empirical report-status rate shrunk toward the
  constant rate.
- Candidate model: empirical report-plus-practice cell rate shrunk toward the
  report-status rate.
- Coherence constraint: expected snap retention cannot exceed the deployed
  report-status-only probability of defensive participation.
- Fixed shrinkage: 20 pseudo-observations at each parent level. This is a
  declared heuristic, not a tuned optimum.

No random train/test split or role/injury-specific search was used. Uncertainty
uses 5,000 paired bootstrap samples with NFL week as the resampling block, so
same-week observations are not treated as independent.

## Information-timing and join audit

The build compares every source `date_modified` with scheduled kickoff in US
Eastern time converted to UTC.

- 10,962 pre-kickoff defensive source rows were eligible.
- 3 post-kickoff rows were excluded.
- 8 rows without a scheduled game were excluded; these correspond to a
  no-outcome/canceled-game condition rather than an injury absence.
- 10,962 unique pre-kickoff player-weeks remained.
- 1 player-week could not be linked to a PFR snap ID and was excluded.
- 10,961 player-weeks entered the train/test dataset.

The first attempted build failed when it encountered a post-kickoff timestamp.
The implementation was revised to exclude and audit such rows. A second build
surfaced the canceled-game case. A third pass added nflverse's player-ID
crosswalk, reducing unmatched records from 1,745 to 1. The failed source
snapshots remain append-only local evidence rather than being overwritten.

During live-feature integration, a review found that the independently shrunk
`Questionable + Full` retention estimate exceeded the chosen report-only
participation probability, violating `E[retention] <= P(participation)`. The
coherence constraint above was added and the unchanged temporal split was
rerun. Held-out retention MAE moved from 0.24430 to 0.24438; the activation
decision did not change.

## Held-out 2024 results

Lower loss is better. Intervals are 95% paired week-block bootstrap intervals
for the improvement of the report-plus-practice model over the named baseline.

| Target / model | Held-out loss | Improvement over baseline (95% interval) |
|---|---:|---:|
| Participation: constant rate | Brier 0.23641 | — |
| Participation: report status | Brier 0.11515 | — |
| Participation: report + practice | Brier 0.11413 | vs constant: 0.12228 [0.11665, 0.12800] |
| Participation: report + practice | Brier 0.11413 | vs report: 0.00103 [−0.00042, 0.00253] |
| Retention: constant mean | MAE 0.43725 | — |
| Retention: report status | MAE 0.24956 | — |
| Retention: report + practice | MAE 0.24438 | vs constant: 0.19286 [0.18375, 0.20212] |
| Retention: report + practice | MAE 0.24438 | vs report: 0.00518 [0.00351, 0.00678] |

H1 is supported on this temporal test. H2 is not established for binary
participation because its interval includes zero. H2 is supported for
retention, but the incremental effect is small; it should not be described as a
large edge.

## Limitations and freeze

- This is a retrospectively assembled temporal test, not prospective evidence.
- Historical source files may contain later corrections even though individual
  predictor rows are required to be timestamped before kickoff.
- Only injury-listed defenders are calibrated; these rates are invalid as an
  unconditional prior for all defenders.
- The baseline uses the last four defensive appearances, not the last four team
  games, and can reach into the prior season.
- Defender role, injury type, age, and previous injury history are excluded to
  avoid sparse retrospective subgroup search.
- Snap retention measures workload, not defender quality, replacement quality,
  or causal opponent impact.
- Provider-supplied play probabilities are not mechanically combined with the
  historical workload model; doing so would require a separately evaluated
  conditional-retention rule.

The source snapshot, train/test years, target definitions, feature categories,
shrinkage constant, exclusion rules, and week-block bootstrap are frozen for
the initial 2026 prospective run. Any revision must be versioned and evaluated
alongside—not in place of—this v0.

The deployable frozen parameters are committed as
[`config/defender-availability-v0.json`](../config/defender-availability-v0.json).

## Reproduction

```sh
.venv/bin/python scripts/calibrate_defender_availability.py build \
  --source-snapshot data/injury/calibration/sources/20260825T183952Z
```

Derived CSV and JSON outputs are local and ignored under
`data/injury/calibration/current/`. The committed
[`source manifest`](artifacts/20260825T183952Z-source-manifest.json) preserves
URLs, sizes, and SHA-256 hashes; the committed
[`evaluation JSON`](artifacts/20260825T183952Z-availability-evaluation.json)
preserves the machine-readable result. Raw source bytes remain local.
