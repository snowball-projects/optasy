# Game-state source review

Reviewed September 14, 2026 for the founder's game-state and refresh brief.
This records a source decision, not a claim that a live-status integration ships.

## Decision

Keep the approved nflverse schedule and show its limits explicitly. It supports
scheduled kickoff and subsequent schedule changes, but does not establish live,
finished, postponed or cancelled states. Use **Upcoming**, **Scheduled start
passed · status unconfirmed**, and **Time TBD** as appropriate. Never turn an
elapsed kickoff, score presence or a presumed game duration into confirmed play
or completion. No new provider integration is approved by this review.

## Observed schedule evidence

The public [games.csv release](https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv)
was retrieved at `2026-09-14T05:21:47Z`: 2,177,573 bytes, HTTP Last-Modified
`2026-09-14T05:16:26Z`, and 272 rows for season 2026. Its 46 columns include
`gameday`, `gametime`, scores, result and overtime, but **no game-status,
completion, cancellation or postponement field**. File update time is not a
per-game observation timestamp.

The publisher's [schedule dictionary](https://raw.githubusercontent.com/nflverse/nflreadr/main/data-raw/dictionary_schedules.csv)
defines kickoff in Eastern time regardless of venue and scores as absent for
games not yet played; it supplies no explicit final-state contract. Preserve the
existing `America/New_York` conversion and local browser display, including DST.
The adapter correctly emits only `scheduled` or `tbd` from this source. Its
comment describing elapsed kickoff as “started” should follow the more precise
unconfirmed wording in the UI.

The [availability page](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html#nflverse-gameschedule-data)
describes five-minute in-season schedule updates. The inspected
[release workflow](https://github.com/nflverse/nfldata/blob/master/.github/workflows/release_games.yml)
instead triggers when `data/games.rds` changes or by manual dispatch; it compares
with the published release and upserts changed records. This verifies the
publication mechanism, not a five-minute cron or latency guarantee for the
upstream producer. No independently inspectable producer schedule was found in
the checked workflow directory. Retain the five-minute statement as publisher
documentation, not optasy's promised freshness.

Existing use remains under the reviewed
[nflverse-data CC BY 4.0 grant](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md),
with the attribution and upstream-provenance limits in [DATA_SOURCES.md](DATA_SOURCES.md).

## Alternative considered

[TheSportsDB's official documentation](https://www.thesportsdb.com/documentation)
offers a free V1 API with shared key `123` and 30 requests/minute, but puts
livescores and V2 access in its paid tier, advertised at $9/month. Its
[terms](https://www.thesportsdb.com/docs_terms_of_use.php) allow copying and
modifying official API responses while preserving notices; they restrict free
app-store publication, require permission or another legal basis for third-party
content, and prohibit unauthorized resale. Free event lookup is not evidence
of a reliable live-status service. This review did not verify a free NFL status
endpoint with documented live/final transitions and timely coverage. Do not add
the paid live service or infer that the generic API permission alone resolves
third-party data rights.

## Implementation boundaries

- Refresh checks the latest shared same-origin artifact, not the upstream NFL
  report. Display browser check, collection time and injury-file update
  separately; injury report publication time remains unknown.
- A browser clock can transition Upcoming to scheduled-start-passed without
  downloading a roster or depth archive. Refresh the shared artifact at a modest
  visibility-aware cadence, with backoff and no overlapping requests.
- Preserve selected players, selected week, scroll and open details when data
  have not changed. Failure retains the last good view with its original age.
- A changed kickoff replaces the prior time on successful validation. An absent
  game is unknown coverage, not proof of cancellation or a bye. Explicit
  postponement/cancellation/live/final labels need a separately verified source
  field and freshness contract; this CSV cannot supply them.
- Keep centralized full-source collection hourly. Increasing its frequency
  cannot improve this source's absent live-state semantics and needlessly
  redownloads the much larger roster and depth inputs. A separate lightweight
  schedule cache is unnecessary for the honest clock-based initial display.

Test the instant before/at kickoff, unknown kickoff, a future replacement time,
stale source and wrong browser clock tolerance, DST conversion, failed/unchanged
refresh, and preservation of selections and active interactions. Score-bearing
records must still not create live/final labels.
