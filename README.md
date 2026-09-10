# Optasy

A snowball project.

[Open the dashboard](https://snowball-projects.github.io/optasy/) ·
[Dashboard guide](docs/DASHBOARD.md)

Optasy (Optimized Fantasy) studies whether injuries to an opposing NFL defense
give a candidate starter a more favorable matchup. Its current focus is weekly
lineup decisions, using existing providers' projections as comparison baselines.

**Direction changed September 10, 2026:** The founder reports that Optasy was
not useful in time for the 2026 draft and that the draft was completed without
it. Draft assistance is no longer an active objective. The
[weekly opponent-injury direction](docs/PRODUCT.md) is the current scope;
older draft plans and broader research proposals are historical context.

This public repository contains reusable Python scripts and synthetic
configuration. Credentials, private league data and generated artifacts stay
local. The dashboard is a published prototype with fictional examples and
manual/local snapshot input. It has no automatic live injury feed.

## What exists

- A compact weekly dashboard: candidate shortlists, opponent matching,
  position-linked injury context, manual entry and local JSON import/download.
- Timestamped, append-only injury and projection snapshots with SHA-256
  verification and source-neutral CSV imports.
- Defender matching against roster, depth-chart and prior-snap context.
- Experimental defender participation and workload-retention estimates, gated
  by report source and information vintage.
- Defender-exposure and defensive-unit burden tables, with replacement
  candidates and explicit missing information.
- A frozen historical availability study and credential-free tests.

The browser connects candidates to opponents using entered/imported schedules
and reports. It does not fetch current player or injury data, run the Python
availability model, or estimate fantasy-point effects. In the Python research
pipeline, replacement candidates come from depth order; replacement quality is not estimated. The current live
context loader uses prior-season snaps and needs current-season, pre-cutoff
context before regular weekly use.

Draft-board and league-history scripts remain available for reference. Their
presence is not a commitment to resume draft, waiver or trade features.

## Design

| Component | Purpose | Main output |
| --- | --- | --- |
| `export_espn_history.py` | Preserve historical league activity | Raw JSON + SQLite |
| `draft_board.py` | Build and freeze draft decisions | CSV + JSON artifacts |
| `injury_snapshot.py` | Capture point-in-time research inputs | Verified snapshot directory |
| `injury_signal.py` | Derive defender and unit availability features | Exposure and burden tables |
| `calibrate_defender_availability.py` | Fit and evaluate historical availability priors | Frozen model + evaluation |

The history exporter uses a local cache; its explicit `--refresh` option replaces
cached raw JSON. Generated data is excluded from Git. Prospective snapshots and
decision records are append-only: once an outcome is known, their original
inputs and recommendations must not be rewritten.

## Quick start

For the dashboard (Node 24; no npm dependencies):

```sh
npm ci
npm test
npm run build
npm run dev
```

The preview opens at `http://127.0.0.1:8786/`. See the
[dashboard guide](docs/DASHBOARD.md) for snapshots and deployment.

For the existing research scripts, Python 3.12 is used in CI.

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

## Historical utilities

These commands preserve the earlier implementation; they are not the active
product roadmap.

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

## Injury research workflow

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
- [Current weekly scope and next steps](docs/PRODUCT.md)
- [Historical opponent-injury research proposal](reports/2026-opponent-injury-signal-proposal.md)
- [Historical draft decision protocol](reports/2026-draft-decision-protocol.md)

The next step is to verify a current injury source and try the prototype on a
real weekly shortlist, connecting the research pipeline to its input format.
A working comparison must distinguish unknown
coverage from a healthy defense and possible matchup relevance from a measured
fantasy advantage. See the [current direction](docs/PRODUCT.md).

## License

Copyright 2026 snowball. Unless otherwise noted, Optasy's original source code,
documentation, configuration examples, and committed research artifacts are
available under the [MIT License](LICENSE). See [NOTICE](NOTICE) for
source attribution. Third-party packages and data remain under their respective
licenses and terms; private inputs and generated artifacts excluded from this
repository are not included in the license grant.
