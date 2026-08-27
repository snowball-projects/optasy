# 2026 opponent-injury signal proposal

**Status:** Proposed research design; not frozen and not yet used in recommendations  
**Prepared:** August 25, 2026  
**Decision owner:** Human project owner

## Purpose

Test whether current injuries to an opponent's defense contain incremental
predictive information about an offensive player's fantasy output after using a
fresh ESPN/FantasyPros projection as the commodity baseline.

The working hypothesis is not simply "injured safety means upgrade the deep
receiver." The defensible hypothesis is:

> An offensive player's exposure to lost defensive capacity, after accounting
> for the injured defender's expected lost snaps, role, replacement quality,
> unit-level injury clusters, and the offensive player's usage profile, explains
> some of the error left by a timestamp-matched consensus projection.

The null hypothesis is that the incremental effect is zero because the injury
does not matter, the defense compensates, or the baseline already prices it in.
Until the null is challenged out of sample, this is a candidate signal rather
than demonstrated alpha.

## Where the signal belongs

The signal is expected to be more useful for weekly lineup, waiver, and trade
decisions than for a season-long draft. At draft time, only injuries with a
credible recovery window can affect known early matchups. Unknown future
injuries must not be imputed, and a current injury must not be treated as if it
persists for all 18 weeks.

For the September 7 draft, the opponent-injury output should initially be
reported as secondary evidence or a tiebreak between practically equivalent
season-long candidates. The established season projection and league-specific
value over replacement remain the primary draft signal.

## Prediction unit, target, and information set

- Observation: offensive player-game at decision timestamp `t`.
- Primary target: realized full-PPR fantasy points in that game.
- Mechanism targets: routes, targets, air yards, carries, expected fantasy
  points, and relevant efficiency measures when available.
- Allowed information: only projections, reports, depth charts, snap counts,
  schedules, and player usage available at or before `t`.
- Forbidden information: final inactive status, later depth-chart changes,
  in-game participation, or outcomes not yet available at `t`.

The prediction and its inputs must be appended with source timestamps. Later
refreshes cannot overwrite earlier vintages.

The implemented `injury_signal.py --freeze` path writes one immutable prediction
artifact per source snapshot, hashes its inputs and outputs, and refuses a
second write to the same prediction ID. The August 25 preseason artifact is a
pipeline dry run; it is not a final-status forecast and activates no historical
availability prior.

## Baseline

For player `i`, week `w`, and timestamp `t`, put ESPN and FantasyPros projected
full-PPR points on the same scoring basis:

```text
B_iwt = w_E * ESPN_iwt + w_F * FantasyPros_iwt
w_E >= 0, w_F >= 0, w_E + w_F = 1
```

The weights are estimated only on earlier weeks with rolling-origin validation:

```text
(w_E, w_F) = argmin sum_train (actual_iw - B_iwt)^2
```

Until enough valid timestamped observations exist, the declared fallback is
`w_E = 0.5` and `w_F = 0.5`. This is a temporary neutral prior, not a claim that
the sources are equally accurate. If only one point-projection source is
available, it is preserved as a named one-source baseline rather than silently
treated as an ensemble.

Ranks are downstream outputs. The model combines projected points, not ordinal
ESPN and FantasyPros ranks.

## Defensive lost-capacity feature

For each potentially unavailable defender `d`:

```text
L_dwt = lost_snap_fraction_dwt
        * healthy_snap_share_d
        * standardized_quality_gap_d
```

Where:

- `lost_snap_fraction` is the expected fraction of normal snaps lost given all
  information available at `t`, including the official practice trajectory and
  game designation. It handles both absence and a limited role.
- `healthy_snap_share` is estimated from strictly prior healthy games and is
  shrunk toward the defender-role average when the sample is small.
- `standardized_quality_gap` is the projected starter-minus-replacement quality
  difference within the defender's role. An injured starter with a comparable
  backup should produce little signal.

Lost capacity is aggregated into a defensive-role vector for interior line,
edge, linebacker, cornerback, and safety. A separate cluster feature represents
multiple losses in the same unit; this is not assumed to be the simple sum of
individual injuries.

## Offensive exposure and matchup relevance

Each offensive player receives a strictly lagged usage/exposure vector `a_iwt`,
such as deep-target share, outside/slot usage, middle-of-field target share,
route participation, receiving-back usage, and inside/outside rushing share.

A predeclared relevance matrix `M` permits only football-plausible interactions,
including:

- deep passing exposure with cornerback, safety, and pass-rush capacity;
- outside and slot receiving exposure with the relevant cornerback roles;
- tight-end and receiving-back exposure with linebacker, safety, and slot
  coverage capacity;
- inside/outside rushing exposure with defensive interior, edge, and linebacker
  capacity; and
- quarterback passing exposure with pass rush and coverage capacity.

The matrix declares candidate relationships; it does not assign fantasy points
from human intuition. Coefficients are learned and regularized.

```text
X_iwt = a_iwt' * M * H_opponent,wt
```

## Incremental injury model and final projection

Fit the injury feature only to the error remaining in the contemporaneous
baseline:

```text
actual_iw - B_iwt
    = alpha_position
    + beta_position * X_iwt
    + beta_cluster * cluster_opponent,wt
    + error_iw
```

Use a hierarchical or ridge-regularized model so sparse position/archetype cells
shrink toward zero. All hyperparameters are selected with time-ordered training
and validation; random train/test splits are not allowed.

The incremental adjustment and final weekly projection are:

```text
delta_iwt = E[actual_iw - B_iwt | information at t]
mu_iwt    = B_iwt + delta_iwt
```

This is intentionally not a fixed `90% consensus + 10% injury` score. The
baseline supplies the forecast level. The injury model receives only the weight
supported by its ability to predict residual error. If an injury is already
priced into ESPN/FantasyPros, its estimated incremental adjustment should shrink
toward zero.

Human intuition receives zero direct numerical weight. It is used to propose and
approve hypotheses, choose defensible information sets, and review failure
modes—not to add undocumented fantasy points.

## Draft ranking

For a draft candidate `i`:

```text
AdjustedDraftVORP_i
    = baseline_season_points_i
    - league_replacement_points_position(i)
    + sum(delta_iw for early weeks with credible injury information)
```

The best current choice is then evaluated conditionally on draft state:

```text
ChoiceValue_i
    = AdjustedDraftVORP_i
    + expected_future_roster_value(state after selecting i)
```

The second term is the role of the existing availability model. Availability
does not determine player quality; it estimates the opportunity cost of taking
one player instead of waiting for another.

## Scope of the first custom model

The first custom mean-adjustment model should be entirely injury-conditioned.
It includes exposure, replacement quality, and cluster effects because those are
necessary to translate an injury into a matchup effect; they are not separate
alphas.

Weather, betting markets, generic strength of schedule, recent-point streaks,
and manual narrative boosts are excluded from the first model. They can be
reconsidered only after the injury hypothesis is evaluated cleanly against the
commodity baseline. Baseline disagreement is retained as an uncertainty flag,
not automatically treated as expected value.

## Prospective snapshots

For every game, preserve at least three vintages when available:

1. Before the first official practice report.
2. Immediately after the final game-status report.
3. After official inactive lists, for a separate last-minute decision model.

The model used at one vintage may not consume information from a later vintage.
Recording baseline revisions between vintages helps reveal how much injury news
the commodity sources already incorporated.

## Evaluation and activation gate

Compare `baseline + injury` with the frozen baseline on the exact same
player-games:

- MAE, RMSE, mean error, and interval coverage for forecast performance;
- paired loss differences with bootstrap uncertainty;
- calibration of any exceedance or start probabilities; and
- lineup/draft regret for decision performance.

Mechanism outcomes and fantasy outcomes are reported separately. A receiver can
earn more deep opportunities without realizing more fantasy points in one noisy
game.

No production weight is activated merely because a retrospective coefficient
has the expected sign. Activation requires improvement on a time-ordered holdout
and then continued prospective reporting in 2026. If the incremental effect is
small or unstable, the correct result is to keep the commodity projection and
stop investing in a larger injury model.

## Data-source strategy and current constraint

- ESPN supplies league scoring, projections, and an existing prior for player
  and defensive-unit quality.
- FantasyPros can supply a second projection baseline, expert dispersion,
  injuries, practice status, and probability-of-playing data.
- Official NFL reports are the authoritative availability record.
- nflverse can supply schedules, identifiers, historical outcomes, snap counts,
  depth charts, and historical injuries through 2024. Its live injury pipeline
  is currently unavailable after the 2024 season, so it cannot be the sole 2026
  injury source.

The immediate engineering priority is a timestamped, append-only snapshot
pipeline and source-neutral schema. Model complexity comes only after the data
contract is reliable.
