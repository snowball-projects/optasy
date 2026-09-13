import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  validateFeed,
  parseFeed,
  safeUrl,
  MAX_FEED_BYTES,
} from "../web/feed.mjs";
import {
  searchPlayers,
  currentWeek,
  comparePlayer,
  restoreSelections,
  MAX_SELECTIONS,
} from "../web/model.mjs";

const fixture = () =>
  JSON.parse(readFileSync(new URL("../web/example.json", import.meta.url)));
const now = Date.parse("2026-09-13T12:00:00Z");
const week = "example-2026-2";
const result = (data, id = "demo-kai", time = now) =>
  comparePlayer(
    data,
    data.players.find((player) => player.id === id),
    week,
    time,
  );
function rejects(mutate, match) {
  const data = fixture();
  mutate(data);
  assert.throws(() => validateFeed(data, now), match);
}

test("search matches names, accents, team and position without filtering injured current members", () => {
  const data = validateFeed(fixture(), now);
  assert.equal(searchPlayers(data, "eli")[0].roster_status, "injured-reserve");
  assert.equal(searchPlayers(data, "sam")[0].roster_status, "pup");
  assert.equal(searchPlayers(data, "drew")[0].roster_status, "practice-squad");
  assert.equal(searchPlayers(data, "river")[0].roster_status, "exempt");
  assert.equal(searchPlayers(data, "renee BUF")[0].id, "demo-renee");
  assert.equal(searchPlayers(data, "BUF wr").length, 1);
  assert.equal(searchPlayers(data, "Kai Mercer").length, 2);
  assert.deepEqual(
    searchPlayers(data, "Kai", ["demo-kai"]).map((player) => player.id),
    ["demo-same-name"],
  );
  assert.deepEqual(searchPlayers(data, "  "), []);
});

test("saved selections deduplicate stable IDs, keep current members and cap the handful", () => {
  const data = fixture();
  assert.deepEqual(
    restoreSelections(
      ["demo-kai", "demo-kai", "old-player", null, "demo-eli"],
      data,
    ),
    ["demo-kai", "demo-eli"],
  );
  assert.equal(
    restoreSelections(
      data.players.map((player) => player.id),
      data,
    ).length,
    MAX_SELECTIONS,
  );
  assert.deepEqual(restoreSelections({ id: "demo-kai" }, data), []);
});

test("current week uses explicit nonoverlapping windows and never promotes an old schedule", () => {
  const data = fixture();
  assert.equal(currentWeek(data, now).key, week);
  assert.equal(
    currentWeek(data, Date.parse(data.weeks[1].starts_at)).key,
    week,
  );
  assert.equal(currentWeek(data, Date.parse(data.weeks[1].ends_at)), null);
  assert.equal(currentWeek(data, Date.parse("2027-09-13T12:00:00Z")), null);
  assert.equal(
    comparePlayer(data, data.players[0], null, now).state,
    "no-week",
  );
  rejects((data) => {
    data.weeks[1].starts_at = data.weeks[0].starts_at;
  }, /overlap/);
});

test("complete available reports retain offense and special teams without counting an advantage", () => {
  const data = validateFeed(fixture(), now),
    comparison = result(data);
  assert.equal(comparison.opponent, "BAL");
  assert.equal(comparison.entries.length, data.reports[0].entries.length);
  assert.deepEqual(
    comparison.entries.map((entry) => entry.position),
    ["CB", "S", "EDGE", "LB", "WR", "T", "K", "LS"],
  );
  assert.ok(
    comparison.entries.find((entry) => entry.position === "CB").relevance,
  );
  assert.equal(
    comparison.entries.find((entry) => entry.position === "WR").relevance,
    null,
  );
  assert.match(
    comparison.message,
    /not an individual assignment or demonstrated fantasy effect/,
  );
  assert.equal("advantage" in comparison, false);
  assert.equal("points" in comparison, false);
});

test("game designation, practice participation and uncertain news remain separate", () => {
  const comparison = result(fixture());
  assert.equal(
    comparison.entries[0].availability,
    "Official report designates Out for this game",
  );
  assert.equal(comparison.entries[1].availability, "Availability uncertain");
  assert.match(comparison.entries[3].availability, /not guaranteed/);
  const news = comparison.entries.find(
    (entry) => entry.status_source === "news",
  );
  assert.equal(news.game_status, "Unknown");
  assert.equal(news.practice_status, "Unknown");
  assert.match(news.availability, /unknown/);
  assert.match(news.note, /news note/);
  rejects((data) => {
    data.reports[0].entries[7].game_status = "Out";
  }, /cannot supply official/);
});

test("kickers and defensive selections still see the complete report without invented relevance", () => {
  for (const id of ["demo-casey", "demo-remy"]) {
    const comparison = result(fixture(), id);
    assert.ok(comparison.entries.length > 0);
    assert.ok(comparison.entries.every((entry) => entry.relevance === null));
  }
});

test("a selected identity follows its current team after a transfer", () => {
  const data = fixture(),
    saved = { ...data.players[0] };
  data.players[0].team = "KC";
  const comparison = comparePlayer(validateFeed(data, now), saved, week, now);
  assert.equal(comparison.opponent, "DET");
  assert.equal(comparison.player.team, "KC");
  data.players = data.players.filter((player) => player.id !== saved.id);
  assert.equal(comparePlayer(data, saved, week, now).state, "not-rostered");
});

test("provider team aliases normalize without changing the original source object", () => {
  const data = fixture(),
    original = JSON.stringify(data);
  const normalized = validateFeed(data, now);
  assert.notEqual(normalized, data);
  assert.equal(JSON.stringify(data), original);
  data.players.find((player) => player.id === "demo-quinn").team = "JAC";
  data.games.find((game) => game.home === "JAX").home = "JAC";
  const comparison = result(validateFeed(data, now), "demo-quinn");
  assert.equal(comparison.opponent, "CIN");
  assert.equal(comparison.player.team, "JAX");
});

test("confirmed byes, missing schedules, missing reports and empty reports differ", () => {
  const data = fixture();
  assert.equal(result(data, "demo-ash").state, "bye");
  assert.equal(result(data, "demo-river").state, "missing-schedule");
  assert.equal(result(data, "demo-quinn").state, "missing-report");
  const empty = result(data, "demo-jo");
  assert.equal(empty.state, "report");
  assert.equal(empty.entries.length, 0);
  assert.equal(empty.report.coverage, "unknown");
  rejects((data) => {
    data.weeks[1].byes.push("BUF");
  }, /game and a confirmed bye/);
});

test("report joins require the exact game and week; older reports cannot fill a missing current report", () => {
  const data = fixture();
  data.reports = data.reports.filter(
    (report) => report.game_id !== "demo-BAL-BUF",
  );
  assert.equal(result(data).state, "missing-report");
  rejects((data) => {
    data.reports[0].week_key = "example-2026-1";
  }, /must match/);
  rejects((data) => {
    data.reports[0].team = "KC";
  }, /must match/);
  rejects((data) => {
    data.reports[0].game_id = "unknown-game";
  }, /must match/);
});

test("unknown report time stays unknown despite fresh retrieval and fresh source-file modification", () => {
  const data = fixture(),
    comparison = result(data, "demo-remy");
  assert.equal(comparison.report.reported_at, null);
  assert.equal(comparison.report.source_updated_at, data.generated_at);
  assert.equal(comparison.ageHours, null);
  assert.equal(comparison.vintagePrecision, "unknown");
  assert.equal(comparison.retrievalStale, false);
  const dateOnly = result(data, "demo-sam");
  assert.equal(dateOnly.vintagePrecision, "date");
  assert.equal(dateOnly.report.reported_at, null);
  assert.equal(dateOnly.ageHours, null);
  assert.equal(dateOnly.ageDays, 1);
});

test("stale source vintage and retrieval are separate states", () => {
  const data = fixture();
  assert.equal(result(data, "demo-casey").stale, true);
  assert.equal(result(data, "demo-casey").retrievalStale, false);
  const later = result(data, "demo-kai", now + 25 * 3600000);
  assert.equal(later.retrievalStale, true);
  assert.equal(later.rosterStale, true);
  assert.equal(later.scheduleStale, true);
  data.reports.find((report) => report.team === "NYG").reported_date =
    "2026-09-09";
  assert.equal(result(data, "demo-sam").stale, true);
});

test("fresh retrieval never hides an old or unknown source file", () => {
  const data = fixture();
  for (const metadata of [data.roster, data.schedule, data.reports[0]])
    metadata.source_updated_at = "2026-09-01T12:00:00Z";
  data.reports[0].reported_at = null;
  const comparison = result(validateFeed(data, now));
  assert.equal(comparison.retrievalStale, false);
  assert.equal(comparison.sourceFileStale, true);
  assert.equal(comparison.sourceFileAgeHours, 12 * 24);
  assert.equal(comparison.vintagePrecision, "unknown");
  assert.equal(comparison.ageHours, null);
  assert.equal(comparison.rosterStale, true);
  assert.equal(comparison.scheduleStale, true);
  assert.match(comparison.entries[0].availability, /needs confirmation/);
  data.reports[0].source_updated_at = null;
  assert.equal(result(data).sourceFileUnknown, true);
});

test("freshly republished files cannot erase explicitly old roster or schedule vintages", () => {
  const data = fixture();
  data.roster.reported_at = "2026-09-12T10:00:00Z";
  data.schedule.reported_date = "2026-09-10";
  const comparison = result(validateFeed(data, now));
  assert.equal(comparison.rosterStale, true);
  assert.equal(comparison.scheduleStale, true);
  assert.equal(comparison.sourceFileStale, false);
  assert.equal(comparison.retrievalStale, false);
});

test("postponed, canceled, TBD, rescheduled and started games preserve honest state", () => {
  const data = fixture();
  assert.equal(result(data, "demo-alex").game.status, "postponed");
  assert.equal(result(data, "demo-alex").started, false);
  assert.equal(result(data, "demo-remy").game.kickoff, null);
  assert.equal(result(data, "demo-drew").state, "canceled");
  assert.equal(result(data, "demo-quinn").started, true);
  assert.equal(
    result(data, "demo-kai", Date.parse(data.games[0].kickoff)).started,
    true,
  );
  data.games[0].kickoff = "2026-09-16T17:00:00Z";
  assert.equal(
    result(validateFeed(data, now)).game.kickoff,
    "2026-09-16T17:00:00Z",
  );
});

test("reports after kickoff stay visible but cannot silently serve as pregame evidence", () => {
  const data = fixture();
  data.games[0].kickoff = "2026-09-12T17:00:00Z";
  const comparison = result(validateFeed(data, now));
  assert.equal(comparison.reportedAfterKickoff, true);
  assert.equal(comparison.started, true);
  assert.equal(comparison.entries.length, 8);
});

test("strict parsing rejects malformed JSON, impossible dates, unbounded arrays and unsupported fields", () => {
  assert.throws(() => parseFeed("{", now), /not valid JSON/);
  assert.throws(() => parseFeed(" ".repeat(MAX_FEED_BYTES + 1), now), /5 MB/);
  rejects((data) => {
    data.players = Array(6001).fill(data.players[0]);
  }, /6000/);
  rejects((data) => {
    data.generated_at = "2026-02-30T12:00:00Z";
  }, /invalid date/);
  rejects((data) => {
    data.roster.reported_date = "2026-02-30";
  }, /calendar date/);
  rejects((data) => {
    data.players[0].fantasy_points = 14;
  }, /unsupported field/);
  rejects((data) => {
    data.reports[0].entries[0].game_status = "Probably fine";
  }, /Invalid/);
});

test("provenance validation prevents fabricated exact freshness and accidental live fixture use", () => {
  rejects((data) => {
    data.roster.reported_at = "2026-09-14T12:00:00Z";
  }, /newer than retrieval/);
  rejects((data) => {
    data.roster.source_updated_at = "2026-09-14T12:00:00Z";
  }, /newer than retrieval/);
  rejects((data) => {
    data.schedule.retrieved_at = "2026-09-14T12:00:00Z";
  }, /newer than the feed/);
  rejects((data) => {
    data.reports[0].reported_at = undefined;
  }, /timestamp or null/);
  rejects((data) => {
    data.reports[0].source_id = "unverified-source";
  }, /unknown source/);
  rejects((data) => {
    data.mode = "live";
  }, /mode must match/);
  rejects((data) => {
    data.mode = "live";
    data.sources[0].permission = "verified";
    data.generated_at = "2027-01-01T00:00:00Z";
  }, /future/);
  rejects((data) => {
    data.reports[0].reported_at = "2026-09-12T21:00:00";
  }, /timezone/);
});

test("ambiguous identities, game assignments and reports fail clearly", () => {
  rejects((data) => {
    data.players.push(data.players[0]);
  }, /Duplicate player/);
  rejects((data) => {
    data.games.push({ ...data.games[0], id: "another-game" });
  }, /same week/);
  rejects((data) => {
    data.reports.push(data.reports[0]);
  }, /Duplicate team injury/);
  rejects((data) => {
    data.reports[0].entries.push(data.reports[0].entries[0]);
  }, /Duplicate injury player/);
});

test("source links reject script URLs, cleartext, credentials and control characters", () => {
  for (const url of [
    "javascript:alert(1)",
    "http://example.org",
    "https://name:secret@example.org",
    "https://example.org/\ninjuries",
  ]) {
    assert.equal(safeUrl(url), false);
    rejects((data) => {
      data.sources[0].url = url;
    }, /HTTPS/);
  }
  assert.equal(safeUrl("https://example.org/injuries"), true);
});

test("parsing and comparisons preserve source inputs and all reported entries", () => {
  const data = fixture(),
    original = JSON.stringify(data);
  for (const player of data.players) comparePlayer(data, player, week, now);
  assert.equal(JSON.stringify(data), original);
  assert.deepEqual(parseFeed(original, now), data);
});
