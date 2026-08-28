# Optasy

A snowball project.

Optasy (Optimized Fantasy) is a personal fantasy-football analytics project. It
turns projection, draft, league-history, and injury data into small,
explainable decision artifacts instead of an opaque recommendation score.

This public repository contains the reusable implementation and synthetic
configuration only. Private league data, credentials, generated boards, and
prospective decision records stay local.

## What it does

- Archives authenticated ESPN league history as immutable JSON and a queryable
  SQLite database.
- Builds a projection-aware draft board from ESPN data and FantasyPros-derived
  consensus rankings published by DynastyProcess.
- Estimates whether candidates are likely to survive until a later pick using
  historically observed draft residuals.
- Captures append-only injury and projection snapshots with timestamps and
  SHA-256 manifests.
- Combines injury status with nflverse roster, depth-chart, and snap context to
  estimate defender availability and workload retention.
- Preserves baselines, alternatives, uncertainty, and reversal conditions so a
  recommendation can be evaluated after the fact.

The live-draft watcher is experimental and read-only. Optasy does not automate
draft selections or scrape the browser interface. The current product decision
is to test an established synchronized draft assistant before investing further
in custom live-draft integration.

## Design

| Component | Purpose | Main output |
| --- | --- | --- |
| `export_espn_history.py` | Preserve historical league activity | Raw JSON + SQLite |
| `draft_board.py` | Build and freeze draft decisions | CSV + JSON artifacts |
| `injury_snapshot.py` | Capture point-in-time research inputs | Verified snapshot directory |
| `injury_signal.py` | Derive defender and unit availability features | Exposure and burden tables |
| `calibrate_defender_availability.py` | Fit and evaluate historical availability priors | Frozen model + evaluation |

Generated data is deliberately excluded from Git. Prospective snapshots and
decision records are append-only: once an outcome is known, their original
inputs and recommendations must not be rewritten.

## Quick start

Python 3.12 is used in CI.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

The complete unit suite uses synthetic fixtures and requires neither
credentials nor a local `data/` directory.

## Private configuration

Create local copies of the examples before using provider-backed commands:

```sh
cp config/league.example.yaml config/league.yaml
cp .env.example .env
```

Fill in the local files with your own ESPN league ID and, when authenticated
access is required, ESPN cookies. `FANTASYPROS_API_KEY` is optional. Both local
files are ignored by Git; never commit credentials or private league data.

## Workflows

Archive selected ESPN seasons:

```sh
.venv/bin/python scripts/export_espn_history.py --seasons 2024 2025
```

Refresh and build a draft board, or rebuild from the newest preserved snapshot:

```sh
.venv/bin/python scripts/draft_board.py refresh
.venv/bin/python scripts/draft_board.py build
```

Freeze the exact pre-draft inputs after review:

```sh
.venv/bin/python scripts/draft_board.py freeze-sources
```

Capture and verify an injury-research snapshot:

```sh
.venv/bin/python scripts/injury_snapshot.py capture \
  --week 1 \
  --vintage preseason \
  --fetch-espn-nfl-injuries \
  --fetch-nflverse

.venv/bin/python scripts/injury_snapshot.py verify
.venv/bin/python scripts/injury_signal.py --freeze
```

Reproduce the historical defender-availability model from a preserved source
snapshot:

```sh
.venv/bin/python scripts/calibrate_defender_availability.py build \
  --source-snapshot data/injury/calibration/sources/<snapshot-id>
```

Network-backed commands depend on provider availability and terms. ESPN's
fantasy endpoints used here are undocumented, so adapters are isolated and
their raw responses are preserved before normalization.

## Evidence and limits

The frozen availability study uses 2021–2023 for fitting and 2024 as a temporal
test. Across 10,961 player-week records, adding practice participation to report
status materially outperformed a global play-rate baseline. Its incremental
play-probability improvement over report status alone was small and uncertain;
the corresponding workload-retention improvement was small but positive. These
are availability estimates, not evidence that a defender's absence changes an
opposing player's fantasy points.

- [Defender-availability calibration](reports/2021-2024-defender-availability-calibration.md)
- [Frozen evaluation](reports/artifacts/20260825T183952Z-availability-evaluation.json)
- [Opponent-injury signal design](reports/2026-opponent-injury-signal-proposal.md)
- [Draft decision protocol](reports/2026-draft-decision-protocol.md)

Optasy remains a focused personal decision tool, not a hosted product. The next
substantive step is an independent projection-source audit and a comparison
against an established live draft assistant.

## License

Copyright 2026 snowball. Unless otherwise noted, Optasy's original source code,
documentation, configuration examples, and committed research artifacts are
available under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for
source attribution. Third-party packages and data remain under their respective
licenses and terms; private inputs and generated artifacts excluded from this
repository are not included in the license grant.
