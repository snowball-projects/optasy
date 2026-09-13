import { TEAMS, POSITIONS, validateFeed, safeUrl } from "./feed.mjs";

export { TEAMS, POSITIONS, validateFeed, safeUrl };
export const MAX_SELECTIONS = 6;
export const REPORT_MAX_AGE_HOURS = 48;
export const FEED_MAX_AGE_HOURS = 24;

const RELEVANCE = {
  QB: {
    CB: "Coverage",
    S: "Coverage",
    FS: "Coverage",
    SS: "Coverage",
    DB: "Coverage",
    EDGE: "Pass rush",
    DE: "Pass rush",
    OLB: "Pressure or coverage",
    DT: "Interior pressure",
    NT: "Interior pressure",
    DI: "Interior pressure",
    DL: "Pressure",
  },
  WR: {
    CB: "Coverage",
    S: "Deep coverage",
    FS: "Deep coverage",
    SS: "Coverage",
    DB: "Coverage",
    EDGE: "Time for routes to develop",
    DE: "Time for routes to develop",
  },
  RB: {
    DI: "Run defense",
    DT: "Run defense",
    NT: "Run defense",
    DL: "Run defense",
    DE: "Edge containment",
    EDGE: "Edge containment",
    LB: "Run defense or receiving coverage",
    ILB: "Run defense or receiving coverage",
    MLB: "Run defense or receiving coverage",
    OLB: "Run defense or receiving coverage",
    S: "Run support or receiving coverage",
    SS: "Run support or receiving coverage",
    FS: "Run support or receiving coverage",
  },
  FB: {
    DL: "Run defense",
    DT: "Run defense",
    LB: "Run defense or receiving coverage",
  },
  TE: {
    LB: "Receiving coverage",
    ILB: "Receiving coverage",
    MLB: "Receiving coverage",
    OLB: "Receiving coverage",
    S: "Receiving coverage",
    SS: "Receiving coverage",
    FS: "Receiving coverage",
    DB: "Receiving coverage",
    CB: "Receiving coverage",
  },
};

const normalizeSearch = (value) =>
  value
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();

// Current roster membership includes injured and reserve players. Game
// participation never determines eligibility for search.
export function searchPlayers(feed, query, selectedIds = []) {
  const words = normalizeSearch(String(query ?? ""))
    .split(/\s+/)
    .filter(Boolean);
  if (!words.length) return [];
  const selected = new Set(selectedIds);
  return feed.players
    .filter((player) => {
      if (selected.has(player.id)) return false;
      const haystack = normalizeSearch(
        `${player.name} ${player.team} ${player.position}`,
      );
      return words.every((word) => haystack.includes(word));
    })
    .sort(
      (a, b) =>
        a.name.localeCompare(b.name) ||
        a.team.localeCompare(b.team) ||
        a.id.localeCompare(b.id),
    );
}

export function restoreSelections(value, feed) {
  if (!Array.isArray(value)) return [];
  const current = new Set(feed.players.map((player) => player.id));
  return [
    ...new Set(value.filter((id) => typeof id === "string" && current.has(id))),
  ].slice(0, MAX_SELECTIONS);
}

export function currentWeek(feed, now = Date.now()) {
  return (
    feed.weeks.find(
      (week) =>
        Date.parse(week.starts_at) <= now && now < Date.parse(week.ends_at),
    ) ?? null
  );
}

export function vintage(
  metadata,
  now = Date.now(),
  maxAgeHours = REPORT_MAX_AGE_HOURS,
) {
  const exact = metadata.reported_at ? Date.parse(metadata.reported_at) : null;
  const date = metadata.reported_date
    ? Date.parse(`${metadata.reported_date}T00:00:00Z`)
    : null;
  const ageHours = exact === null ? null : Math.max(0, (now - exact) / 3600000);
  const ageDays =
    date === null
      ? null
      : Math.floor(now / 86400000) - Math.floor(date / 86400000);
  const sourceFileAgeHours = metadata.source_updated_at
    ? Math.max(0, (now - Date.parse(metadata.source_updated_at)) / 3600000)
    : null;
  return {
    vintagePrecision:
      exact !== null ? "time" : date !== null ? "date" : "unknown",
    ageHours,
    ageDays,
    // A date has no timezone or time. Its last possible instant is next-day
    // noon UTC, so only flag dates safely beyond the chosen age threshold.
    stale:
      ageHours !== null
        ? ageHours > maxAgeHours
        : ageDays !== null && ageDays >= Math.ceil((maxAgeHours + 36) / 24),
    retrievalStale:
      now - Date.parse(metadata.retrieved_at) > FEED_MAX_AGE_HOURS * 3600000,
    sourceFileAgeHours,
    sourceFileStale:
      sourceFileAgeHours !== null && sourceFileAgeHours > FEED_MAX_AGE_HOURS,
    sourceFileUnknown: sourceFileAgeHours === null,
  };
}

function availability(entry, freshness) {
  if (entry.status_source !== "official")
    return "Official availability unknown";
  if (entry.game_status === "Out")
    return freshness.vintagePrecision === "unknown" ||
      freshness.stale ||
      freshness.retrievalStale ||
      freshness.sourceFileStale
      ? "Reported Out; current availability needs confirmation"
      : "Official report designates Out for this game";
  if (["Doubtful", "Questionable"].includes(entry.game_status))
    return "Availability uncertain";
  if (entry.game_status === "Not listed")
    return "No game designation in this source; availability is not guaranteed";
  return "Official game availability unknown";
}

export function comparePlayer(feed, player, weekKey, now = Date.now()) {
  // A saved selection follows a transfer using its stable ID and current team.
  const currentPlayer = feed.players.find(
    (candidate) => candidate.id === player.id,
  );
  const rosterFreshness = vintage(feed.roster, now, FEED_MAX_AGE_HOURS),
    scheduleFreshness = vintage(feed.schedule, now, FEED_MAX_AGE_HOURS);
  const base = {
    entries: [],
    started: false,
    stale: false,
    retrievalStale: false,
    ageHours: null,
    ageDays: null,
    vintagePrecision: "unknown",
    sourceFileAgeHours: null,
    sourceFileStale: false,
    sourceFileUnknown: true,
    rosterStale:
      rosterFreshness.stale ||
      rosterFreshness.retrievalStale ||
      rosterFreshness.sourceFileStale,
    scheduleStale:
      scheduleFreshness.stale ||
      scheduleFreshness.retrievalStale ||
      scheduleFreshness.sourceFileStale,
  };
  if (!currentPlayer)
    return {
      ...base,
      state: "not-rostered",
      message: "This player is no longer in the current roster feed.",
    };
  const week = feed.weeks.find((candidate) => candidate.key === weekKey);
  if (!week)
    return {
      ...base,
      state: "no-week",
      message: "No current NFL week is established by this feed.",
    };
  const game = feed.games.find(
    (candidate) =>
      candidate.week_key === weekKey &&
      [candidate.home, candidate.away].includes(currentPlayer.team),
  );
  if (!game) {
    if (week.byes.includes(currentPlayer.team))
      return {
        ...base,
        state: "bye",
        message: "Confirmed bye in this schedule.",
      };
    return {
      ...base,
      state: "missing-schedule",
      message: "No matchup is available. This does not establish a bye.",
    };
  }
  const opponent = game.home === currentPlayer.team ? game.away : game.home;
  const started =
    ["in-progress", "final"].includes(game.status) ||
    (game.status === "scheduled" &&
      game.kickoff !== null &&
      Date.parse(game.kickoff) <= now);
  const result = { ...base, player: currentPlayer, game, opponent, started };
  if (game.status === "canceled")
    return {
      ...result,
      state: "canceled",
      message: "This game is canceled in the schedule.",
    };
  const report = feed.reports.find(
    (candidate) =>
      candidate.game_id === game.id &&
      candidate.week_key === weekKey &&
      candidate.team === opponent,
  );
  if (!report)
    return {
      ...result,
      state: "missing-report",
      message:
        "No opponent injury report is available for this matchup. Coverage is unknown.",
    };
  const freshness = vintage(report, now);
  const entries = report.entries.map((entry) => ({
    ...entry,
    relevance: RELEVANCE[currentPlayer.position]?.[entry.position] ?? null,
    availability: availability(entry, freshness),
  }));
  return {
    ...result,
    ...freshness,
    state: "report",
    report,
    entries,
    reportedAfterKickoff:
      report.reported_at !== null &&
      game.kickoff !== null &&
      Date.parse(report.reported_at) >= Date.parse(game.kickoff),
    message:
      "All available opponent entries are shown. Role context is a possibility, not an individual assignment or demonstrated fantasy effect.",
  };
}
