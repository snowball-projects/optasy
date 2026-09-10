# Dashboard MVP

Live: <https://snowball-projects.github.io/optasy/> · v0.2.0

The dashboard is a static, dependency-free prototype. It starts with explicitly
fictional examples. It does not fetch current NFL injuries, projections, rosters
or schedules, and it does not call the Python availability model.

## Use it

1. Choose **New snapshot**, select the week, and use **+** to add candidates,
   their opponents and kickoffs. Matchups for the same team/week are reused.
   Team order is only for joining opponents; no home-field adjustment exists.
2. Select candidates to compare. **Add injury** records an opposing defender's
   role, status, practice participation, optional prior snap share, likely
   replacement, source and report time. Manual reports have partial coverage.
3. Expand a defender for possible positional relevance and context. The rules
   are broad hypotheses, not assigned coverage matchups or measured effects.
   No absence count, probability or fantasy-point score ranks candidates.
4. **Download snapshot** preserves a JSON file; **Import snapshot** restores it.
   Imports and edits stay in the tab's memory. Closing or reloading loses them
   unless downloaded. Replacing a populated personal snapshot prompts first.

Each team/week report has one source vintage. Additional manual entries use
that same timestamp; adding a defender never retimestamps earlier evidence.
Prepare/import a new snapshot for a later report. Original downloaded/imported
files are not overwritten. Sample snapshots remain labelled as samples even
after edits; start a new snapshot before entering a real weekly comparison.

The first version has no individual edit/delete controls. A correction can be
made in a downloaded JSON copy and reimported, or entered in a new snapshot.
Inputs are manual and not independently verified. Only enter data you may use;
never put credentials in a snapshot. Downloaded files are not published.

## Portable input

Use [the fictional example](../web/sample.json) as a complete template. The
dashboard format is a compact presentation contract, separate from Python's
raw-source snapshot manifests; a verified exporter is a future integration.

| Field                            | Meaning                                                                                                       |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `schema_version`                 | `1`                                                                                                           |
| `kind`                           | `sample` for demonstrations; `user` for user-entered/imported data                                            |
| `label`, `season`, `captured_at` | Snapshot name, season and timezone-aware ISO timestamp                                                        |
| `players`                        | Unique `id`, `name`, NFL `team` abbreviation and `position` (QB/RB/WR/TE/K)                                   |
| `games`                          | `week` (1–18), distinct `home`/`away` teams, timezone-aware `kickoff`; at most one game per team/week         |
| `reports`                        | One entry per `week`/`team`: `source`, optional HTTPS `url`, `observed_at`, `coverage`, `defenders`           |
| `coverage`                       | `partial`, `unknown`, or `reviewed` (user assertion, not independent verification)                            |
| Each defender                    | `name`, `role` (CB/S/DB/EDGE/DI/DL/LB), `status`, `practice`, `snap_share`, optional `replacement` and `note` |

Statuses: Out, Questionable, Doubtful, IR, PUP, Unknown. Practice: Unknown,
Did not practice, Limited, Full. `snap_share` is a percentage (0–100) of prior
defensive snaps, or `null`; it is not a probability or quality rating. Explain
the prior workload period in the note. No probability is inferred from
Questionable, Doubtful or practice status.

Imports are capped at 2 MB, 1,000 players/games/reports each and 100 defenders
per report. Duplicate IDs, games, reports and defender names are rejected.
Source URLs require HTTPS without credentials. Text is rendered as text, never
HTML. Reports cannot be newer than their containing snapshot; user snapshots
cannot be future-dated beyond a five-minute clock tolerance.

Only matching team/week evidence is shown. Reports at or after kickoff are
excluded from pre-game comparisons. Started games are labelled historical.
Reports older than 48 hours receive a review flag, an operational reminder
rather than a validated injury-confidence threshold. Missing reports or empty
relevant lists never imply a healthy defense. Kicker effects are not modeled.

## Develop and deploy

Node 24, Python 3.12. The web app has no npm dependencies.

```sh
npm ci
npm test
npm run build
npm run dev
```

The preview runs at `http://127.0.0.1:8786/`. The builder copies an explicit
allowlist from `web/`, plus LICENSE and NOTICE, into ignored `dist/`; it never
packages credentials, Python inputs, league configuration or arbitrary files.
Run the Python suite from the README as well when changing the research code.

`.github/workflows/tests.yml` verifies both suites, builds the static artifact
and deploys main to GitHub Pages. Repository Pages must use GitHub Actions.
There is no server, database, scheduled data collection or paid API dependency.
Hosting uses the existing GitHub Pages setup, with no added paid service.
To revive elsewhere, run the build and serve `dist/`; update the canonical URL
and project/source links for the new home. Standard Git commits and release
tags preserve prior source versions.

## Next iteration

Verify a current injury source's coverage and permitted use; add dated current
schedule/roster context and an exporter from verified Python snapshots; then
try a real weekly shortlist. Automatic refresh, numerical injury adjustments
and additional fantasy features are not part of this release.
