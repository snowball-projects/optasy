import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  validateSnapshot,
  comparePlayer,
  safeUrl,
  newSnapshot,
} from "../web/model.mjs";
const fixture = () =>
  JSON.parse(readFileSync(new URL("../web/sample.json", import.meta.url)));
const now = Date.parse("2026-09-10T13:00:00Z");

test("sample compares only relevant opposing roles and distinguishes absence from uncertainty", () => {
  const d = validateSnapshot(fixture(), now),
    r = comparePlayer(d, d.players[0], 1, now);
  assert.equal(r.opponent, "BAL");
  assert.equal(r.defenders.length, 3);
  assert.deepEqual(
    r.defenders.map((p) => p.absent),
    [true, false, false],
  );
  assert.ok(r.defenders.every((p) => !["DI", "LB"].includes(p.role)));
});
test("no schedule or report never becomes a healthy opponent", () => {
  const d = fixture();
  assert.equal(comparePlayer(d, d.players[0], 2, now).state, "no-game");
  assert.equal(comparePlayer(d, d.players[4], 1, now).state, "missing");
  const empty = comparePlayer(d, d.players[2], 1, now);
  assert.equal(empty.defenders.length, 0);
  assert.match(empty.message, /does not establish/);
});
test("does not borrow injuries from another week or team", () => {
  const d = fixture();
  d.reports[0].week = 2;
  assert.equal(comparePlayer(d, d.players[0], 1, now).state, "missing");
});
test("post-kickoff reports are excluded, old reports and started games are labelled", () => {
  const d = fixture();
  d.reports[0].observed_at = d.games[0].kickoff;
  assert.equal(comparePlayer(d, d.players[0], 1, now).state, "late");
  d.reports[0].observed_at = "2026-09-07T11:00:00Z";
  assert.equal(comparePlayer(d, d.players[0], 1, now).stale, true);
  assert.equal(
    comparePlayer(d, d.players[0], 1, Date.parse("2026-09-14T12:00:00Z"))
      .started,
    true,
  );
});
test("kickers receive no invented injury mechanism", () => {
  const d = fixture();
  const r = comparePlayer(d, d.players[5], 1, now);
  assert.equal(r.defenders.length, 0);
  assert.match(r.message, /not modeled/);
});
test("rejects ambiguous games, duplicate candidates and duplicate team reports", () => {
  for (const mutate of [
    (d) => d.games.push({ ...d.games[0], home: "TEN" }),
    (d) => d.players.push(d.players[0]),
    (d) => d.reports.push(d.reports[0]),
  ]) {
    const d = fixture();
    mutate(d);
    assert.throws(() => validateSnapshot(d, now));
  }
});
test("rejects misleading units, unknown status and duplicate defenders", () => {
  for (const mutate of [
    (d) => (d.reports[0].defenders[0].snap_share = 101),
    (d) => (d.reports[0].defenders[0].status = "Probably fine"),
    (d) => d.reports[0].defenders.push(d.reports[0].defenders[0]),
  ]) {
    const d = fixture();
    mutate(d);
    assert.throws(() => validateSnapshot(d, now));
  }
});
test("requires timezone provenance, source-before-snapshot, and no future user snapshots", () => {
  for (const mutate of [
    (d) => (d.reports[0].observed_at = "2026-09-10T11:00:00"),
    (d) => (d.reports[0].observed_at = "2026-09-10T12:30:00Z"),
    (d) => {
      d.kind = "user";
      d.captured_at = "2026-09-11T00:00:00Z";
    },
  ]) {
    const d = fixture();
    mutate(d);
    assert.throws(() => validateSnapshot(d, now));
  }
});
test("rejects unsafe URLs, embedded credentials and unbounded imports", () => {
  for (const url of [
    "javascript:alert(1)",
    "http://example.org",
    "https://name:secret@example.org",
  ]) {
    assert.equal(safeUrl(url), false);
    const d = fixture();
    d.reports[0].url = url;
    assert.throws(() => validateSnapshot(d, now));
  }
  assert.equal(safeUrl("https://example.org/injuries"), true);
  const d = fixture();
  d.players = Array(1001).fill(d.players[0]);
  assert.throws(() => validateSnapshot(d, now));
});
test("JSON round-trip preserves original inputs; comparison does not mutate them", () => {
  const d = fixture(),
    original = JSON.stringify(d);
  comparePlayer(d, d.players[0], 1, now);
  assert.equal(
    JSON.stringify(validateSnapshot(JSON.parse(JSON.stringify(d)), now)),
    original,
  );
  assert.equal(JSON.stringify(d), original);
  assert.equal(validateSnapshot(newSnapshot(new Date(now)), now).kind, "user");
});
