import {
  TEAMS,
  POSITIONS,
  ROLES,
  STATUSES,
  PRACTICES,
  validateSnapshot,
  comparePlayer,
  newSnapshot,
} from "./model.mjs";

const $ = (id) => document.getElementById(id);
let data,
  selected = new Set(),
  currentWeek = 1,
  pendingReplace,
  injuryTeam,
  edited = false;
const node = (tag, text, className) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (className) n.className = className;
  return n;
};
const displayTime = (value) =>
  new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
const localTime = (value) => {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
};
const option = (value, label = value) => {
  const n = node("option", label);
  n.value = value;
  return n;
};
const message = (text) => {
  $("message").textContent = text;
};
const button = (label, action, className) => {
  const b = node("button", label, className);
  b.type = "button";
  b.addEventListener("click", action);
  return b;
};

for (let w = 1; w <= 18; w++) $("week").append(option(w, String(w)));
for (const [id, values] of [
  ["player-position", POSITIONS],
  ["player-team", TEAMS],
  ["player-opponent", TEAMS],
  ["defender-role", ROLES],
  ["defender-status", STATUSES],
  ["defender-practice", PRACTICES],
])
  for (const v of values) $(id).append(option(v));
for (const b of document.querySelectorAll("[data-close]"))
  b.addEventListener("click", () => $(b.dataset.close).close());
$("about-open").addEventListener("click", () => $("about").showModal());
for (const id of ["search", "position"])
  $(id).addEventListener("input", renderPlayers);
$("week").addEventListener("change", () => {
  currentWeek = Number($("week").value);
  render();
});

function apply(snapshot) {
  data = validateSnapshot(snapshot);
  selected = new Set(data.players.slice(0, 3).map((p) => p.id));
  currentWeek = data.games[0]?.week || 1;
  $("week").value = currentWeek;
  $("search").value = "";
  $("position").value = "";
  edited = false;
  message("");
  render();
}
function replace(snapshot) {
  if (edited || (data?.kind === "user" && data.players.length)) {
    pendingReplace = snapshot;
    $("replace-dialog").showModal();
  } else apply(snapshot);
}
$("confirm-replace").addEventListener("click", () => {
  apply(pendingReplace);
  pendingReplace = null;
  $("replace-dialog").close();
});
$("new").addEventListener("click", () => replace(newSnapshot()));
$("sample").addEventListener("click", loadSample);
async function loadSample() {
  try {
    const response = await fetch("./sample.json");
    if (!response.ok)
      throw new Error(
        "Example could not be loaded. Start a new snapshot instead.",
      );
    const sample = await response.json();
    data ? replace(sample) : apply(sample);
  } catch (error) {
    if (!data) apply(newSnapshot());
    message(error.message);
  }
}
$("import").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  try {
    if (!file) return;
    if (file.size > 2000000)
      throw new Error("Choose a JSON snapshot smaller than 2 MB.");
    const snapshot = validateSnapshot(JSON.parse(await file.text()));
    replace(snapshot);
  } catch (error) {
    message(
      `Could not import: ${error instanceof SyntaxError ? "the file is not valid JSON." : error.message}`,
    );
  } finally {
    event.target.value = "";
  }
});
function download() {
  if (!data) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2) + "\n"], {
      type: "application/json",
    }),
  );
  const a = node("a");
  a.href = url;
  a.download = `optasy-${data.kind}-${data.season}-${new Date().toISOString().replaceAll(":", "-")}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  message("Snapshot downloaded. It can be imported again.");
}
$("export").addEventListener("click", download);
$("save-before-replace").addEventListener("click", download);

function renderPlayers() {
  if (!data) return;
  const q = $("search").value.trim().toLowerCase(),
    pos = $("position").value;
  const players = data.players.filter(
    (p) =>
      (!pos || p.position === pos) &&
      `${p.name} ${p.team}`.toLowerCase().includes(q),
  );
  $("players").replaceChildren();
  for (const p of players) {
    const label = node(
      "label",
      undefined,
      `player-choice${selected.has(p.id) ? " selected" : ""}`,
    );
    const check = node("input");
    check.type = "checkbox";
    check.checked = selected.has(p.id);
    const copy = node("span", undefined, "player-copy");
    copy.append(
      node("strong", p.name),
      node("small", `${p.position} · ${p.team}`),
    );
    check.addEventListener("change", () => {
      check.checked ? selected.add(p.id) : selected.delete(p.id);
      label.classList.toggle("selected", check.checked);
      renderComparisons();
    });
    label.append(check, copy);
    $("players").append(label);
  }
  if (!players.length)
    $("players").append(
      node(
        "p",
        data.players.length
          ? "No matching candidates."
          : "Add your first candidate with +.",
        "privacy",
      ),
    );
}
function render() {
  $("season").textContent = `${data.season} · Week ${currentWeek}`;
  $("mode").textContent =
    data.kind === "sample" ? "Sample data" : "Your snapshot";
  $("mode").classList.toggle("user", data.kind !== "sample");
  $("dataset-note").textContent =
    data.kind === "sample"
      ? "Fictional players, injuries and matchups. Start a new snapshot for your own lineup."
      : `${data.label} · Snapshot ${displayTime(data.captured_at)} · No automatic live feed.`;
  renderPlayers();
  renderComparisons();
}
function renderComparisons() {
  $("comparisons").replaceChildren();
  const players = data.players.filter((p) => selected.has(p.id));
  if (!players.length) {
    const empty = node("div", undefined, "empty");
    empty.append(
      node("strong", "Choose players to compare"),
      node(
        "p",
        "Select candidates from your shortlist, or add a player and this week’s opponent.",
      ),
    );
    $("comparisons").append(empty);
    return;
  }
  for (const p of players) {
    const result = comparePlayer(data, p, currentWeek);
    const card = node("article", undefined, "comparison-card"),
      intro = node("div", undefined, "candidate");
    intro.append(node("h3", p.name), node("span", p.position, "position"));
    if (result.game) {
      intro.append(
        node("div", `${p.team} / ${result.opponent}`, "matchup"),
        node("span", displayTime(result.game.kickoff), "kickoff"),
      );
      intro.append(button("Add injury", () => openInjury(result.opponent)));
    } else intro.append(node("div", p.team, "matchup"));
    const evidence = node("div", undefined, "evidence");
    const meta = node("div", undefined, "report-meta");
    if (result.started)
      meta.append(node("span", "Game started · historical context", "flag"));
    if (result.report) {
      const r = result.report;
      meta.append(
        node(
          "span",
          `${r.coverage === "reviewed" ? "User-reviewed" : r.coverage === "partial" ? "Partial" : "Unknown"} coverage`,
        ),
      );
      meta.append(node("span", displayTime(r.observed_at)));
      if (result.stale)
        meta.append(node("span", "Older than 48h · check for updates", "flag"));
      if (r.url) {
        const link = node("a", `${r.source} ↗`);
        link.href = r.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        meta.append(link);
      } else meta.append(node("span", r.source));
    }
    evidence.append(meta);
    for (const d of result.defenders) {
      const detail = node("details", undefined, "defender"),
        summary = node("summary");
      summary.append(
        node("span", d.role, "role"),
        node("span", d.name, "defender-name"),
        node("span", d.status, `status${d.absent ? " absent" : ""}`),
        node("span", "+", "expand"),
      );
      const info = node("div", undefined, "defender-info");
      info.append(
        node(
          "p",
          `Possible relevance: ${d.relevance.toLowerCase()}.`,
          "relevance",
        ),
      );
      info.append(
        node(
          "p",
          `Practice: ${d.practice.toLowerCase()} · Prior snap share: ${d.snap_share === null ? "unknown" : `${d.snap_share}%`}`,
        ),
      );
      info.append(
        node(
          "p",
          `Replacement: ${d.replacement || "unknown"}. Quality difference not estimated.`,
        ),
      );
      if (d.note) info.append(node("p", d.note));
      detail.append(summary, info);
      evidence.append(detail);
    }
    evidence.append(node("p", result.message, "evidence-note"));
    card.append(intro, evidence);
    $("comparisons").append(card);
  }
}

const playerForm = $("player-form");
function syncGame() {
  const game = data.games.find(
    (g) =>
      g.week === currentWeek &&
      [g.home, g.away].includes(playerForm.elements.team.value),
  );
  playerForm.elements.opponent.disabled = Boolean(game);
  playerForm.elements.kickoff.readOnly = Boolean(game);
  if (game) {
    playerForm.elements.opponent.value =
      game.home === playerForm.elements.team.value ? game.away : game.home;
    playerForm.elements.kickoff.value = localTime(game.kickoff);
  }
}
playerForm.elements.team.addEventListener("change", syncGame);
$("add-player-open").addEventListener("click", () => {
  playerForm.reset();
  $("player-error").textContent = "";
  $("player-week").textContent = currentWeek;
  playerForm.elements.season.value = data.season;
  playerForm.elements.season.readOnly = Boolean(
    data.players.length || data.games.length || data.reports.length,
  );
  syncGame();
  $("player-dialog").showModal();
});
playerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    const v = Object.fromEntries(new FormData(playerForm)),
      copy = structuredClone(data);
    const game = copy.games.find(
      (g) => g.week === currentWeek && [g.home, g.away].includes(v.team),
    );
    if (!game)
      copy.games.push({
        week: currentWeek,
        home: v.opponent,
        away: v.team,
        kickoff: new Date(v.kickoff).toISOString(),
      });
    if (
      copy.players.some(
        (p) =>
          p.name.toLowerCase() === v.name.trim().toLowerCase() &&
          p.team === v.team,
      )
    )
      throw new Error("That candidate is already in your shortlist.");
    const player = {
      id: crypto.randomUUID(),
      name: v.name.trim(),
      position: v.position,
      team: v.team,
    };
    copy.players.push(player);
    copy.season = Number(v.season);
    copy.captured_at = new Date().toISOString();
    validateSnapshot(copy);
    data = copy;
    selected.add(player.id);
    edited = true;
    $("search").value = "";
    $("position").value = "";
    $("player-dialog").close();
    render();
    message("Candidate added.");
  } catch (error) {
    $("player-error").textContent = error.message;
  }
});

const injuryForm = $("injury-form");
function openInjury(team) {
  injuryTeam = team;
  injuryForm.reset();
  $("injury-error").textContent = "";
  $("injury-title").textContent = `${team} · Week ${currentWeek}`;
  const report = data.reports.find(
    (r) => r.week === currentWeek && r.team === team,
  );
  for (const key of ["source", "url", "observed_at"])
    injuryForm.elements[key].readOnly = Boolean(report);
  injuryForm.elements.source.value = report?.source || "";
  injuryForm.elements.url.value = report?.url || "";
  injuryForm.elements.observed_at.value = localTime(
    report?.observed_at || new Date(),
  );
  injuryForm.elements.status.value = "Unknown";
  injuryForm.elements.practice.value = "Unknown";
  $("injury-source-note").textContent = report
    ? "Adds to this team’s existing source vintage. Import a new snapshot to use a later report; old evidence is not silently retimestamped."
    : "Use the report’s timestamp. A manual entry has partial coverage.";
  $("injury-dialog").showModal();
}
injuryForm.addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    const v = Object.fromEntries(new FormData(injuryForm)),
      copy = structuredClone(data);
    let report = copy.reports.find(
      (r) => r.week === currentWeek && r.team === injuryTeam,
    );
    if (!report) {
      report = {
        week: currentWeek,
        team: injuryTeam,
        source: v.source.trim(),
        url: v.url.trim(),
        observed_at: new Date(v.observed_at).toISOString(),
        coverage: "partial",
        defenders: [],
      };
      copy.reports.push(report);
    }
    report.defenders.push({
      name: v.name.trim(),
      role: v.role,
      status: v.status,
      practice: v.practice,
      snap_share: v.snap_share === "" ? null : Number(v.snap_share),
      replacement: v.replacement.trim(),
      note: v.note.trim(),
    });
    copy.captured_at = new Date().toISOString();
    validateSnapshot(copy);
    data = copy;
    edited = true;
    $("injury-dialog").close();
    render();
    message("Injury added. Download the snapshot to keep your entries.");
  } catch (error) {
    $("injury-error").textContent = error.message;
  }
});

await loadSample();
