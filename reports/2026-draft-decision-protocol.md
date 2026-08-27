# 2026 draft decision protocol

**Status:** Development draft; not frozen  
**Prepared:** August 25, 2026  
**Must be frozen:** Before the configured league draft

## Confirmed objective

At each configured-team pick, rank the players who are still available by projected
season-long starter value above a league-specific positional replacement level.
Championship-relevant upside, downside, positional scarcity, and next-pick
availability are secondary evidence. They do not currently enter an opaque
weighted score.

This objective was explicitly chosen by the user on August 25, 2026. It avoids
claiming that a fragile full-season simulator can estimate championship
probability precisely enough to drive the opening picks.

## Decision and target

The decision is which available player to select, conditional on the observed
draft state. The primary model output is value over replacement (`VORP`):

```text
ESPN projected season points - projected points of the marginal league starter
```

Replacement levels are recalculated from the same frozen ESPN snapshot:

- 12 QBs, 24 RBs, 24 WRs, and 12 TEs fill the direct starter slots.
- The 12 highest remaining RB/WR/TE projections fill the league's FLEX slots.
- The lowest projection selected at each position is that position's replacement
  level.

The candidate order is conditional: a low probability of reaching a pick does
not make a player worse if he actually remains available.

## Availability as a supporting model

Availability estimates answer whether selecting a player now is preferable to
waiting for him or a comparable alternative. They do not determine player value.

For the top 60 pre-draft consensus players in each historical season:

```text
draft residual = actual league pick - pre-draft consensus rank
```

The current estimator blends the empirical global residual distribution with
the position-specific distribution. The position weight is `n / (n + 20)`, and
binary availability probabilities receive a Beta(1,1) prior. Inputs are pinned
DynastyProcess snapshots from August 30, 2024 and August 29, 2025, both before
their respective league drafts.

Both historical seasons have already influenced model design. Therefore all
2024–2025 results are exploratory; they are not an untouched holdout. The 2026
draft is the prospective evaluation.

## Information available at prediction time

Allowed inputs are:

- The frozen ESPN projection, PPR rank, ADP, auction values, ownership, and
  injury status.
- The frozen FantasyPros-derived consensus rank and expert-rank dispersion from
  DynastyProcess.
- League rules and draft order recorded before the draft.
- Draft selections observed before the recommendation is produced.
- The frozen historical availability calibration described above.

Future selections, player outcomes, and any data refreshed after the recorded
decision timestamp are forbidden.

Expert-rank standard deviation is disagreement among rankers, not calibrated
outcome uncertainty. It must not be presented as a predictive interval.

## Baselines

Preserve these recommendations at every material pick:

1. FantasyPros/DynastyProcess consensus best available.
2. ESPN PPR rank best available, approximating the visible ESPN/auto-draft
   market.
3. Highest ESPN-projected VORP.
4. The user's stated early RB/WR policy, with QB2 as a strong but defeasible
   later preference.
5. Optasy's final recommendation after the human reviews the disclosed secondary
   evidence.

## Prospective recording

For each configured-team pick, append rather than overwrite:

- Data and code version.
- Recommendation timestamp and observed picks.
- Available candidate set.
- Every baseline's preferred player.
- Optasy's preferred player, strongest alternative, and reversal conditions.
- The user's final selection and any reason for overriding Optasy.

Live selections may condition the next calculation. Model parameters, replacement
rules, and baseline definitions may not be changed during the draft.

The live implementation writes `live-rankings.csv` and
`current-recommendation.json` after every observed board change. When the next
unfilled ESPN slot belongs to the configured team, it also writes a content-addressed,
append-only decision package under `data/draft/decisions/`. The package records
the observed picks, source-snapshot hash, draft-code hash, complete candidate
set, recommendation, strongest alternative, baselines, and reversal conditions.
The user's final choice and override reason still require a separate human entry.

ESPN does not currently supply a usable season projection for kickers. No
cross-position value is imputed. If a required lineup slot reaches its final
possible pick, the tool uses a labeled required-position fallback and consensus
order as the within-position tiebreaker.

## Evaluation

Evaluate the availability submodel immediately after the draft with Brier score
as the primary metric and log loss as secondary. Calibration plots are
descriptive because candidate-pick observations from one sequential draft are
not independent.

Evaluate player-value forecasts and draft decisions separately after the season:

- Projection MAE and bias for the candidate set.
- Realized points and value above replacement for the selected player and the
  recorded alternatives.
- Lineup contribution and weeks started.
- Differences from each preserved baseline.

Realized player outcomes are noisy and do not, by themselves, prove that a draft
decision was good or bad. Expected decision quality and realized results must be
reported separately.

## Excluded from v1

- Opponent-specific adjustments in the recommendation order.
- A direct championship-probability simulator.
- A combined injury or expert-disagreement uncertainty score.
- An arbitrary composite score mixing VORP with availability.
- Retrospective tuning presented as prospective validation.

## Decisions required before freezing

1. Confirm whether ESPN is acceptable as the sole point-projection source for
   v1 or whether a second projection source must be added.
2. Define a practical-equivalence threshold within which secondary scarcity
   evidence may reverse the VORP order.
3. Define how large a QB/TE advantage must be to override the early RB/WR policy.

Until those decisions are recorded, `opening-decisions.csv` is a transparent
planning table rather than a frozen autonomous draft policy.
