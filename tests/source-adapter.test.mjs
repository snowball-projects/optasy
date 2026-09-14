import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  parseCsv,
  normalizeRoster,
  normalizeSchedule,
  normalizeInjuries,
  normalizeSources,
  normalizeDepthCsv,
  easternTimestamp,
} from "../scripts/source-adapter.mjs";
import {
  fetchSource,
  sourceDefinitions,
  collectFeed,
  PUBLICATION_POLICY,
} from "../scripts/refresh-data.mjs";
import { gzipSync } from "node:zlib";
import { validateFeed } from "../web/feed.mjs";

const read = async (name) =>
  readFile(new URL(`./fixtures/source-${name}.csv`, import.meta.url), "utf8");
const [rosterCsv, scheduleCsv, injuryCsv] = await Promise.all(
  ["roster", "schedule", "injuries"].map(read),
);
const depthCsv = await read("depth");
const roster = parseCsv(rosterCsv),
  schedule = parseCsv(scheduleCsv),
  injuries = parseCsv(injuryCsv);
const NOW = "2026-09-13T06:00:00.000Z",
  UPDATED = "2026-09-12T11:35:55.000Z";
const metadata = {
  source_id: "nflverse-injuries",
  reported_at: null,
  source_updated_at: UPDATED,
  retrieved_at: NOW,
};
const definition = sourceDefinitions(2026)[0];
const response = (text, headers = {}, status = 200) =>
  new Response(text, {
    status,
    headers: { "content-type": "text/csv", ...headers },
  });

test("bounded CSV parser handles quoted commas, escaped quotes and multiline cells", () => {
  assert.deepEqual(
    parseCsv('\uFEFFname,note\r\n"A, B","line 1\nline ""2"""\r\n'),
    [{ name: "A, B", note: 'line 1\nline "2"' }],
  );
  for (const broken of [
    "a,a\n1,2",
    "a, a\n1,2",
    "a,b\n1",
    'a,b\n"bad,2',
    'a,b\n"ok"x,2',
  ])
    assert.throws(() => parseCsv(broken));
  assert.throws(() => parseCsv("a\nlarge", { maxBytes: 3 }), /limit/);
  assert.throws(() => parseCsv("a\n1\n2", { maxRows: 1 }), /row limit/);
});

test("roster retains current injured, inactive, defense and practice-squad identities; filters released/retired", () => {
  const players = normalizeRoster(roster, 2026);
  assert.equal(players.length, 6);
  assert.equal(
    players.find((p) => p.id === "gsis:fiction-ir").roster_status,
    "reserve",
  );
  assert.equal(players.find((p) => p.id === "gsis:fiction-lb").position, "LB");
  assert.equal(
    players.find((p) => p.id === "gsis:fiction-lb").roster_status,
    "inactive",
  );
  assert.equal(
    players.find((p) => p.id === "gsis-it:fiction-it").roster_status,
    "practice-squad",
  );
  assert.equal(
    players.find((p) => p.id === "gsis:fiction-transfer").team,
    "CAR",
  );
  assert.ok(players.every((p) => !/retired|historical/.test(p.id)));
});

test("ambiguous transfers or unidentifiable rostered players fail instead of disappearing or guessing", () => {
  const duplicate = { ...roster[0], team: "CAR" };
  assert.throws(
    () => normalizeRoster([...roster, duplicate], 2026),
    /Conflicting current roster/,
  );
  assert.throws(
    () =>
      normalizeRoster(
        [{ ...roster[0], gsis_id: "", gsis_it_id: "", espn_id: "" }],
        2026,
      ),
    /no stable source identity/,
  );
  const old = { ...roster[0], week: "2", status: "CUT" };
  assert.ok(
    !normalizeRoster([...roster, old], 2026).some(
      (p) => p.id === "gsis:fiction-qb",
    ),
  );
});

test("schedule timestamps use documented Eastern time with daylight saving; invalid dates fail", () => {
  assert.equal(
    easternTimestamp("2026-09-13", "13:00"),
    "2026-09-13T17:00:00.000Z",
  );
  assert.equal(
    easternTimestamp("2027-01-16", "16:30"),
    "2027-01-16T21:30:00.000Z",
  );
  assert.throws(
    () => easternTimestamp("2026-02-30", "13:00"),
    /Invalid calendar/,
  );
  assert.throws(
    () => easternTimestamp("2026-03-08", "02:30"),
    /does not exist/,
  );
});

test("schedule preserves unknown kickoff and postseason, with partial coverage never inventing byes", () => {
  const result = normalizeSchedule(schedule, 2026);
  assert.equal(result.games.length, 3);
  assert.equal(result.coverage, "partial");
  assert.equal(result.games[1].kickoff, null);
  assert.equal(result.games[1].status, "tbd");
  assert.equal(result.weeks[2].key, "2026-WC-19");
  assert.equal(result.weeks[0].starts_at, "2026-09-08T04:00:00.000Z");
  assert.ok(result.weeks.every((week) => week.byes.length === 0));
  assert.throws(
    () =>
      normalizeSchedule(
        [...schedule, { ...schedule[0], game_id: "duplicate" }],
        2026,
      ),
    /Conflicting/,
  );
});

test("complete 272-game season allows explicit regular-season byes", () => {
  const teams =
    "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split(
      " ",
    );
  const rows = [];
  for (let week = 1; week <= 18; week++) {
    const date = new Date("2026-09-13T00:00:00Z");
    date.setUTCDate(date.getUTCDate() + 7 * (week - 1));
    for (let pair = 0; pair < 16; pair++) {
      if ((week === 5 && pair < 8) || (week === 6 && pair >= 8)) continue;
      rows.push({
        ...schedule[0],
        week: String(week),
        game_id: `fixture-${week}-${pair}`,
        gameday: date.toISOString().slice(0, 10),
        away_team: teams[pair * 2],
        home_team: teams[pair * 2 + 1],
      });
    }
  }
  const result = normalizeSchedule(rows, 2026);
  assert.equal(result.coverage, "complete");
  assert.equal(result.weeks.find((week) => week.week === 5).byes.length, 16);
  assert.equal(result.weeks.find((week) => week.week === 6).byes.length, 16);
});

test("changed schedule replaces kickoff; conflicting or overlapping schedule fails clearly", () => {
  const changed = schedule.map((row) =>
    row.game_id === "fiction-2026-1" ? { ...row, gametime: "16:25" } : row,
  );
  assert.equal(
    normalizeSchedule(changed, 2026).games[0].kickoff,
    "2026-09-13T20:25:00.000Z",
  );
  const overlapping = schedule.map((row) =>
    row.game_id === "fiction-2026-1" ? { ...row, gameday: "2026-09-23" } : row,
  );
  assert.throws(
    () => normalizeSchedule(overlapping, 2026),
    /overlaps week windows/,
  );
});

test("reports preserve all available offense, defense and special-teams rows and separate unknown report vintage", () => {
  const games = normalizeSchedule(schedule, 2026).games;
  const reports = normalizeInjuries(injuries, 2026, games, metadata);
  const report = reports.find((item) => item.team === "CAR");
  assert.equal(report.entries.length, 4);
  assert.deepEqual(report.entries.map((entry) => entry.position).sort(), [
    "CB",
    "G",
    "P",
    "WR",
  ]);
  assert.equal(report.reported_at, null);
  assert.equal(report.source_updated_at, UPDATED);
  assert.equal(report.retrieved_at, NOW);
  assert.equal(report.coverage, "partial");
  assert.equal(
    report.entries.find((entry) => entry.position === "G").game_status,
    "Not listed",
  );
  assert.equal(
    report.entries.find((entry) => entry.position === "G").practice_status,
    "Full",
  );
  assert.equal(
    reports.reduce((sum, item) => sum + item.entries.length, 0),
    injuries.length,
  );
  assert.equal(
    reports.some((item) => item.week_key === "2026-REG-2"),
    false,
  );
});

test("unmatched reports and undated duplicate injury rows fail without silent narrowing", () => {
  const games = normalizeSchedule(schedule, 2026).games;
  assert.throws(
    () =>
      normalizeInjuries(
        [{ ...injuries[0], team: "BUF" }],
        2026,
        games,
        metadata,
      ),
    /cannot join one scheduled game/,
  );
  assert.throws(
    () => normalizeInjuries([...injuries, injuries[0]], 2026, games, metadata),
    /Duplicate injury row/,
  );
  assert.throws(
    () =>
      normalizeInjuries(
        [{ ...injuries[0], full_name: "" }],
        2026,
        games,
        metadata,
      ),
    /no player name/,
  );
  const report = normalizeInjuries(
    [{ ...injuries[0], report_status: "Unfamiliar status" }],
    2026,
    games,
    metadata,
  )[0];
  assert.equal(report.entries[0].game_status, "Unknown");
  assert.match(report.entries[0].note, /Unfamiliar status/);
});

test("source normalization outputs source metadata without laundering retrieval into report time", () => {
  const sources = sourceDefinitions(2026).map(({ key, ...source }) => ({
    ...source,
    permission: "example",
  }));
  const feed = normalizeSources({
    rosterCsv,
    scheduleCsv,
    injuryCsv,
    season: 2026,
    sources,
    generatedAt: NOW,
    metadata: {
      roster: { ...metadata, source_id: "nflverse-roster" },
      schedule: { ...metadata, source_id: "nflverse-schedule" },
      injuries: metadata,
    },
  });
  assert.doesNotThrow(() => validateFeed(feed, Date.parse(NOW)));
  assert.equal(feed.mode, "example");
  assert.equal(feed.roster.reported_at, null);
  assert.equal(feed.schedule.source_updated_at, UPDATED);
  assert.equal(feed.reports[0].source_updated_at, UPDATED);
});

test("downloader allowlists exact datasets and HTTPS release redirects", async () => {
  await assert.rejects(
    fetchSource({ ...definition, url: "https://example.com/private" }),
    /fixed dataset allowlist/,
  );
  let calls = 0;
  const result = await fetchSource(definition, {
    now: () => new Date(NOW),
    fetchImpl: async () =>
      ++calls === 1
        ? response(
            "",
            {
              location:
                "https://release-assets.githubusercontent.com/fixture.csv",
            },
            302,
          )
        : response("a\n1", {
            "last-modified": "Sat, 12 Sep 2026 11:35:55 GMT",
          }),
  });
  assert.equal(calls, 2);
  assert.equal(result.metadata.source_updated_at, UPDATED);
  assert.equal(result.metadata.reported_at, null);
  await assert.rejects(
    fetchSource(definition, {
      fetchImpl: async () =>
        response("", { location: "https://example.com/escaped" }, 302),
    }),
    /outside the HTTPS/,
  );
  await assert.rejects(
    fetchSource(definition, {
      fetchImpl: async () =>
        response("", { location: "http://github.com/insecure" }, 302),
    }),
    /outside the HTTPS/,
  );
});

test("downloader bounds size, rejects HTML, future source clocks and rate limits without retry", async () => {
  await assert.rejects(
    fetchSource(definition, {
      maxBytes: 3,
      fetchImpl: async () => response("a\n1234"),
    }),
    /download size limit/,
  );
  await assert.rejects(
    fetchSource(definition, {
      fetchImpl: async () =>
        response("<html>", { "content-type": "text/html" }),
    }),
    /content type/,
  );
  await assert.rejects(
    fetchSource(definition, {
      now: () => new Date(NOW),
      fetchImpl: async () =>
        response("a\n1", { "last-modified": "Sun, 13 Sep 2026 09:00:00 GMT" }),
    }),
    /future/,
  );
  let calls = 0;
  await assert.rejects(
    fetchSource(definition, {
      fetchImpl: async () => {
        calls++;
        return response("", { "retry-after": "3600" }, 429);
      },
    }),
    /HTTP 429/,
  );
  assert.equal(calls, 1);
});

test("source collection fails as a whole on one unavailable feed and never retries", async () => {
  let calls = 0;
  await assert.rejects(
    collectFeed({
      season: 2026,
      inspect: true,
      now: () => new Date(NOW),
      fetchImpl: async (url) => {
        calls++;
        return String(url).includes("injuries")
          ? response("", {}, 503)
          : response(String(url).includes("roster") ? rosterCsv : scheduleCsv);
      },
    }),
    /injuries:.*HTTP 503/,
  );
  assert.equal(calls, 4);
});

test("inspection requests four fixed sources and returns aggregate source/report vintage separately", async () => {
  let calls = 0;
  const { summary } = await collectFeed({
    season: 2026,
    inspect: true,
    now: () => new Date(NOW),
    fetchImpl: async (url) => {
      calls++;
      return response(
        String(url).includes("rosters")
          ? rosterCsv
          : String(url).includes("injuries")
            ? injuryCsv
            : String(url).includes("depth_charts")
              ? gzipSync(depthCsv)
              : scheduleCsv,
        { "last-modified": "Sat, 12 Sep 2026 11:35:55 GMT" },
      );
    },
  });
  assert.equal(calls, 4);
  assert.equal(summary.entries, 5);
  assert.equal(summary.reported_at, null);
  assert.equal(summary.source_updated_at.injuries, UPDATED);
  assert.equal(summary.publication_permitted, PUBLICATION_POLICY.verified);
});

test("postseason report phase joins its postseason game only", () => {
  const games = normalizeSchedule(schedule, 2026).games;
  const report = normalizeInjuries(
    [{ ...injuries[0], season_type: "POST", game_type: "POST", week: "19" }],
    2026,
    games,
    metadata,
  )[0];
  assert.equal(report.week_key, "2026-WC-19");
  assert.equal(report.game_id, "fiction-2026-wc");
});

test("source downloader passes one deadline through fetch and rejects timed-out work", async () => {
  await assert.rejects(
    fetchSource(definition, {
      timeoutMs: 10,
      fetchImpl: async (_url, options) => {
        assert.equal(options.redirect, "manual");
        assert.ok(options.signal instanceof AbortSignal);
        await new Promise((resolve, reject) => {
          const timer = setTimeout(resolve, 100);
          options.signal.addEventListener(
            "abort",
            () => {
              clearTimeout(timer);
              reject(options.signal.reason);
            },
            { once: true },
          );
        });
        return response("a\n1");
      },
    }),
    /timeout|aborted/i,
  );
});

test("missing report IDs preserve named players with stable validator-safe synthetic IDs", () => {
  const games = normalizeSchedule(schedule, 2026).games;
  const sourceRow = {
    ...injuries[0],
    gsis_id: "",
    full_name: "Jordan O'Fixture, Jr.",
  };
  const first = normalizeInjuries([sourceRow], 2026, games, metadata)[0]
    .entries[0];
  const next = normalizeInjuries([sourceRow], 2026, games, metadata)[0]
    .entries[0];
  assert.equal(first.id, next.id);
  assert.match(first.id, /^report:[a-f0-9]{24}$/);
  assert.equal(first.name, sourceRow.full_name);
  const feed = normalizeSources({
    rosterCsv,
    scheduleCsv,
    injuryCsv,
    season: 2026,
    sources: sourceDefinitions(2026).map(({ key, ...source }) => ({
      ...source,
      permission: "example",
    })),
    generatedAt: NOW,
    metadata: {
      roster: { ...metadata, source_id: "nflverse-roster" },
      schedule: { ...metadata, source_id: "nflverse-schedule" },
      injuries: metadata,
    },
  });
  feed.reports[0].entries.push({ ...first, id: `fixture:${first.id}` });
  assert.doesNotThrow(() => validateFeed(feed, Date.parse(NOW)));
});

test("depth charts keep the latest team snapshot, join stable IDs and reject conflicting or future rows", () => {
  const meta = { ...metadata, source_id: "nflverse-depth" };
  const result = normalizeDepthCsv(depthCsv, meta);
  assert.equal(result.entries.length, 2);
  assert.equal(
    result.entries.find((row) => row.player_id === "gsis:fiction-qb").rank,
    1,
  );
  assert.equal(result.reported_at, null);
  assert.throws(
    () =>
      normalizeDepthCsv(depthCsv.replaceAll("2026-09-12", "2026-09-15"), meta),
    /observation/,
  );
  const conflict =
    depthCsv +
    "2026-09-12T11:30:00Z,BUF,Fiction Quarterback,9001,fiction-qb,1,Offense,1,Quarterback,QB,1,2\n";
  assert.throws(() => normalizeDepthCsv(conflict, meta), /Conflicting/);
});

test("compressed depth download is bounded and rejects malformed gzip", async () => {
  const definition = sourceDefinitions(2026).find(
    (source) => source.key === "depth",
  );
  const result = await fetchSource(definition, {
    now: () => new Date(NOW),
    fetchImpl: async () => response(gzipSync(depthCsv)),
  });
  assert.equal(result.csv, depthCsv);
  await assert.rejects(
    fetchSource(definition, { fetchImpl: async () => response("not gzip") }),
  );
});
