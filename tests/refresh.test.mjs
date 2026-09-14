import test from "node:test";
import assert from "node:assert/strict";
import { createRefreshController, canApplyRefresh } from "../web/refresh.mjs";
import {
  gameStateLabel,
  reportFreshnessLabel,
  clockFingerprint,
} from "../web/model.mjs";

test("refresh serializes requests, distinguishes unchanged data and keeps last good data after failures or rollback", async () => {
  let clock = 1000000,
    resolve,
    calls = 0;
  const states = [],
    applied = [];
  const refresh = createRefreshController({
    now: () => clock,
    request: () => {
      calls++;
      return new Promise((r) => (resolve = r));
    },
    onState: (s) => states.push(s),
    onData: (d) => applied.push(d),
  });
  const data = { mode: "live", generated_at: "2026-09-14T10:00:00Z" };
  const first = refresh.refresh();
  assert.equal(await refresh.refresh(), false);
  assert.equal(calls, 1);
  resolve(data);
  await first;
  assert.equal(states.at(-1).phase, "updated");
  const second = refresh.refresh();
  resolve({ ...data });
  await second;
  assert.equal(states.at(-1).phase, "unchanged");
  assert.equal(applied.length, 1);
  const rollback = refresh.refresh();
  resolve({ ...data, generated_at: "2026-09-13T10:00:00Z" });
  await rollback;
  assert.equal(states.at(-1).phase, "error");
  assert.equal(applied.length, 1);
  clock += 300000;
  assert.equal(refresh.due(), false);
  clock += 300000;
  assert.equal(refresh.due(true), false);
  assert.equal(refresh.due(), true);
  const next = refresh.refresh();
  resolve({ ...data, generated_at: "2026-09-14T11:00:00Z" });
  await next;
  assert.equal(applied.length, 2);
  assert.equal(states.at(-1).failures, 0);
});

test("timeouts and rejected response parsing fail clearly and cap retry backoff", async () => {
  let clock = 1000000;
  const states = [];
  const refresh = createRefreshController({
    now: () => clock,
    request: async () => {
      throw new DOMException("deadline", "TimeoutError");
    },
    onData: () => assert.fail(),
    onState: (s) => states.push(s),
  });
  for (let i = 0; i < 7; i++) await refresh.refresh();
  assert.equal(states.at(-1).error, "The request timed out.");
  clock += 3599999;
  assert.equal(refresh.due(), false);
  clock++;
  assert.equal(refresh.due(), true);
});

test("pending data waits for dialogs, searches and focused roster/week controls", () => {
  const idle = { popoverOpen: false, searchOpen: false, focusedControl: false };
  assert.equal(canApplyRefresh(idle), true);
  for (const key of Object.keys(idle))
    assert.equal(canApplyRefresh({ ...idle, [key]: true }), false);
});

test("clock transitions never turn elapsed kickoff into confirmed live or final", () => {
  const game = { status: "scheduled", kickoff: "2026-09-14T17:00:00Z" };
  const start = Date.parse(game.kickoff);
  assert.equal(gameStateLabel(game, start - 1), "Upcoming");
  assert.match(gameStateLabel(game, start), /Start passed.*unconfirmed/);
  assert.match(gameStateLabel(game, start + 86400000), /unconfirmed/);
  for (const [status, label] of [
    ["in-progress", "In progress"],
    ["final", "Finished"],
    ["postponed", "Postponed"],
    ["canceled", "Canceled"],
  ])
    assert.equal(gameStateLabel({ ...game, status }, start), label);
  assert.match(gameStateLabel({ ...game, kickoff: null }), /Time TBD/);
});

test("visible report freshness distinguishes file age from unknown report publication", () => {
  const report = {
    source_updated_at: "2026-09-14T10:00:00Z",
    reported_at: null,
    reported_date: null,
  };
  assert.equal(
    reportFreshnessLabel(report, Date.parse("2026-09-14T12:30:00Z")),
    "File 2h old · report time unknown",
  );
  assert.equal(reportFreshnessLabel(null), "Injury report unavailable");
  assert.match(
    reportFreshnessLabel({ ...report, source_updated_at: null }),
    /File age unknown/,
  );
  assert.match(
    reportFreshnessLabel({ ...report, reported_date: "2026-09-14" }),
    /report date only/,
  );
});

test("retained identical data changes its display fingerprint at freshness and depth expiry", () => {
  const now = Date.parse("2026-09-14T10:00:00Z");
  const metadata = {
    reported_at: null,
    reported_date: null,
    retrieved_at: "2026-09-14T10:00:00Z",
    source_updated_at: "2026-09-14T10:00:00Z",
  };
  const feed = {
    roster: metadata,
    schedule: metadata,
    reports: [metadata],
    weeks: [],
    games: [],
    depth: { ...metadata, entries: [{ observed_at: "2026-09-13T11:00:00Z" }] },
  };
  const key = clockFingerprint(feed, "week", now);
  assert.equal(clockFingerprint(feed, "week", now + 60000), key);
  assert.notEqual(clockFingerprint(feed, "week", now + 3600001), key);
  assert.notEqual(clockFingerprint(feed, "week", now + 86400001), key);
});
