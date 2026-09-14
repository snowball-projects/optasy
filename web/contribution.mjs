// Historical event counts are not defensive quality, playing-time or advantage scores.
export const CONTRIBUTION_SEASON = 2025;
export const CONTRIBUTION_SOURCE =
  "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv.gz";
export const CONTRIBUTION_TERMS =
  "https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md";
export const MAX_CONTRIBUTION_BYTES = 1_500_000;
export const CONTRIBUTION_COUNTS = [
  "sacks",
  "qb_hits",
  "passes_defended",
  "interceptions",
];
const TEAMS = new Set(
  "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split(
    " ",
  ),
);
const PERIOD = "2025 regular season";
const LIMITATION =
  "Recorded events, not defensive quality or playing time. Historical teams and roles may differ. Replacement quality and the effect on your player are unmeasured.";
const METRICS = {
  sacks: { key: "sacks", label: "Sacks", short: "sacks" },
  qb_hits: { key: "qb_hits", label: "Quarterback hits", short: "QB hits" },
  passes_defended: {
    key: "passes_defended",
    label: "Passes defended",
    short: "PD",
  },
  interceptions: { key: "interceptions", label: "Interceptions", short: "INT" },
};
function requireValue(ok, message) {
  if (!ok) throw new Error(`Invalid contribution data: ${message}`);
}
function object(value, keys, label) {
  requireValue(
    value && typeof value === "object" && !Array.isArray(value),
    label,
  );
  requireValue(
    Object.keys(value).length === keys.length &&
      keys.every((key) => Object.hasOwn(value, key)),
    `${label} fields`,
  );
}
function integer(value, min, max, label) {
  requireValue(Number.isInteger(value) && value >= min && value <= max, label);
}
function timestamp(value, label, now) {
  requireValue(
    typeof value === "string" &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value) &&
      Number.isFinite(Date.parse(value)) &&
      Date.parse(value) <= now + 300_000,
    label,
  );
  // Date.parse normalizes impossible month days, so require canonical UTC input.
  requireValue(
    new Date(value).toISOString().replace(".000Z", "Z") ===
      value.replace(".000Z", "Z"),
    label,
  );
}
function counts(record, label) {
  integer(record.recorded_games, 1, 18, `${label} recorded game rows`);
  for (const key of CONTRIBUTION_COUNTS) {
    const value = record[key];
    requireValue(
      typeof value === "number" &&
        Number.isFinite(value) &&
        value >= 0 &&
        value <= record.recorded_games * 100 &&
        Number.isInteger(value * (key === "sacks" ? 2 : 1)),
      `${label} ${key}`,
    );
  }
}

/** Strict optional artifact boundary. Callers retain their core feed on failure. */
export function validateContributions(data, now = Date.now()) {
  requireValue(Number.isFinite(now), "clock");
  object(
    data,
    [
      "schema_version",
      "season",
      "season_type",
      "source",
      "coverage",
      "players",
    ],
    "artifact",
  );
  requireValue(
    data.schema_version === 1 &&
      data.season === CONTRIBUTION_SEASON &&
      data.season_type === "REG",
    "reviewed period",
  );
  object(
    data.source,
    [
      "url",
      "terms_url",
      "permission",
      "permission_note",
      "retrieved_at",
      "source_updated_at",
    ],
    "source",
  );
  const source = data.source;
  requireValue(
    source.url === CONTRIBUTION_SOURCE &&
      source.terms_url === CONTRIBUTION_TERMS &&
      source.permission === "verified",
    "reviewed source",
  );
  requireValue(
    typeof source.permission_note === "string" &&
      source.permission_note.length >= 20 &&
      source.permission_note.length <= 1500,
    "permission note",
  );
  timestamp(source.retrieved_at, "retrieval time", now);
  if (source.source_updated_at !== null)
    timestamp(
      source.source_updated_at,
      "file update time",
      Math.min(now, Date.parse(source.retrieved_at)),
    );
  object(
    data.coverage,
    ["status", "teams", "game_count", "record_count", "player_count"],
    "coverage",
  );
  const coverage = data.coverage;
  requireValue(
    coverage.status === "partial",
    "independent completeness is not established",
  );
  requireValue(
    Array.isArray(coverage.teams) &&
      coverage.teams.length > 0 &&
      coverage.teams.length <= 32 &&
      new Set(coverage.teams).size === coverage.teams.length &&
      coverage.teams.every((team) => TEAMS.has(team)),
    "covered teams",
  );
  integer(coverage.game_count, 1, 300, "covered games");
  integer(coverage.record_count, 1, 40_000, "covered defensive stat rows");
  integer(coverage.player_count, 1, 3000, "covered players");
  requireValue(
    Array.isArray(data.players) &&
      data.players.length === coverage.player_count,
    "player coverage",
  );
  const ids = new Set(),
    teams = new Set();
  let records = 0;
  for (const player of data.players) {
    object(
      player,
      ["id", "teams", "recorded_games", ...CONTRIBUTION_COUNTS],
      "player",
    );
    requireValue(
      typeof player.id === "string" &&
        /^gsis:00-\d{7}$/.test(player.id) &&
        !ids.has(player.id),
      "unique GSIS identity",
    );
    ids.add(player.id);
    counts(player, "player");
    requireValue(
      player.recorded_games <= coverage.game_count,
      "player game coverage",
    );
    requireValue(
      Array.isArray(player.teams) &&
        player.teams.length > 0 &&
        player.teams.length <= 4,
      "historical teams",
    );
    const playerTeams = new Set();
    for (const team of player.teams) {
      object(
        team,
        ["team", "recorded_games", ...CONTRIBUTION_COUNTS],
        "team subtotal",
      );
      requireValue(
        TEAMS.has(team.team) && !playerTeams.has(team.team),
        "unique historical team",
      );
      playerTeams.add(team.team);
      teams.add(team.team);
      counts(team, "team subtotal");
    }
    for (const key of ["recorded_games", ...CONTRIBUTION_COUNTS])
      requireValue(
        player[key] === player.teams.reduce((sum, team) => sum + team[key], 0),
        `team subtotal ${key}`,
      );
    records += player.recorded_games;
  }
  requireValue(records === coverage.record_count, "stat-row denominator");
  requireValue(
    teams.size === coverage.teams.length &&
      coverage.teams.every((team) => teams.has(team)),
    "team coverage totals",
  );
  requireValue(
    JSON.stringify(data).length <= MAX_CONTRIBUTION_BYTES,
    "artifact size",
  );
  return data;
}

export function contributionMetrics(selectedPosition) {
  const keys =
    selectedPosition === "QB"
      ? ["sacks", "qb_hits"]
      : ["WR", "TE"].includes(selectedPosition)
        ? ["passes_defended", "interceptions"]
        : selectedPosition === "MIXED"
          ? ["sacks", "passes_defended"]
          : [];
  return keys.map((key) => ({ ...METRICS[key] }));
}

/** Exact identity lookup; historical team context is deliberately preserved. */
export function defenderContribution(data, defenderId, selectedPosition) {
  if (!data) return null;
  const record = data.players.find((player) => player.id === defenderId);
  if (!record) return null;
  return {
    period: PERIOD,
    record,
    metrics: contributionMetrics(selectedPosition).map((metric) => ({
      ...metric,
      value: record[metric.key],
    })),
    allMetrics: CONTRIBUTION_COUNTS.map((key) => ({
      ...METRICS[key],
      value: record[key],
    })),
    relevance:
      selectedPosition === "QB"
        ? "Recorded passing disruption; not a pressure rate or an individual matchup."
        : ["WR", "TE"].includes(selectedPosition)
          ? "Recorded coverage events; they do not identify who will cover your player or measure coverage efficiency."
          : selectedPosition === "MIXED"
            ? "Separate recorded pass-disruption and coverage events. The broad roster position does not establish a current rush or coverage assignment. All four recorded counts are shown above."
            : "These counts do not isolate rushing defense or establish benefit for this position.",
    limitation: LIMITATION,
    absence:
      "If unavailable, this recorded contribution must be replaced; the effect on your player is unmeasured.",
  };
}

// Each event has its own leader set; no weights or overall defender ranking.
export function productionLeaders(data, members) {
  const ids = new Set(members.map((member) => member.id));
  const records = data?.players.filter((player) => ids.has(player.id)) || [];
  return Object.fromEntries(
    CONTRIBUTION_COUNTS.map((key) => {
      const highest = Math.max(0, ...records.map((record) => record[key]));
      return [
        key,
        highest > 0
          ? records
              .filter((record) => record[key] === highest)
              .map((record) => record.id)
          : [],
      ];
    }),
  );
}
