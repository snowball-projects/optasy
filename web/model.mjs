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
export const POSITIONS = ["QB", "RB", "WR", "TE", "K"];
export const ROLES = ["CB", "S", "DB", "EDGE", "DI", "DL", "LB"];
export const STATUSES = [
  "Out",
  "Questionable",
  "Doubtful",
  "IR",
  "PUP",
  "Unknown",
];
export const PRACTICES = ["Unknown", "Did not practice", "Limited", "Full"];
const RELEVANCE = {
  QB: {
    CB: "Coverage",
    S: "Coverage",
    DB: "Coverage",
    EDGE: "Pass rush",
    DI: "Interior pressure",
  },
  WR: {
    CB: "Coverage",
    S: "Deep coverage",
    DB: "Coverage",
    EDGE: "Time for routes to develop",
  },
  RB: {
    DI: "Run defense",
    DL: "Run defense",
    EDGE: "Edge containment",
    LB: "Run defense / receiving coverage",
    S: "Run support / receiving coverage",
  },
  TE: {
    LB: "Receiving coverage",
    S: "Receiving coverage",
    DB: "Receiving coverage",
    CB: "Receiving coverage",
  },
  K: {},
};
function requireValue(ok, message) {
  if (!ok) throw new Error(message);
}
function text(value, label, limit = 180) {
  requireValue(
    typeof value === "string" &&
      value.trim().length > 0 &&
      value.length <= limit,
    `${label} must be text (1–${limit} characters).`,
  );
}
function optionalText(value, label, limit = 500) {
  if (value !== undefined && value !== "") text(value, label, limit);
}
function choice(value, choices, label) {
  requireValue(choices.includes(value), `Invalid ${label}.`);
}
function week(value) {
  requireValue(
    Number.isInteger(value) && value >= 1 && value <= 18,
    "Week must be 1–18.",
  );
}
function timestamp(value, label) {
  requireValue(
    typeof value === "string" &&
      /T.*(?:Z|[+-]\d\d:\d\d)$/.test(value) &&
      Number.isFinite(Date.parse(value)),
    `${label} needs an ISO timestamp with a timezone.`,
  );
}
export function safeUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === "https:" && !u.username && !u.password;
  } catch {
    return false;
  }
}
export function validateSnapshot(data, now = Date.now()) {
  requireValue(
    data && typeof data === "object" && !Array.isArray(data),
    "Import a snapshot object.",
  );
  requireValue(data.schema_version === 1, "Unsupported snapshot version.");
  choice(data.kind, ["sample", "user"], "snapshot kind");
  text(data.label, "Snapshot name", 80);
  requireValue(
    Number.isInteger(data.season) && data.season >= 2020 && data.season <= 2100,
    "Invalid season.",
  );
  timestamp(data.captured_at, "Snapshot time");
  if (data.kind !== "sample")
    requireValue(
      Date.parse(data.captured_at) <= now + 300000,
      "Snapshot time cannot be in the future.",
    );
  for (const field of ["players", "games", "reports"])
    requireValue(
      Array.isArray(data[field]) && data[field].length <= 1000,
      `${field} must be a list of up to 1,000 entries.`,
    );
  const ids = new Set(),
    games = new Set(),
    reports = new Set();
  for (const p of data.players) {
    text(p.id, "Player ID", 80);
    text(p.name, "Player name", 100);
    requireValue(!ids.has(p.id), "Duplicate player ID.");
    ids.add(p.id);
    choice(p.team, TEAMS, "player team");
    choice(p.position, POSITIONS, "player position");
  }
  for (const g of data.games) {
    week(g.week);
    choice(g.home, TEAMS, "home team");
    choice(g.away, TEAMS, "away team");
    requireValue(g.home !== g.away, "A team cannot play itself.");
    timestamp(g.kickoff, "Kickoff");
    for (const team of [g.home, g.away]) {
      const key = `${g.week}:${team}`;
      requireValue(
        !games.has(key),
        "A team has more than one game in the same week.",
      );
      games.add(key);
    }
  }
  for (const r of data.reports) {
    week(r.week);
    choice(r.team, TEAMS, "report team");
    const key = `${r.week}:${r.team}`;
    requireValue(!reports.has(key), "Duplicate team/week report.");
    reports.add(key);
    text(r.source, "Report source");
    timestamp(r.observed_at, "Report time");
    requireValue(
      Date.parse(r.observed_at) <= Date.parse(data.captured_at),
      "A report cannot be newer than its snapshot.",
    );
    optionalText(r.url, "Source URL", 2000);
    requireValue(
      !r.url || safeUrl(r.url),
      "Source links must use HTTPS without credentials.",
    );
    choice(r.coverage, ["partial", "reviewed", "unknown"], "coverage");
    requireValue(
      Array.isArray(r.defenders) && r.defenders.length <= 100,
      "A team report supports up to 100 defenders.",
    );
    const names = new Set();
    for (const d of r.defenders) {
      text(d.name, "Defender name", 100);
      const key = d.name.trim().toLowerCase();
      requireValue(!names.has(key), "Duplicate defender in a team report.");
      names.add(key);
      choice(d.role, ROLES, "defensive role");
      choice(d.status, STATUSES, "injury status");
      choice(d.practice, PRACTICES, "practice status");
      optionalText(d.replacement, "Replacement", 100);
      optionalText(d.note, "Injury note");
      requireValue(
        d.snap_share === null ||
          (Number.isFinite(d.snap_share) &&
            d.snap_share >= 0 &&
            d.snap_share <= 100),
        "Snap share must be a percentage from 0 to 100, or null.",
      );
    }
  }
  return data;
}
export function comparePlayer(snapshot, player, weekNumber, now = Date.now()) {
  const game = snapshot.games.find(
    (g) => g.week === weekNumber && [g.home, g.away].includes(player.team),
  );
  if (!game)
    return {
      state: "no-game",
      defenders: [],
      message: "No game in this snapshot. Check for a bye or missing schedule.",
    };
  const opponent = game.home === player.team ? game.away : game.home;
  const report = snapshot.reports.find(
    (r) => r.week === weekNumber && r.team === opponent,
  );
  const result = {
    game,
    opponent,
    report,
    started: Date.parse(game.kickoff) <= now,
    defenders: [],
  };
  if (!report)
    return {
      ...result,
      state: "missing",
      message: "No opponent report. Injury coverage is unknown.",
    };
  // Never use reports from after kickoff as pre-game lineup evidence.
  if (Date.parse(report.observed_at) >= Date.parse(game.kickoff))
    return {
      ...result,
      state: "late",
      message:
        "Report is from kickoff or later. Excluded from pre-game comparison.",
    };
  const defenders = report.defenders
    .filter((d) => RELEVANCE[player.position][d.role])
    .map((d) => ({
      ...d,
      relevance: RELEVANCE[player.position][d.role],
      absent: ["Out", "IR", "PUP"].includes(d.status),
    }));
  const ageHours = (now - Date.parse(report.observed_at)) / 3600000;
  return {
    ...result,
    state: "report",
    defenders,
    ageHours,
    stale: ageHours > 48,
    message:
      player.position === "K"
        ? "Kicker-specific injury effects are not modeled."
        : defenders.length
          ? "Possible matchup relevance; no fantasy-point adjustment."
          : "No position-linked injuries listed. This does not establish a healthy defense.",
  };
}
export function newSnapshot(now = new Date()) {
  return {
    schema_version: 1,
    kind: "user",
    label: "My weekly snapshot",
    season: now.getFullYear(),
    captured_at: now.toISOString(),
    players: [],
    games: [],
    reports: [],
  };
}
