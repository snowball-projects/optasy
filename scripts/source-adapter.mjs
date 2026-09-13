// Source-shaped parsing stays independent of fetching and public-data permission.
// This module does not grant rights to any input or label data current by itself.
import { createHash } from "node:crypto";

const TEAMS = new Set(
  "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split(
    " ",
  ),
);
const ALIASES = {
  LA: "LAR",
  OAK: "LV",
  SD: "LAC",
  STL: "LAR",
  JAC: "JAX",
  WSH: "WAS",
};
const GAME_TYPES = new Set(["REG", "WC", "DIV", "CON", "SB"]);
const NON_ROSTERED = new Set(["CUT", "RET", "UFA", "FA"]);
const MAX_CSV_BYTES = 20 * 1024 * 1024;

function fail(message) {
  throw new Error(message);
}
function clean(value) {
  return String(value ?? "").trim();
}
function team(value) {
  const input = clean(value).toUpperCase();
  const normalized = ALIASES[input] || input;
  if (!TEAMS.has(normalized)) fail(`Unknown NFL team: ${input || "(empty)"}`);
  return normalized;
}
function requiredColumns(rows, fields, label) {
  if (!rows.length) fail(`${label} CSV has no rows.`);
  for (const field of fields)
    if (!Object.hasOwn(rows[0], field))
      fail(`${label} CSV is missing ${field}.`);
}
function positiveInteger(value, label) {
  const input = clean(value);
  if (!/^\d+$/.test(input) || Number(input) < 1)
    fail(`Invalid ${label}: ${input}`);
  return Number(input);
}

/** Small bounded RFC 4180 parser: quoted commas/newlines/escaped quotes, no coercion. */
export function parseCsv(
  text,
  { maxBytes = MAX_CSV_BYTES, maxRows = 40000 } = {},
) {
  if (typeof text !== "string" || Buffer.byteLength(text) > maxBytes)
    fail("CSV exceeds the input limit.");
  text = text.replace(/^\uFEFF/, "");
  const records = [];
  let row = [],
    cell = "",
    quoted = false,
    afterQuote = false;
  const addCell = () => {
    row.push(cell);
    cell = "";
    afterQuote = false;
  };
  const addRow = () => {
    addCell();
    if (row.some((value) => value !== "")) records.push(row);
    row = [];
    if (records.length > maxRows + 1) fail("CSV exceeds the row limit.");
  };
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (c === '"') {
        quoted = false;
        afterQuote = true;
      } else cell += c;
    } else if (c === ",") addCell();
    else if (c === "\r" || c === "\n") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      addRow();
    } else if (afterQuote)
      fail("Unexpected character after CSV closing quote.");
    else if (c === '"') {
      if (cell) fail("Unexpected CSV quote.");
      quoted = true;
    } else cell += c;
    if (cell.length > 10000 || row.length > 200)
      fail("CSV field or column limit exceeded.");
  }
  if (quoted) fail("Unterminated CSV quote.");
  if (cell || row.length || afterQuote) addRow();
  const header = records.shift()?.map((name) => name.trim());
  if (
    !header ||
    header.some((name) => !name.trim()) ||
    new Set(header).size !== header.length
  )
    fail("CSV headers are empty or duplicated.");
  return records.map((record, index) => {
    if (record.length !== header.length)
      fail(`CSV row ${index + 2} has an unexpected column count.`);
    return Object.fromEntries(
      header.map((name, i) => [name.trim(), record[i]]),
    );
  });
}

export function rosterStatus(row) {
  const detail = clean(row.status_description_abbr).toUpperCase();
  if (["IR", "RESERVE/INJURED"].includes(detail)) return "injured-reserve";
  if (detail.includes("PUP")) return "pup";
  if (detail.includes("NFI")) return "nfi";
  if (detail.includes("SUSP")) return "suspended";
  return (
    {
      ACT: "active",
      DEV: "practice-squad",
      EXE: "exempt",
      RES: "reserve",
      INA: "inactive",
    }[clean(row.status).toUpperCase()] || "unknown"
  );
}

export function normalizeRoster(rows, season) {
  requiredColumns(
    rows,
    ["season", "team", "full_name", "gsis_id", "position", "status"],
    "Roster",
  );
  const identities = new Map();
  for (const row of rows) {
    if (Number(row.season) !== season) continue;
    const status = clean(row.status).toUpperCase();
    // Cut/retired entries remain in season rosters; they are not current players.
    // Reserve, inactive and practice-squad entries must remain searchable.
    const id = clean(row.gsis_id)
      ? `gsis:${clean(row.gsis_id)}`
      : clean(row.espn_id)
        ? `espn:${clean(row.espn_id)}`
        : clean(row.gsis_it_id)
          ? `gsis-it:${clean(row.gsis_it_id)}`
          : null;
    if (!id) {
      if (NON_ROSTERED.has(status)) continue;
      fail(
        `Rostered player has no stable source identity: ${clean(row.full_name)}`,
      );
    }
    const week = clean(row.week) ? positiveInteger(row.week, "roster week") : 0;
    const records = identities.get(id) || [];
    records.push({ row, week, status });
    identities.set(id, records);
  }
  const players = [];
  for (const [id, records] of identities) {
    const latest = Math.max(...records.map((record) => record.week));
    const current = records.filter(
      (record) => record.week === latest && !NON_ROSTERED.has(record.status),
    );
    if (!current.length) continue;
    const alternatives = new Map();
    for (const { row } of current) {
      const player = {
        id,
        name: clean(row.full_name),
        team: team(row.team),
        position: clean(row.position).toUpperCase() || "UNK",
        roster_status: rosterStatus(row),
      };
      if (!player.name) fail(`Player ${id} has no name.`);
      alternatives.set(JSON.stringify(player), player);
    }
    if (alternatives.size !== 1)
      fail(
        `Conflicting current roster identities for ${id}; refusing to guess a transfer.`,
      );
    players.push([...alternatives.values()][0]);
  }
  if (!players.length) fail(`Roster has no current players for ${season}.`);
  return players.sort(
    (a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id),
  );
}

/** nflverse documents gametime in Eastern, including games played elsewhere. */
export function easternTimestamp(date, time) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time))
    fail("Invalid schedule date or Eastern time.");
  const naive = Date.parse(`${date}T${time}:00Z`);
  if (
    !Number.isFinite(naive) ||
    new Date(naive).toISOString().slice(0, 16) !== `${date}T${time}`
  )
    fail("Invalid calendar date or clock time.");
  const format = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  let resolved = naive;
  for (let iteration = 0; iteration < 3; iteration++) {
    const parts = Object.fromEntries(
      format
        .formatToParts(new Date(resolved))
        .map(({ type, value }) => [type, value]),
    );
    const local = Date.parse(
      `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}Z`,
    );
    resolved += naive - local;
  }
  const parts = Object.fromEntries(
    format
      .formatToParts(new Date(resolved))
      .map(({ type, value }) => [type, value]),
  );
  if (
    `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}` !==
    `${date}T${time}`
  )
    fail("Schedule clock time does not exist in Eastern time.");
  return new Date(resolved).toISOString();
}

function tuesdayBefore(date) {
  const day = new Date(`${date}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 5) % 7));
  return day.toISOString().slice(0, 10);
}
function nextTuesday(date) {
  const day = new Date(`${date}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate() + (7 - ((day.getUTCDay() + 5) % 7)));
  return day.toISOString().slice(0, 10);
}

export function normalizeSchedule(rows, season) {
  requiredColumns(
    rows,
    [
      "season",
      "game_id",
      "game_type",
      "week",
      "gameday",
      "gametime",
      "away_team",
      "home_team",
    ],
    "Schedule",
  );
  const games = [],
    groups = new Map(),
    ids = new Set(),
    teamWeeks = new Set();
  for (const row of rows) {
    if (Number(row.season) !== season || !GAME_TYPES.has(clean(row.game_type)))
      continue;
    const week = positiveInteger(row.week, "schedule week");
    if (week > 22) fail("Schedule week exceeds the supported NFL season.");
    const type = clean(row.game_type),
      weekKey = `${season}-${type}-${week}`;
    const id = clean(row.game_id),
      home = team(row.home_team),
      away = team(row.away_team);
    if (!id || ids.has(id) || home === away)
      fail("Invalid or duplicate schedule game.");
    for (const value of [home, away]) {
      const key = `${weekKey}:${value}`;
      if (teamWeeks.has(key))
        fail(`Conflicting ${weekKey} games for ${value}.`);
      teamWeeks.add(key);
    }
    ids.add(id);
    const date = clean(row.gameday),
      time = clean(row.gametime);
    const dateKnown = date && date !== "NA";
    if (dateKnown) easternTimestamp(date, "12:00");
    const kickoff =
      dateKnown && time && time !== "NA" ? easternTimestamp(date, time) : null;
    // This CSV does not establish real-time game status. A past kickoff is
    // handled as started by the UI; scores alone never manufacture a final.
    games.push({
      id,
      week_key: weekKey,
      home,
      away,
      kickoff,
      status: kickoff ? "scheduled" : "tbd",
    });
    const group = groups.get(weekKey) || {
      key: weekKey,
      season,
      week,
      type,
      dates: [],
      teams: new Set(),
    };
    if (dateKnown) group.dates.push(date);
    group.teams.add(home);
    group.teams.add(away);
    groups.set(weekKey, group);
  }
  if (!games.length) fail(`Schedule has no supported games for ${season}.`);
  const regular = games.filter((game) => game.week_key.includes("-REG-"));
  const perTeam = new Map();
  regular.forEach((game) =>
    [game.home, game.away].forEach((value) =>
      perTeam.set(value, (perTeam.get(value) || 0) + 1),
    ),
  );
  const complete =
    regular.length === 272 &&
    perTeam.size === 32 &&
    [...perTeam.values()].every((count) => count === 17);
  const ordered = [...groups.values()].sort((a, b) => a.week - b.week);
  const weeks = ordered.map((group, index) => {
    group.dates.sort();
    if (!group.dates.length)
      fail(`No schedule dates establish the ${group.key} week window.`);
    const nextDates = ordered[index + 1]?.dates.filter(Boolean).sort();
    const startDate = tuesdayBefore(group.dates[0]);
    const earliestEnd = nextTuesday(group.dates.at(-1));
    // A postponed game can extend a week across the next nominal week.
    // Do not publish overlapping guessed windows; request source review.
    const nextStart = nextDates?.length ? tuesdayBefore(nextDates[0]) : null;
    if ((nextStart && nextStart < earliestEnd) || earliestEnd <= startDate)
      fail(`Changed schedule overlaps week windows at ${group.key}.`);
    const endDate = earliestEnd;
    const labels = {
      WC: "Wild card",
      DIV: "Divisional round",
      CON: "Conference championships",
      SB: "Super Bowl",
    };
    return {
      key: group.key,
      label: group.type === "REG" ? `Week ${group.week}` : labels[group.type],
      season,
      week: group.week,
      starts_at: easternTimestamp(startDate, "00:00"),
      ends_at: easternTimestamp(endDate, "00:00"),
      byes:
        complete && group.type === "REG"
          ? [...TEAMS].filter((value) => !group.teams.has(value)).sort()
          : [],
    };
  });
  return { games, weeks, coverage: complete ? "complete" : "partial" };
}

function gameStatus(value) {
  const status = clean(value);
  if (!status || status === "NA") return "Not listed";
  if (["Out", "Doubtful", "Questionable"].includes(status)) return status;
  return "Unknown";
}
function practiceStatus(value) {
  const status = clean(value);
  if (!status || status === "NA") return "Not listed";
  return (
    {
      "Did Not Participate In Practice": "Did not practice",
      "Limited Participation in Practice": "Limited",
      "Full Participation in Practice": "Full",
      "Did not practice": "Did not practice",
      Limited: "Limited",
      Full: "Full",
    }[status] || "Unknown"
  );
}

export function normalizeInjuries(rows, season, games, metadata) {
  requiredColumns(
    rows,
    [
      "season",
      "week",
      "team",
      "gsis_id",
      "full_name",
      "position",
      "report_primary_injury",
      "report_status",
      "practice_status",
    ],
    "Injury",
  );
  const reports = new Map();
  let matched = 0;
  for (const row of rows) {
    if (Number(row.season) !== season) continue;
    const week = positiveInteger(row.week, "injury week"),
      club = team(row.team);
    const type = clean(row.game_type || row.season_type);
    if (!type) fail("Injury row has no season phase.");
    const candidates = games.filter(
      (game) =>
        Number(game.week_key.split("-").at(-1)) === week &&
        (game.home === club || game.away === club) &&
        (type === "POST"
          ? !game.week_key.includes("-REG-")
          : game.week_key.includes(`-${type}-`)),
    );
    if (candidates.length !== 1)
      fail(
        `Injury row cannot join one scheduled game: ${season}/${type}/${week}/${club}.`,
      );
    const game = candidates[0],
      key = `${game.id}:${club}`;
    const report = reports.get(key) || {
      game_id: game.id,
      week_key: game.week_key,
      team: club,
      ...metadata,
      reported_at: null,
      coverage: "partial",
      entries: [],
    };
    // Report rows are retained regardless of position, game status or identity
    // presence in the current roster. Team-report coverage must not be filtered.
    const name = clean(row.full_name);
    if (!name) fail("Injury report row has no player name.");
    const rawId = clean(row.gsis_id);
    const id = rawId
      ? `gsis:${rawId}`
      : `report:${createHash("sha256")
          .update(
            `${club}:${name.toLowerCase()}:${clean(row.position).toUpperCase()}`,
          )
          .digest("hex")
          .slice(0, 24)}`;
    if (report.entries.some((entry) => entry.id === id))
      fail(
        `Duplicate injury row for ${key}/${id}; no date establishes a newer record.`,
      );
    const rawGame = clean(row.report_status),
      rawPractice = clean(row.practice_status);
    const status = gameStatus(rawGame),
      practice = practiceStatus(rawPractice);
    const injuries = [
      row.report_primary_injury,
      row.practice_primary_injury,
      row.practice_secondary_injury,
    ]
      .map(clean)
      .filter((value) => value && value !== "NA");
    const notes = [];
    if (status === "Unknown") notes.push(`Source game status: ${rawGame}.`);
    if (practice === "Unknown")
      notes.push(`Source practice status: ${rawPractice}.`);
    notes.push(
      "Source supplies no report date; the designation may predate the dataset update.",
    );
    report.entries.push({
      id,
      name,
      position: clean(row.position).toUpperCase() || "UNK",
      injury: [...new Set(injuries)].join("; ") || "Not specified",
      game_status: status,
      practice_status: practice,
      roster_status: "unknown",
      status_source: "official",
      note: notes.join(" "),
    });
    reports.set(key, report);
    matched++;
  }
  if (!matched) fail(`Injury source has no matched rows for ${season}.`);
  return [...reports.values()].map((report) => ({
    ...report,
    entries: report.entries.sort(
      (a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id),
    ),
  }));
}

export function normalizeSources({
  rosterCsv,
  scheduleCsv,
  injuryCsv,
  season,
  metadata,
  sources,
  generatedAt,
  mode = "example",
}) {
  const players = normalizeRoster(parseCsv(rosterCsv), season);
  const schedule = normalizeSchedule(parseCsv(scheduleCsv), season);
  const reports = normalizeInjuries(
    parseCsv(injuryCsv),
    season,
    schedule.games,
    metadata.injuries,
  );
  return {
    schema_version: 2,
    mode,
    label:
      mode === "live"
        ? "Opponent injury reports"
        : "Fictional source-adapter fixture",
    generated_at: generatedAt,
    sources,
    roster: { ...metadata.roster, reported_at: null, coverage: "partial" },
    schedule: {
      ...metadata.schedule,
      reported_at: null,
      coverage: schedule.coverage,
    },
    weeks: schedule.weeks,
    players,
    games: schedule.games,
    reports,
  };
}
