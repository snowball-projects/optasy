# optasy

A snowball project. Find an NFL player and see their opponent's injury report.

[Open optasy](https://snowball-projects.github.io/optasy/) ·
[Product scope](docs/PRODUCT.md) · [Dashboard guide](docs/DASHBOARD.md) ·
[Data sources](docs/DATA_SOURCES.md) · [Image credits](docs/MEDIA.md)

Search the current roster source by name, team or position and select up to six
players. A compact toolbar holds search, the week selector and an information
button. Below it, one board starts with two equal vertical spaces and divides
into narrower tiles as players are added. Small screens scroll the board
horizontally. Each tile resolves the week's opponent and displays the opponent's **entire available defensive roster**, merging injury entries by
stable identity and retaining report-only players. Offense and special teams
are excluded from opponent tiles. Each player has a status-colored border and a short text label.
Hover, focus or tap a player for roster, depth and injury details. Remove a player with its × button.
Injured and reserve roster members remain searchable. Selections stay in the
browser; there are no accounts or league connections.

The dashboard defaults to the current regular-season NFL week when the schedule
covers it. Explicit byes, missing schedules/reports, changed kickoffs, started
games and old collections have distinct states. Broad defensive-role context
is available within report entries. Injury counts do not measure advantage;
optasy supplies no point boosts, rankings or start/sit verdicts.

All 32 team logos are served locally with recorded provenance and use bases. Player photos are omitted pending a practical
licensed source. Source details, timestamps, privacy and licensing sit behind
the information buttons; the board keeps only compact operational exceptions.

## Current data and honest limits

The dashboard uses roster, schedule, injury and depth-chart releases from **nflverse-data**
under its explicit **CC BY 4.0 data license**. The integration preserves all
matching injury rows and credits the source; independent completeness against
original team reports is not established. Source report dates are currently
absent. Information popups distinguish that unknown vintage from file
modification and optasy collection times.

A shared GitHub Actions run checks the four sources hourly at minute 23.
Upstream injury and roster files normally update daily, not live. Schedules
update more often. Runs can be delayed, fail or become dormant; a failed
collection leaves the previous site visible with ageing timestamps. Data gaps
never imply a healthy opponent.

See [the source review](docs/DATA_SOURCES.md) for the September 13 evidence,
publisher-license basis, upstream provenance limitation, refresh schedules and
free quotas. The existing public GitHub Pages site and standard public Actions
runners require no API key or new paid service. Browser requests stay on the
site's origin. A labelled fictional example is available when current data
cannot be loaded.

## Develop

Node 24 and Python 3.12:

```sh
npm ci
npm test
node --check web/app.mjs
npm run build
npm run dev
```

Preview: `http://127.0.0.1:8786/`. An offline build includes the interface and
fictional fixture. To collect the approved public data before building:

```sh
npm run refresh
npm run build
```

The collector writes ignored `web/current.json` atomically after validation.
Raw provider files are never written to the repository. Builds copy an explicit
public allowlist to `dist/`; private inputs and historical research are excluded.
`npm run build:live` requires validated current data, and is the publication path.

The Python research suite remains credential-free:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Both suites run on source changes. The separate data-refresh run verifies the
Node suite and static build. Deployment and recovery are documented in
[the dashboard guide](docs/DASHBOARD.md).

## Preserved research

The founder's September 13 direction replaces the earlier manual comparison
flow. League settings, roster construction/imports, ESPN Fantasy connections,
multi-league management, drafts, waivers, trades, general rankings and a
start/sit engine are outside product scope.

The Python implementation and frozen evidence remain available for research:

| Source                                                                           | Purpose                                     |
| -------------------------------------------------------------------------------- | ------------------------------------------- |
| [injury_snapshot.py](scripts/injury_snapshot.py)                                 | Append-only, verified point-in-time inputs  |
| [injury_signal.py](scripts/injury_signal.py)                                     | Experimental defender and unit availability |
| [calibrate_defender_availability.py](scripts/calibrate_defender_availability.py) | Historical calibration and evaluation       |
| [export_espn_history.py](scripts/export_espn_history.py)                         | Historical private league exports           |
| [draft_board.py](scripts/draft_board.py)                                         | Historical draft experiments                |

These utilities are not part of the browser flow or active roadmap. Local
credentials, league configuration, private history and generated artifacts
remain ignored. Provider access in historical scripts is not authorization for
public collection or redistribution.

The [frozen availability study](reports/2021-2024-defender-availability-calibration.md)
measures defender participation and workload, not opposing fantasy outcomes.
The [older research proposal](reports/2026-opponent-injury-signal-proposal.md)
and [draft protocol](reports/2026-draft-decision-protocol.md) remain historical
records. The previous dashboard is preserved in Git at
`ba7bdc8d97004ed1f22be6d9f97075722f6a622b`.

## License

Copyright 2026 snowball. Original software, documentation and synthetic fixtures
use the [MIT License](LICENSE). Published nflverse data retain **CC BY 4.0**;
third-party packages and data retain their own terms. See [NOTICE](NOTICE).
Team logos have their own documented [public-domain bases and trademark
status](docs/MEDIA.md). The software license does not cover team marks, private
inputs or personal writing.

[Operations](https://snowball-projects.github.io/operations/#optasy)
