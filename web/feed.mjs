export const TEAMS = [
  "ARI",
  "ATL",
  "BAL",
  "BUF",
  "CAR",
  "CHI",
  "CIN",
  "CLE",
  "DAL",
  "DEN",
  "DET",
  "GB",
  "HOU",
  "IND",
  "JAX",
  "KC",
  "LAC",
  "LAR",
  "LV",
  "MIA",
  "MIN",
  "NE",
  "NO",
  "NYG",
  "NYJ",
  "PHI",
  "PIT",
  "SEA",
  "SF",
  "TB",
  "TEN",
  "WAS",
];
export const POSITIONS = [
  "QB",
  "RB",
  "FB",
  "WR",
  "TE",
  "C",
  "G",
  "T",
  "OL",
  "OT",
  "OG",
  "LS",
  "K",
  "P",
  "NT",
  "DT",
  "DI",
  "DE",
  "DL",
  "EDGE",
  "OLB",
  "ILB",
  "MLB",
  "LB",
  "CB",
  "DB",
  "FS",
  "SS",
  "S",
  "ATH",
  "UNK",
];
export const ROSTER_STATUSES = [
  "active",
  "inactive",
  "reserve",
  "injured-reserve",
  "pup",
  "nfi",
  "suspended",
  "practice-squad",
  "exempt",
  "unknown",
];
export const MAX_FEED_BYTES = 5_000_000;
const ALIASES = {
  ARZ: "ARI",
  BLT: "BAL",
  CLV: "CLE",
  HST: "HOU",
  JAC: "JAX",
  LA: "LAR",
  WSH: "WAS",
};
const COVERAGES = ["complete", "partial", "unknown"];
const ISO =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/;

function requireValue(ok, message) {
  if (!ok) throw new Error(message);
}
function object(value, label, keys) {
  requireValue(
    value !== null && typeof value === "object" && !Array.isArray(value),
    `${label} must be an object.`,
  );
  requireValue(
    Object.keys(value).every((key) => keys.includes(key)),
    `${label} contains an unsupported field.`,
  );
}
function text(value, label, limit = 180) {
  requireValue(
    typeof value === "string" &&
      value.trim().length > 0 &&
      value.length <= limit &&
      !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(value),
    `${label} must be text (1–${limit} characters).`,
  );
}
function id(value, label) {
  text(value, label, 100);
  requireValue(
    /^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(value),
    `${label} is not a stable identifier.`,
  );
}
function choice(value, choices, label) {
  requireValue(choices.includes(value), `Invalid ${label}.`);
}
function list(value, label, limit) {
  requireValue(
    Array.isArray(value) && value.length <= limit,
    `${label} must be a list of up to ${limit} entries.`,
  );
}
function timestamp(value, label) {
  requireValue(
    typeof value === "string" &&
      ISO.test(value) &&
      Number.isFinite(Date.parse(value)),
    `${label} needs an ISO timestamp with a timezone.`,
  );
  const date = value.slice(0, 10);
  requireValue(
    new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10) === date,
    `${label} has an invalid date.`,
  );
}
function dateOnly(value, label) {
  requireValue(
    typeof value === "string" &&
      /^\d{4}-\d{2}-\d{2}$/.test(value) &&
      Number.isFinite(Date.parse(`${value}T00:00:00Z`)) &&
      new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value,
    `${label} needs a calendar date.`,
  );
}
function team(value, label) {
  const result = ALIASES[value] ?? value;
  choice(result, TEAMS, label);
  return result;
}
function unique(set, key, label) {
  requireValue(!set.has(key), `Duplicate ${label}.`);
  set.add(key);
}

export function safeUrl(value) {
  if (typeof value !== "string" || value.length > 2000 || /\s/u.test(value))
    return false;
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      Boolean(url.hostname) &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
}

function metadata(value, label, sourceIds, generatedAt) {
  requireValue(
    sourceIds.has(value.source_id),
    `${label} references an unknown source.`,
  );
  choice(value.coverage, COVERAGES, `${label} coverage`);
  timestamp(value.retrieved_at, `${label} retrieval time`);
  requireValue(
    Date.parse(value.retrieved_at) <= generatedAt,
    `${label} retrieval is newer than the feed.`,
  );
  requireValue(
    value.reported_at === null || typeof value.reported_at === "string",
    `${label} report vintage must be a timestamp or null.`,
  );
  if (value.reported_at !== null) {
    timestamp(value.reported_at, `${label} report vintage`);
    requireValue(
      Date.parse(value.reported_at) <= Date.parse(value.retrieved_at),
      `${label} report vintage is newer than retrieval.`,
    );
  }
  if (value.reported_date != null) {
    dateOnly(value.reported_date, `${label} report date`);
    requireValue(
      Date.parse(`${value.reported_date}T00:00:00Z`) <=
        Date.parse(value.retrieved_at) + 86400000,
      `${label} report date is newer than retrieval.`,
    );
  }
  if (value.source_updated_at != null) {
    timestamp(value.source_updated_at, `${label} source update time`);
    requireValue(
      Date.parse(value.source_updated_at) <= Date.parse(value.retrieved_at),
      `${label} source update is newer than retrieval.`,
    );
  }
}
const META_KEYS = [
  "source_id",
  "reported_at",
  "reported_date",
  "source_updated_at",
  "retrieved_at",
  "coverage",
];

export function validateFeed(input, now = Date.now()) {
  object(input, "Feed", [
    "schema_version",
    "mode",
    "label",
    "generated_at",
    "sources",
    "roster",
    "schedule",
    "weeks",
    "players",
    "games",
    "reports",
    "depth",
  ]);
  requireValue(input.schema_version === 2, "Unsupported feed version.");
  choice(input.mode, ["example", "live"], "feed mode");
  text(input.label, "Feed label", 100);
  timestamp(input.generated_at, "Feed generation time");
  const generatedAt = Date.parse(input.generated_at);
  if (input.mode === "live")
    requireValue(
      generatedAt <= now + 300000,
      "Live feed cannot be generated in the future.",
    );
  // Normalize a copy; original provider evidence remains untouched.
  const data = structuredClone(input);
  list(data.sources, "Sources", 20);
  requireValue(data.sources.length > 0, "Feed needs source provenance.");
  const sourceIds = new Set();
  for (const source of data.sources) {
    object(source, "Source", [
      "id",
      "label",
      "url",
      "terms_url",
      "permission",
      "permission_note",
    ]);
    id(source.id, "Source ID");
    unique(sourceIds, source.id, "source ID");
    text(source.label, "Source label");
    text(source.permission_note, "Source permission note", 1000);
    requireValue(
      safeUrl(source.url) && safeUrl(source.terms_url),
      "Source and terms links must use HTTPS without credentials.",
    );
    choice(source.permission, ["example", "verified"], "source permission");
    requireValue(
      data.mode === "example"
        ? source.permission === "example"
        : source.permission === "verified",
      "Feed mode must match its source permission.",
    );
  }
  for (const field of ["roster", "schedule"]) {
    object(data[field], field, META_KEYS);
    metadata(data[field], field, sourceIds, generatedAt);
  }
  if (Object.hasOwn(data, "depth")) {
    object(data.depth, "Depth chart", [...META_KEYS, "entries"]);
    metadata(data.depth, "Depth chart", sourceIds, generatedAt);
    list(data.depth.entries, "Depth entries", 12000);
    const identities = new Set();
    for (const entry of data.depth.entries) {
      object(entry, "Depth entry", [
        "player_id",
        "team",
        "rank",
        "position",
        "observed_at",
      ]);
      id(entry.player_id, "Depth player ID");
      entry.team = team(entry.team, "depth team");
      text(entry.position, "Depth position", 20);
      requireValue(
        Number.isInteger(entry.rank) && entry.rank > 0 && entry.rank <= 20,
        "Invalid depth rank.",
      );
      timestamp(entry.observed_at, "Depth observation");
      requireValue(
        Date.parse(entry.observed_at) <= Date.parse(data.depth.retrieved_at),
        "Depth observation is newer than retrieval.",
      );
      unique(
        identities,
        `${entry.team}:${entry.player_id}:${entry.position}`,
        "depth entry",
      );
    }
  }
  list(data.weeks, "Weeks", 40);
  list(data.players, "Players", 6000);
  list(data.games, "Games", 800);
  list(data.reports, "Reports", 1600);
  const weeks = new Map(),
    windows = [],
    playerIds = new Set(),
    gameIds = new Set(),
    teamWeeks = new Set(),
    reports = new Set();
  for (const week of data.weeks) {
    object(week, "Week", [
      "key",
      "label",
      "season",
      "week",
      "starts_at",
      "ends_at",
      "byes",
    ]);
    id(week.key, "Week key");
    text(week.label, "Week label", 80);
    requireValue(!weeks.has(week.key), "Duplicate week key.");
    requireValue(
      Number.isInteger(week.season) &&
        week.season >= 2020 &&
        week.season <= 2100,
      "Invalid season.",
    );
    requireValue(
      Number.isInteger(week.week) && week.week >= 1 && week.week <= 22,
      "Invalid NFL week.",
    );
    timestamp(week.starts_at, "Week start");
    timestamp(week.ends_at, "Week end");
    const start = Date.parse(week.starts_at),
      end = Date.parse(week.ends_at);
    requireValue(
      start < end && end - start <= 15 * 86400000,
      "Week window must be positive and no longer than 15 days.",
    );
    requireValue(
      !windows.some(([a, b]) => start < b && a < end),
      "Week windows cannot overlap.",
    );
    windows.push([start, end]);
    list(week.byes, "Confirmed byes", 32);
    week.byes = week.byes.map((value) => team(value, "bye team"));
    requireValue(
      new Set(week.byes).size === week.byes.length,
      "Duplicate bye team.",
    );
    weeks.set(week.key, week);
  }
  for (const player of data.players) {
    object(player, "Player", [
      "id",
      "name",
      "team",
      "position",
      "roster_status",
    ]);
    id(player.id, "Player ID");
    unique(playerIds, player.id, "player ID");
    text(player.name, "Player name", 100);
    player.team = team(player.team, "player team");
    choice(player.position, POSITIONS, "player position");
    choice(player.roster_status, ROSTER_STATUSES, "roster status");
  }
  for (const game of data.games) {
    object(game, "Game", [
      "id",
      "week_key",
      "home",
      "away",
      "kickoff",
      "status",
    ]);
    id(game.id, "Game ID");
    unique(gameIds, game.id, "game ID");
    requireValue(weeks.has(game.week_key), "Game references an unknown week.");
    game.home = team(game.home, "home team");
    game.away = team(game.away, "away team");
    requireValue(game.home !== game.away, "A team cannot play itself.");
    choice(
      game.status,
      ["scheduled", "postponed", "canceled", "in-progress", "final", "tbd"],
      "game status",
    );
    requireValue(
      game.kickoff === null || typeof game.kickoff === "string",
      "Kickoff must be a timestamp or null.",
    );
    if (game.kickoff !== null) timestamp(game.kickoff, "Kickoff");
    if (["scheduled", "in-progress", "final"].includes(game.status))
      requireValue(
        game.kickoff !== null,
        "Scheduled or started games need a kickoff time.",
      );
    for (const gameTeam of [game.home, game.away]) {
      unique(
        teamWeeks,
        `${game.week_key}:${gameTeam}`,
        "team game in the same week",
      );
      requireValue(
        !weeks.get(game.week_key).byes.includes(gameTeam),
        "A team cannot have a game and a confirmed bye.",
      );
    }
  }
  for (const report of data.reports) {
    object(report, "Report", [
      ...META_KEYS,
      "game_id",
      "week_key",
      "team",
      "entries",
    ]);
    metadata(report, "Report", sourceIds, generatedAt);
    report.team = team(report.team, "report team");
    const game = data.games.find(
      (candidate) => candidate.id === report.game_id,
    );
    requireValue(
      game &&
        game.week_key === report.week_key &&
        [game.home, game.away].includes(report.team),
      "Report must match its game, week and team.",
    );
    unique(
      reports,
      `${report.game_id}:${report.team}`,
      "team injury report for the same game",
    );
    list(report.entries, "Injury entries", 250);
    const entryIds = new Set();
    for (const entry of report.entries) {
      object(entry, "Injury entry", [
        "id",
        "name",
        "position",
        "injury",
        "game_status",
        "practice_status",
        "roster_status",
        "status_source",
        "note",
      ]);
      id(entry.id, "Injury player ID");
      unique(entryIds, entry.id, "injury player ID");
      text(entry.name, "Injury player name", 100);
      choice(entry.position, POSITIONS, "injury player position");
      text(entry.injury, "Reported injury", 300);
      choice(
        entry.game_status,
        ["Out", "Doubtful", "Questionable", "Not listed", "Unknown"],
        "official game status",
      );
      choice(
        entry.practice_status,
        ["Did not practice", "Limited", "Full", "Not listed", "Unknown"],
        "official practice status",
      );
      choice(entry.roster_status, ROSTER_STATUSES, "injury roster status");
      choice(
        entry.status_source,
        ["official", "news", "unknown"],
        "status source",
      );
      if (entry.note !== undefined) text(entry.note, "Injury note", 1000);
      if (entry.status_source !== "official")
        requireValue(
          entry.game_status === "Unknown" &&
            entry.practice_status === "Unknown",
          "News and uncertain reports cannot supply official statuses.",
        );
    }
  }
  return data;
}

export function parseFeed(jsonText, now = Date.now()) {
  requireValue(
    typeof jsonText === "string" &&
      new TextEncoder().encode(jsonText).byteLength <= MAX_FEED_BYTES,
    "Feed exceeds the 5 MB limit.",
  );
  let data;
  try {
    data = JSON.parse(jsonText);
  } catch {
    throw new Error("Feed is not valid JSON.");
  }
  return validateFeed(data, now);
}
