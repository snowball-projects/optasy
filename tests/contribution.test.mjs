import test from "node:test";
import assert from "node:assert/strict";
import { gzipSync } from "node:zlib";
import { metricPerspective } from "../web/model.mjs";
import {
  normalizeContributions,
  collectContributions,
} from "../scripts/contribution-data.mjs";
import {
  CONTRIBUTION_SOURCE,
  validateContributions,
  defenderContribution,
  contributionMetrics,
} from "../web/contribution.mjs";

const NOW = Date.parse("2026-09-14T12:00:00Z");
const metadata = {
  retrieved_at: new Date(NOW).toISOString(),
  source_updated_at: "2026-08-13T16:51:22Z",
};
const header =
  "player_id,position_group,season,season_type,week,game_id,team,opponent_team,def_sacks,def_qb_hits,def_pass_defended,def_interceptions";
const first = "00-0012345,DL,2025,REG,1,2025_01_ARI_NO,ARI,NO,0.5,2,0,0";
const second = "00-0012345,DL,2025,REG,2,2025_02_NO_LA,LA,NO,1,0,1,0";
const zero = "00-0012346,DB,2025,REG,1,2025_01_ARI_NO,NO,ARI,0,0,0,0";
const csv = (...rows) => [header, ...rows].join("\n");
const normalize = (...rows) =>
  normalizeContributions(csv(...rows), metadata, NOW);
const fixture = () => normalize(first, second, zero);
const reply = (body, options = {}) =>
  new Response(body, {
    headers: {
      "content-type": "application/octet-stream",
      "last-modified": metadata.source_updated_at,
    },
    ...options,
  });

test("coarse linebacker roles retain recorded disruption in receiver and tight-end views", () => {
  const data = normalize(
    first.replace(",DL,", ",LB,").replace(",0.5,2,0,0", ",8.5,19,0,0"),
  );
  for (const selected of ["QB", "WR", "TE"])
    for (const position of ["LB", "ILB", "MLB", "OLB"]) {
      const history = defenderContribution(
        data,
        "gsis:00-0012345",
        metricPerspective(selected, position),
      );
      assert.deepEqual(
        history.metrics.map(({ key, value }) => [key, value]),
        [
          ["sacks", 8.5],
          ["passes_defended", 0],
        ],
      );
      assert.match(history.relevance, /does not establish.*assignment/);
      assert.equal(
        history.allMetrics.find((metric) => metric.key === "qb_hits").value,
        19,
      );
    }
  assert.equal(metricPerspective("WR", "EDGE"), "QB");
  assert.equal(metricPerspective("WR", "CB"), "WR");
  assert.deepEqual(contributionMetrics(metricPerspective("RB", "LB")), []);
});

test("historical contribution sums half credits by stable identity and preserves transferred-team subtotals", () => {
  const data = fixture();
  assert.equal(data.season, 2025);
  assert.equal(data.season_type, "REG");
  assert.deepEqual(data.coverage, {
    status: "partial",
    teams: ["ARI", "LAR", "NO"],
    game_count: 2,
    record_count: 3,
    player_count: 2,
  });
  const player = data.players[0];
  assert.equal(player.id, "gsis:00-0012345");
  assert.equal(player.sacks, 1.5);
  assert.equal(player.recorded_games, 2);
  assert.deepEqual(
    player.teams.map((team) => [team.team, team.sacks, team.recorded_games]),
    [
      ["ARI", 0.5, 1],
      ["LAR", 1, 1],
    ],
  );
});

test("only reviewed regular-season defensive stats enter the baseline, without current-season leakage", () => {
  const offense = first.replace(",DL,", ",QB,");
  const postseason = first.replace(",REG,1,2025_01_", ",POST,19,2025_19_");
  const data = normalize(first, offense, postseason);
  assert.equal(data.coverage.record_count, 1);
  assert.throws(() => normalize(first.replaceAll("2025", "2026")), /season/);
  assert.throws(() => normalize(offense), /covered teams/);
});

test("source identity, game joins and numeric boundaries fail rather than invent totals", () => {
  assert.throws(() => normalize(first, first), /Duplicate/);
  assert.throws(
    () => normalize(first, first.replace(",ARI,NO,", ",NO,ARI,")),
    /Duplicate/,
  );
  assert.throws(
    () => normalize(first.replace("00-0012345", "Same Name")),
    /GSIS/,
  );
  assert.throws(
    () => normalize(first.replace("2025_01_ARI_NO", "2025_02_ARI_NO")),
    /season\/week/,
  );
  assert.throws(
    () => normalize(first.replace(",ARI,NO,", ",ARI,NYJ,")),
    /teams/,
  );
  for (const bad of ["", "NaN", "-1", "Infinity", "0.25", "101", "1e2"])
    assert.throws(() => normalize(first.replace(",0.5,", `,${bad},`)), /sacks/);
  assert.throws(
    () => normalize(first.replace(",2,0,0", ",0.5,0,0")),
    /qb_hits/,
  );
});

test("missing identities differ from recorded zero and helper does not infer benefit or use names", () => {
  const data = fixture(),
    before = structuredClone(data);
  assert.equal(defenderContribution(data, "gsis:00-0000000", "QB"), null);
  assert.equal(defenderContribution(null, "gsis:00-0012346", "QB"), null);
  const zeroRecord = defenderContribution(data, "gsis:00-0012346", "QB");
  assert.deepEqual(
    zeroRecord.metrics.map((metric) => metric.value),
    [0, 0],
  );
  assert.equal(defenderContribution(data, "00-0012346", "QB"), null);
  assert.deepEqual(
    contributionMetrics("QB").map((metric) => metric.key),
    ["sacks", "qb_hits"],
  );
  assert.deepEqual(
    contributionMetrics("WR").map((metric) => metric.key),
    ["passes_defended", "interceptions"],
  );
  assert.deepEqual(contributionMetrics("RB"), []);
  const rb = defenderContribution(data, "gsis:00-0012345", "RB");
  assert.equal(rb.allMetrics.length, 4);
  assert.match(rb.relevance, /do not isolate rushing defense/);
  assert.match(zeroRecord.absence, /If unavailable/);
  assert.match(zeroRecord.limitation, /unmeasured/);
  assert.deepEqual(data, before);
});

test("artifact validation rejects unsupported rights, false completeness and untraceable totals", () => {
  const mutations = [
    (data) => (data.source.url = "https://example.com/data.csv"),
    (data) => (data.source.permission = "unknown"),
    (data) => (data.source.terms_url = "https://example.com/MIT"),
    (data) => (data.season = 2026),
    (data) => (data.coverage.status = "complete"),
    (data) => data.coverage.record_count++,
    (data) => data.coverage.teams.push("KC"),
    (data) => data.players[0].sacks++,
    (data) => data.players[0].teams.push(data.players[0].teams[0]),
    (data) => (data.players[0].id = "gsis-it:123"),
    (data) => (data.advantage = 0.2),
    (data) => (data.players[0].games_played = 2),
    (data) => (data.source.retrieved_at = "2026-02-30T12:00:00Z"),
    (data) => (data.source.source_updated_at = "2026-09-15T12:00:00Z"),
  ];
  for (const mutate of mutations) {
    const data = fixture();
    mutate(data);
    assert.throws(
      () => validateContributions(data, NOW),
      /Invalid contribution data/,
    );
  }
  const unknownVintage = fixture();
  unknownVintage.source.source_updated_at = null;
  assert.equal(
    validateContributions(unknownVintage, NOW).source.source_updated_at,
    null,
  );
});

test("collector requests only the fixed approved historical source and validates gzip before publication", async () => {
  const requested = [];
  const data = await collectContributions({
    now: () => new Date(NOW),
    fetchImpl: async (url, options) => {
      requested.push(String(url));
      assert.equal(options.redirect, "manual");
      assert.ok(options.signal);
      return reply(gzipSync(csv(first, zero)));
    },
  });
  assert.deepEqual(requested, [CONTRIBUTION_SOURCE]);
  assert.equal(data.coverage.record_count, 2);
  assert.equal(data.source.retrieved_at, metadata.retrieved_at);
});

test("collector rejects untrusted redirects, caps redirect chains and performs no HTTP retry", async () => {
  for (const location of [
    "https://example.com/private",
    "http://github.com/file",
    "https://token@github.com/file",
  ])
    await assert.rejects(
      collectContributions({
        fetchImpl: async () =>
          reply(null, { status: 302, headers: { location } }),
      }),
      /allowlist/,
    );
  let calls = 0;
  await assert.rejects(
    collectContributions({
      fetchImpl: async () => {
        calls++;
        return reply(null, {
          status: 302,
          headers: { location: "https://github.com/again" },
        });
      },
    }),
    /redirect limit/,
  );
  assert.equal(calls, 4);
  calls = 0;
  await assert.rejects(
    collectContributions({
      fetchImpl: async () => {
        calls++;
        return reply("wait", { status: 429 });
      },
    }),
    /HTTP 429/,
  );
  assert.equal(calls, 1);
});

test("collector bounds advertised/streamed/compressed output and rejects bad content or future vintage", async () => {
  await assert.rejects(
    collectContributions({
      maxBytes: 10,
      fetchImpl: async () =>
        reply("tiny", { headers: { "content-length": "11" } }),
    }),
    /size limit/,
  );
  await assert.rejects(
    collectContributions({
      maxBytes: 10,
      fetchImpl: async () => reply("more than ten bytes"),
    }),
    /download size/,
  );
  await assert.rejects(
    collectContributions({
      fetchImpl: async () =>
        reply("<html>", { headers: { "content-type": "text/html" } }),
    }),
    /content type/,
  );
  await assert.rejects(
    collectContributions({
      fetchImpl: async () => reply(gzipSync("x".repeat(20 * 1024 * 1024 + 1))),
    }),
    /larger than|size|length/i,
  );
  await assert.rejects(
    collectContributions({
      now: () => new Date(NOW),
      fetchImpl: async () =>
        reply(gzipSync(csv(first)), {
          headers: { "last-modified": "Tue, 15 Sep 2026 12:00:00 GMT" },
        }),
    }),
    /file update time/,
  );
});

test("production leaders use separate positive measures, include ties and exclude missing histories", async () => {
  const { productionLeaders } = await import("../web/contribution.mjs");
  const data = {
    players: [
      { id: "a", sacks: 5, qb_hits: 6, passes_defended: 0, interceptions: 0 },
      { id: "b", sacks: 5, qb_hits: 8, passes_defended: 0, interceptions: 0 },
      {
        id: "outside",
        sacks: 99,
        qb_hits: 99,
        passes_defended: 99,
        interceptions: 9,
      },
    ],
  };
  assert.deepEqual(
    productionLeaders(data, [{ id: "a" }, { id: "b" }, { id: "missing" }]),
    {
      sacks: ["a", "b"],
      qb_hits: ["b"],
      passes_defended: [],
      interceptions: [],
    },
  );
});
