// One reviewed, historical release download; no provider requests from visitors.
import { readFile, rename, rm, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { gunzipSync } from "node:zlib";
import { parseCsv } from "./source-adapter.mjs";
import {
  CONTRIBUTION_SEASON,
  CONTRIBUTION_SOURCE,
  CONTRIBUTION_TERMS,
  CONTRIBUTION_COUNTS,
  validateContributions,
} from "../web/contribution.mjs";

export const CONTRIBUTION_POLICY = Object.freeze({
  verified: true,
  checked_on: "2026-09-14",
  reason:
    "nflverse-data publishes its calculated player statistics under CC BY 4.0. optasy selects 2025 regular-season defensive records and sums separate event credits by GSIS identity, preserving historical teams. This relies on the publisher's data grant, not a separately verified NFL agreement. No endorsement or defensive-quality claim is implied. See docs/CONTRIBUTION_REVIEW.md.",
});
const MAX_BYTES = 4 * 1024 * 1024;
const MAX_EXPANDED_BYTES = 20 * 1024 * 1024;
const REDIRECT_HOSTS = new Set([
  "github.com",
  "release-assets.githubusercontent.com",
  "objects.githubusercontent.com",
]);
const TEAMS = new Set(
  "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split(
    " ",
  ),
);
const FIELDS = {
  sacks: "def_sacks",
  qb_hits: "def_qb_hits",
  passes_defended: "def_pass_defended",
  interceptions: "def_interceptions",
};
const DEFENSE = new Set(["DL", "LB", "DB"]);
const OUTPUT = new URL("../web/contributions.json", import.meta.url);
function requireValue(ok, message) {
  if (!ok) throw new Error(message);
}
function team(value) {
  const normalized = value === "LA" ? "LAR" : value;
  requireValue(TEAMS.has(normalized), "Unknown contribution team.");
  return normalized;
}
function emptyCounts() {
  return Object.fromEntries(
    ["recorded_games", ...CONTRIBUTION_COUNTS].map((key) => [key, 0]),
  );
}
function eventCount(input, key) {
  requireValue(
    typeof input === "string" && /^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(input),
    `Missing or invalid ${key}.`,
  );
  const value = Number(input);
  requireValue(
    value <= 100 && Number.isInteger(value * (key === "sacks" ? 2 : 1)),
    `Invalid ${key} credit.`,
  );
  return value;
}

export function normalizeContributions(csv, metadata, now = Date.now()) {
  const rows = parseCsv(csv, { maxBytes: MAX_EXPANDED_BYTES, maxRows: 40_000 });
  requireValue(rows.length > 0, "Contribution source has no rows.");
  for (const field of [
    "player_id",
    "position_group",
    "season",
    "season_type",
    "week",
    "game_id",
    "team",
    "opponent_team",
    ...Object.values(FIELDS),
  ])
    requireValue(
      Object.hasOwn(rows[0], field),
      `Contribution source missing ${field}.`,
    );
  const players = new Map(),
    games = new Set(),
    teams = new Set(),
    joins = new Set();
  let recordCount = 0;
  for (const row of rows) {
    requireValue(
      row.season === String(CONTRIBUTION_SEASON) &&
        ["REG", "POST"].includes(row.season_type),
      "Unexpected contribution source season or game type.",
    );
    if (row.season_type !== "REG" || !DEFENSE.has(row.position_group)) continue;
    requireValue(
      /^00-\d{7}$/.test(row.player_id),
      "Missing or invalid defensive GSIS identity.",
    );
    requireValue(
      /^(?:[1-9]|1[0-8])$/.test(row.week),
      "Invalid regular-season stat week.",
    );
    const historicalTeam = team(row.team),
      opponent = team(row.opponent_team);
    const parts = row.game_id.split("_");
    requireValue(
      parts.length === 4 &&
        parts[0] === String(CONTRIBUTION_SEASON) &&
        parts[1] === row.week.padStart(2, "0"),
      "Contribution game does not match season/week.",
    );
    requireValue(
      historicalTeam !== opponent &&
        new Set([team(parts[2]), team(parts[3])]).size === 2 &&
        [team(parts[2]), team(parts[3])].includes(historicalTeam) &&
        [team(parts[2]), team(parts[3])].includes(opponent),
      "Contribution game does not match teams.",
    );
    const join = `${row.player_id}:${row.game_id}`;
    requireValue(
      !joins.has(join),
      "Duplicate or conflicting player-game contribution.",
    );
    joins.add(join);
    const id = `gsis:${row.player_id}`;
    if (!players.has(id))
      players.set(id, { id, teams: new Map(), ...emptyCounts() });
    const player = players.get(id);
    if (!player.teams.has(historicalTeam))
      player.teams.set(historicalTeam, {
        team: historicalTeam,
        ...emptyCounts(),
      });
    const subtotal = player.teams.get(historicalTeam);
    for (const [key, field] of Object.entries(FIELDS)) {
      const value = eventCount(row[field], key);
      player[key] += value;
      subtotal[key] += value;
    }
    player.recorded_games++;
    subtotal.recorded_games++;
    games.add(row.game_id);
    teams.add(historicalTeam);
    recordCount++;
  }
  const artifact = {
    schema_version: 1,
    season: CONTRIBUTION_SEASON,
    season_type: "REG",
    source: {
      url: CONTRIBUTION_SOURCE,
      terms_url: CONTRIBUTION_TERMS,
      permission: CONTRIBUTION_POLICY.verified ? "verified" : "unverified",
      permission_note: CONTRIBUTION_POLICY.reason,
      retrieved_at: metadata.retrieved_at,
      source_updated_at: metadata.source_updated_at,
    },
    coverage: {
      status: "partial",
      teams: [...teams].sort(),
      game_count: games.size,
      record_count: recordCount,
      player_count: players.size,
    },
    players: [...players.values()]
      .map((player) => ({
        ...player,
        teams: [...player.teams.values()].sort((a, b) =>
          a.team.localeCompare(b.team),
        ),
      }))
      .sort((a, b) => a.id.localeCompare(b.id)),
  };
  return validateContributions(artifact, now);
}

function safeRedirect(value) {
  const url = new URL(value);
  requireValue(
    url.protocol === "https:" &&
      !url.username &&
      !url.password &&
      !url.port &&
      REDIRECT_HOSTS.has(url.hostname),
    "Contribution source redirected outside the HTTPS release allowlist.",
  );
  return url;
}

export async function collectContributions({
  fetchImpl = fetch,
  now = () => new Date(),
  timeoutMs = 30_000,
  maxBytes = MAX_BYTES,
} = {}) {
  requireValue(
    CONTRIBUTION_POLICY.verified,
    "Contribution source publication is not approved.",
  );
  const signal = AbortSignal.timeout(timeoutMs);
  let url = safeRedirect(CONTRIBUTION_SOURCE),
    response;
  for (let redirects = 0; redirects <= 3; redirects++) {
    response = await fetchImpl(url, {
      signal,
      redirect: "manual",
      headers: {
        Accept: "application/gzip",
        "User-Agent":
          "optasy-contribution-refresh/1.0 (https://github.com/snowball-projects/optasy)",
      },
    });
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      await response.body?.cancel();
      requireValue(
        redirects < 3,
        "Contribution source exceeded redirect limit.",
      );
      const location = response.headers.get("location");
      requireValue(location, "Contribution source redirect omitted location.");
      url = safeRedirect(new URL(location, url).href);
      continue;
    }
    break;
  }
  if (!response.ok) {
    await response.body?.cancel();
    throw new Error(
      `Contribution source returned HTTP ${response.status}; no immediate retry or publication.`,
    );
  }
  const type = response.headers.get("content-type") || "";
  if (
    Number(response.headers.get("content-length")) > maxBytes ||
    /text\/html|application\/(?:json|xml)/i.test(type)
  ) {
    await response.body?.cancel();
    throw new Error(
      "Contribution source exceeds size limit or has unexpected content type.",
    );
  }
  requireValue(response.body, "Contribution source has no body.");
  const reader = response.body.getReader(),
    chunks = [];
  let bytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maxBytes) {
        await reader.cancel();
        throw new Error("Contribution source exceeds download size limit.");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const retrievedAt = now().toISOString();
  const modified = response.headers.get("last-modified");
  const parsed = modified ? Date.parse(modified) : NaN;
  const csv = new TextDecoder("utf-8", { fatal: true }).decode(
    gunzipSync(Buffer.concat(chunks), { maxOutputLength: MAX_EXPANDED_BYTES }),
  );
  return normalizeContributions(
    csv,
    {
      retrieved_at: retrievedAt,
      source_updated_at: Number.isFinite(parsed)
        ? new Date(parsed).toISOString()
        : null,
    },
    Date.parse(retrievedAt),
  );
}

export async function refreshContributions({
  output = OUTPUT,
  collect = collectContributions,
} = {}) {
  const temporary = new URL("./contributions.json.pending", output);
  try {
    const artifact = validateContributions(await collect());
    await writeFile(temporary, `${JSON.stringify(artifact)}\n`, { flag: "wx" });
    await rename(temporary, output);
    return { status: "updated", artifact };
  } catch (error) {
    await rm(temporary, { force: true });
    try {
      const artifact = validateContributions(
        JSON.parse(await readFile(output, "utf8")),
      );
      return { status: "retained", artifact, error: error.message };
    } catch {
      // Never retain an unchecked artifact after a failed optional collection.
      await rm(output, { force: true });
      return { status: "unavailable", error: error.message };
    }
  }
}

async function main() {
  const args = process.argv.slice(2);
  requireValue(
    args.length <= 1 && args.every((arg) => arg === "--optional"),
    "Usage: node scripts/contribution-data.mjs [--optional]",
  );
  const result = await refreshContributions();
  if (result.error) {
    console.warn(`Historical refresh ${result.status}: ${result.error}`);
    if (!args.includes("--optional")) process.exitCode = 1;
  }
  console.log(
    JSON.stringify(
      {
        status: result.status,
        season: result.artifact?.season,
        source: result.artifact?.source,
        coverage: result.artifact?.coverage,
      },
      null,
      2,
    ),
  );
}
if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url)
  main().catch((error) => {
    console.error(`Contribution refresh failed: ${error.message}`);
    process.exitCode = 1;
  });
