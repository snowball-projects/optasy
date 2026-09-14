import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  opponentRoster,
  comparePlayer,
  DEFENSIVE_POSITIONS,
} from "../web/model.mjs";
import { validateFeed } from "../web/feed.mjs";
const now = Date.parse("2026-09-13T12:00:00Z");
function setup() {
  const feed = JSON.parse(
    readFileSync(new URL("../web/example.json", import.meta.url)),
  );
  const week = feed.weeks.find(
    (w) => Date.parse(w.starts_at) <= now && now < Date.parse(w.ends_at),
  ).key;
  const selected = feed.players[0];
  const comparison = comparePlayer(feed, selected, week, now);
  const team = comparison.opponent;
  const member = {
    id: "test-starter",
    name: "Test Starter",
    team,
    position: "CB",
    roster_status: "active",
  };
  feed.players.push(member);
  feed.depth = {
    ...feed.roster,
    source_updated_at: "2026-09-13T10:00:00Z",
    retrieved_at: "2026-09-13T11:00:00Z",
    entries: [
      {
        player_id: member.id,
        team,
        rank: 1,
        position: "CB",
        observed_at: "2026-09-13T09:00:00Z",
      },
    ],
  };
  return { feed, week, selected, comparison, member };
}
test("defensive roster includes unlisted members, reserves and unmatched defensive injuries without name joins", () => {
  const { feed, week, comparison, member } = setup();
  const before = structuredClone(feed);
  const members = opponentRoster(feed, comparison, week, now);
  const ids = new Set([
    ...feed.players
      .filter(
        (p) =>
          p.team === comparison.opponent && DEFENSIVE_POSITIONS.has(p.position),
      )
      .map((p) => p.id),
    ...comparison.entries
      .filter((e) => DEFENSIVE_POSITIONS.has(e.position))
      .map((e) => e.id),
  ]);
  assert.deepEqual(new Set(members.map((p) => p.id)), ids);
  assert.equal(members.find((p) => p.id === member.id).injury, null);
  assert.deepEqual(feed, before);
  feed.players.push({
    ...member,
    id: "same-name-other-id",
    name: comparison.entries[0].name,
  });
  assert.equal(
    opponentRoster(feed, comparison, week, now).find(
      (p) => p.id === "same-name-other-id",
    ).injury,
    null,
  );
});
test("first-string status requires current, fresh, exact-team depth evidence and is not inferred from active roster", () => {
  const { feed, week, comparison, member } = setup();
  const read = () =>
    opponentRoster(feed, comparison, week, now).find((p) => p.id === member.id);
  assert.equal(read().status.key, "starter");
  feed.depth.entries[0].team = member.team === "BUF" ? "KC" : "BUF";
  assert.equal(read().starter, false);
  feed.depth.entries[0].team = member.team;
  feed.depth.entries[0].observed_at = "2026-09-10T09:00:00Z";
  assert.equal(read().starter, false);
  feed.depth.entries[0].observed_at = "2026-09-13T09:00:00Z";
  assert.equal(
    opponentRoster(feed, comparison, "different-week", now).find(
      (p) => p.id === member.id,
    ).starter,
    false,
  );
  delete feed.depth;
  assert.equal(read().starter, false);
  assert.equal(read().status.key, "active");
});
test("injury status takes priority over first string; current reserve and practice status remain distinct", () => {
  const { feed, week, comparison, member } = setup();
  const injury = {
    ...comparison.entries[0],
    id: member.id,
    name: member.name,
    game_status: "Questionable",
  };
  comparison.entries.push(injury);
  const read = () =>
    opponentRoster(feed, comparison, week, now).find((p) => p.id === member.id);
  assert.equal(read().status.key, "questionable");
  assert.equal(read().starter, true);
  injury.game_status = "Out";
  assert.equal(read().status.key, "out");
  injury.game_status = "Doubtful";
  assert.equal(read().status.key, "doubtful");
  injury.game_status = "Not listed";
  injury.practice_status = "Limited";
  assert.equal(read().status.key, "limited");
  injury.practice_status = "Did not practice";
  assert.equal(read().status.key, "dnp");
  member.roster_status = "injured-reserve";
  assert.equal(read().status.short, "IR");
  assert.equal(read().starter, false);
  member.roster_status = "practice-squad";
  assert.equal(read().status.key, "squad");
});
test("missing or stale injury reports never turn unlisted players green or healthy", () => {
  const { feed, week, comparison, member } = setup();
  delete comparison.report;
  assert.equal(
    opponentRoster(feed, comparison, week, now).find((p) => p.id === member.id)
      .status.key,
    "unknown",
  );
  comparison.report = {};
  comparison.sourceFileStale = true;
  assert.equal(
    opponentRoster(feed, comparison, week, now).find((p) => p.id === member.id)
      .status.key,
    "unknown",
  );
  assert.deepEqual(
    opponentRoster(feed, { ...comparison, opponent: null }, week, now),
    [],
  );
});
test("depth schema rejects future observations, invalid ranks and duplicate assignments", () => {
  const { feed } = setup();
  feed.generated_at = "2026-09-13T12:00:00Z";
  assert.doesNotThrow(() => validateFeed(feed, now));
  feed.depth.entries[0].rank = 0;
  assert.throws(() => validateFeed(feed, now), /depth rank/i);
  feed.depth.entries[0].rank = 1;
  feed.depth.entries.push({ ...feed.depth.entries[0] });
  assert.throws(() => validateFeed(feed, now), /Duplicate depth/);
  feed.depth.entries.pop();
  feed.depth.entries[0].observed_at = "2026-09-14T12:00:00Z";
  assert.throws(() => validateFeed(feed, now), /newer than retrieval/);
});

test("an explicitly malformed optional depth field fails validation", () => {
  for (const value of [null, false, 0, ""]) {
    const { feed } = setup();
    feed.depth = value;
    assert.throws(() => validateFeed(feed, now), /must be an object/);
  }
});

test("opponent tiles exclude offense, special teams and unclassified positions even when injured", () => {
  const { feed, week, comparison, member } = setup();
  for (const position of [
    "QB",
    "RB",
    "FB",
    "WR",
    "TE",
    "T",
    "OT",
    "G",
    "OG",
    "C",
    "OL",
    "K",
    "P",
    "LS",
    "ATH",
    "UNK",
  ]) {
    const player = { ...member, id: "excluded-" + position, position };
    feed.players.push(player);
    comparison.entries.push({
      ...comparison.entries[0],
      id: player.id,
      position,
      game_status: "Out",
    });
  }
  const members = opponentRoster(feed, comparison, week, now);
  assert.ok(members.length > 0);
  assert.ok(members.every((p) => DEFENSIVE_POSITIONS.has(p.position)));
  assert.ok(members.every((p) => !p.id.startsWith("excluded-")));
  const defender = comparison.entries.find((entry) =>
    DEFENSIVE_POSITIONS.has(entry.position),
  );
  assert.ok(members.some((p) => p.id === defender.id));
});
test("a defender listed first at kick returner is not mislabeled a defensive starter", () => {
  const { feed, week, comparison, member } = setup();
  feed.depth.entries[0].position = "KR";
  assert.equal(
    opponentRoster(feed, comparison, week, now).find((p) => p.id === member.id)
      .starter,
    false,
  );
  feed.depth.entries.push({
    ...feed.depth.entries[0],
    position: "RCB",
    rank: 2,
  });
  assert.equal(
    opponentRoster(feed, comparison, week, now).find((p) => p.id === member.id)
      .starter,
    false,
  );
  feed.depth.entries[1].rank = 1;
  assert.equal(
    opponentRoster(feed, comparison, week, now).find((p) => p.id === member.id)
      .starter,
    true,
  );
});
