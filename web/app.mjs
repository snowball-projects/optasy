import { parseFeed } from "./feed.mjs?v=0.5.0";
import {
  searchPlayers,
  opponentRoster,
  STATUS_LEGEND,
  DEFENSIVE_POSITIONS,
  currentWeek,
  comparePlayer,
  MAX_SELECTIONS,
  safeUrl,
} from "./model.mjs?v=0.5.0";
import {
  attachPopover,
  dismissPopover,
  isPopoverOpen,
  refreshPopover,
} from "./popover.mjs?v=0.5.0";

const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "optasy.selected.v2";
let feed = null,
  selected = [],
  weekKey = "",
  activeMode = "live",
  loading = false;
let lastCheck = 0,
  autoWeek = true,
  lastError = "",
  teamAssets = {};
const dateTime = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});
const kickoffTime = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const day = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});
const mobile = () => matchMedia("(max-width: 720px)").matches;
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function button(text, action, className) {
  const el = node("button", text, className);
  el.type = "button";
  if (action) el.addEventListener("click", action);
  return el;
}
function link(label, url) {
  const el = node("a", label);
  if (safeUrl(url)) {
    el.href = url;
    el.rel = "noopener noreferrer";
  }
  return el;
}
function time(value) {
  return value ? dateTime.format(new Date(value)) : "not supplied";
}
function vintage(item) {
  if (item.reported_at) return time(item.reported_at);
  if (item.reported_date)
    return (
      day.format(new Date(item.reported_date + "T00:00:00Z")) +
      " (time not supplied)"
    );
  return "not supplied";
}
function facts(pairs) {
  const list = node("dl");
  for (const [label, value] of pairs)
    list.append(node("dt", label), node("dd", value));
  return list;
}
function announce(text) {
  $("message").textContent = text;
}
function readSelection() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return Array.isArray(value)
      ? [
          ...new Set(
            value.filter((id) => typeof id === "string" && id.length <= 120),
          ),
        ].slice(0, MAX_SELECTIONS)
      : [];
  } catch {
    return [];
  }
}
function saveSelection() {
  if (activeMode !== "live") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selected));
  } catch {
    /* Optional storage. */
  }
}
function sourceFor(id) {
  return feed.sources.find((source) => source.id === id);
}
function openSearch() {
  dismissPopover();
  $("search").focus();
}
function teamMark(team) {
  const asset = teamAssets[team];
  const mark = node(
    "span",
    undefined,
    "team-mark" + (asset ? "" : " team-monogram"),
  );
  mark.setAttribute("aria-hidden", "true");
  if (asset) {
    const img = document.createElement("img");
    img.src = asset.url;
    img.alt = "";
    img.width = 64;
    img.height = 64;
    img.addEventListener(
      "error",
      () => {
        mark.replaceChildren(document.createTextNode(team));
        mark.classList.add("team-monogram");
      },
      { once: true },
    );
    mark.append(img);
  } else mark.textContent = team;
  return mark;
}
function closeSearch() {
  $("search-results").hidden = true;
}
function renderSearch() {
  const list = $("search-results"),
    focusId = document.activeElement.dataset.playerId;
  list.replaceChildren();
  if (!feed || !$("search").value.trim()) {
    closeSearch();
    return;
  }
  const matches = searchPlayers(feed, $("search").value, selected).slice(0, 30);
  list.hidden = false;
  if (!matches.length) list.append(node("p", "No matches", "search-empty"));
  if (selected.length >= MAX_SELECTIONS)
    list.append(
      node("p", "Six selected. Remove one to add another.", "search-empty"),
    );
  for (const player of matches) {
    const choice = button("", () => addPlayer(player), "search-choice");
    choice.dataset.playerId = player.id;
    choice.disabled = selected.length >= MAX_SELECTIONS;
    choice.setAttribute(
      "aria-label",
      "Add " + player.name + ", " + player.team + ", " + player.position,
    );
    const info = node("span", undefined, "player-info");
    info.append(
      node("strong", player.name),
      node(
        "small",
        player.team +
          " · " +
          player.position +
          (player.roster_status !== "active"
            ? " · " + player.roster_status.replaceAll("-", " ")
            : ""),
      ),
    );
    choice.append(info, node("span", "+", "add"));
    list.append(choice);
    if (focusId === player.id) choice.focus({ preventScroll: true });
  }
  $("search-status").textContent =
    matches.length +
    " matching players. Use Tab or Down Arrow to reach results.";
}
function addPlayer(player) {
  player = feed.players.find((candidate) => candidate.id === player.id);
  if (!player) {
    renderSearch();
    announce("That player is no longer in the current roster source.");
    return;
  }
  if (selected.includes(player.id) || selected.length >= MAX_SELECTIONS) return;
  selected.push(player.id);
  saveSelection();
  $("search").value = "";
  closeSearch();
  dismissPopover();
  renderCards();
  announce(player.name + " added.");
  if (mobile()) {
    const card = [...$("cards").children].find(
      (el) => el.dataset.playerId === player.id,
    );
    card.scrollIntoView({ block: "nearest", inline: "nearest" });
    card.querySelector(".remove").focus({ preventScroll: true });
  } else $("search").focus();
}
function removePlayer(id, name) {
  const index = selected.indexOf(id);
  selected = selected.filter((value) => value !== id);
  saveSelection();
  dismissPopover();
  renderCards();
  announce(name + " removed.");
  const removes = [...document.querySelectorAll(".remove")];
  const target = removes[Math.min(index, removes.length - 1)];
  if (target) target.focus();
  else openSearch();
}
function renderWeeks() {
  const select = $("week"),
    current = currentWeek(feed);
  if (activeMode === "example") {
    if (!weekKey) weekKey = feed.weeks.at(-1)?.key || "";
  } else if (autoWeek || !feed.weeks.some((week) => week.key === weekKey))
    weekKey = current?.key || "";
  const expected =
    feed.weeks.map((week) => week.key).join("|") + "|" + Boolean(weekKey);
  if (select.dataset.options !== expected) {
    select.replaceChildren();
    if (!weekKey) {
      const option = node("option", "Week unavailable");
      option.value = "";
      select.append(option);
    }
    for (const week of feed.weeks) {
      const option = node("option", week.label + " · " + week.season);
      option.value = week.key;
      select.append(option);
    }
    select.dataset.options = expected;
  }
  select.value = weekKey;
  select.disabled = !feed.weeks.length;
}
function renderStatus() {
  const status = $("data-status");
  status.replaceChildren();
  status.hidden =
    !lastError &&
    activeMode !== "example" &&
    (!feed || Date.now() - Date.parse(feed.generated_at) <= 86400000);
  $("info").classList.toggle(
    "stale",
    Boolean(
      lastError ||
      (feed && Date.now() - Date.parse(feed.generated_at) > 86400000),
    ),
  );
  if (status.hidden) return;
  status.append(
    node(
      "span",
      activeMode === "example"
        ? "Fictional example"
        : lastError
          ? "Refresh unavailable"
          : "Old collection",
    ),
  );
  if (lastError) status.append(button("Retry", () => loadFeed("live")));
  else if (activeMode === "example")
    status.append(button("Exit", () => loadFeed("live")));
}
function sourceDetails() {
  const panel = node("div");
  panel.append(node("h2", "Sources & information"));
  if (lastError)
    panel.append(
      node(
        "p",
        (activeMode === "example" && feed
          ? "Fictional data remains on screen. "
          : feed
            ? "Previously loaded data remains on screen. "
            : "Current NFL data is unavailable. ") + lastError,
      ),
    );
  if (activeMode === "example")
    panel.append(
      node(
        "p",
        "Fictional example: every player, matchup and injury is invented.",
      ),
    );
  if (feed) {
    panel.append(
      node(
        "p",
        activeMode === "example"
          ? "Synthetic data for trying the interface. These are not NFL reports."
          : "nflverse injury, roster and depth-chart files normally update daily. optasy checks hourly; GitHub runs can be delayed. Report timestamps are not supplied by the current injury source.",
      ),
    );
    panel.append(
      facts([
        ["Collected", time(feed.generated_at)],
        ["Selections", selected.length + " / " + MAX_SELECTIONS],
      ]),
    );
    for (const [label, meta] of [
      ["Roster", feed.roster],
      ["Schedule", feed.schedule],
      ...(feed.depth ? [["Depth chart", feed.depth]] : []),
    ]) {
      const block = node("div", undefined, "source-block"),
        source = sourceFor(meta.source_id);
      block.append(
        link(label + " · " + source.label, source.url),
        facts([
          ["Report vintage", vintage(meta)],
          ["File updated", time(meta.source_updated_at)],
          ["Collected", time(meta.retrieved_at)],
        ]),
      );
      panel.append(block);
    }
    const block = node("div", undefined, "source-block");
    for (const source of feed.sources) {
      const p = node("p");
      p.append(
        link(source.label, source.url),
        document.createTextNode(" · "),
        link(
          activeMode === "example" ? "License" : "CC BY 4.0",
          source.terms_url,
        ),
      );
      block.append(p);
    }
    panel.append(
      block,
      node(
        "p",
        activeMode === "example"
          ? "The example is a static fictional fixture and does not update."
          : "nflverse data are filtered, normalized and joined by optasy. Source-file updates and collection times are not report publication times. Defensive roster and injury entries are shown; independent completeness and current availability are not established.",
        "small",
      ),
    );
  }
  panel.append(
    node(
      "p",
      "Hover, focus or tap an injury for details. Game and practice designations are separate. Role relevance is a possibility, not an individual assignment or a measured fantasy effect.",
      "small",
    ),
  );
  panel.append(
    node(
      "p",
      "Selections stay in this browser. No accounts, analytics or per-visitor provider requests.",
      "small",
    ),
  );
  const links = node("div", undefined, "info-links");
  for (const [label, url] of [
    ["snowball", "https://snowball-projects.github.io/"],
    ["Source", "https://github.com/snowball-projects/optasy"],
    [
      "Data review",
      "https://github.com/snowball-projects/optasy/blob/main/docs/DATA_SOURCES.md",
    ],
    [
      "Image credits",
      "https://github.com/snowball-projects/optasy/blob/main/docs/MEDIA.md",
    ],
    ["Operations", "https://snowball-projects.github.io/operations/#optasy"],
    ["MIT", "https://snowball-projects.github.io/optasy/LICENSE"],
  ])
    links.append(link(label, url));
  panel.append(links);
  const legend = node("div", undefined, "status-legend");
  for (const [key, short, label] of STATUS_LEGEND)
    legend.append(
      node("span", short + " · " + label, "legend-item state-" + key),
    );
  panel.append(
    legend,
    node(
      "p",
      "Injury and reserve designations take priority over depth-chart colors. First string is not a confirmed game starter; active is not a health designation. Roster and depth context describe the current team, not historical game rosters.",
      "small",
    ),
  );
  if (!feed)
    panel.append(
      button("Try fictional example", () => {
        dismissPopover();
        loadFeed("example");
      }),
    );
  return panel;
}
function reportDetails(result) {
  const panel = node("div"),
    report = result.report;
  panel.append(node("h2", (result.opponent || "Opponent") + " report"));
  if (!report) {
    panel.append(node("p", result.message));
    return panel;
  }
  const source = sourceFor(report.source_id);
  panel.append(
    link(source.label, source.url),
    facts([
      [
        "Defensive injury entries",
        String(
          report.entries.filter((entry) =>
            DEFENSIVE_POSITIONS.has(entry.position),
          ).length,
        ),
      ],
      ["Coverage", report.coverage],
      ["Report vintage", vintage(report)],
      ["File updated", time(report.source_updated_at)],
      ["Collected", time(report.retrieved_at)],
    ]),
  );
  if (!report.reported_at && !report.reported_date)
    panel.append(
      node(
        "p",
        "Report date and time are not supplied. Current game availability cannot be confirmed from this file.",
      ),
    );
  const warnings = [];
  if (result.rosterStale)
    warnings.push("Roster context is old; team membership may have changed.");
  if (result.scheduleStale)
    warnings.push(
      "Schedule context is old; the opponent or kickoff may have changed.",
    );
  if (result.stale || result.sourceFileStale || result.retrievalStale)
    warnings.push(
      "Report, source file or collection is old. Newer information may be missing.",
    );
  if (result.sourceFileUnknown)
    warnings.push("Source-file update time is unknown.");
  if (result.started)
    warnings.push(
      "This game has started; this is not a preserved pre-game recommendation.",
    );
  if (result.reportedAfterKickoff)
    warnings.push("Report issued at or after kickoff.");
  for (const warning of warnings) panel.append(node("p", warning));
  panel.append(
    node(
      "p",
      "Defensive roster members and defensive injury entries are shown. Offense and special teams are excluded. Missing or partial coverage does not establish a healthy defense.",
      "small",
    ),
  );
  return panel;
}
function entryDetails(entry, result) {
  const panel = node("div");
  panel.append(node("h2", entry.name + " · " + entry.position));
  panel.append(
    facts([
      ["Injury", entry.injury],
      ["Game", entry.game_status],
      ["Practice", entry.practice_status],
    ]),
  );
  if (entry.availability) panel.append(node("p", entry.availability));
  if (entry.relevance)
    panel.append(
      node(
        "p",
        entry.relevance +
          ": a broad positional possibility. Individual assignments, replacement quality and fantasy effects are not established.",
      ),
    );
  if (entry.status_source !== "official")
    panel.append(
      node("p", "Official designations are not established by this source."),
    );
  else if (
    entry.practice_status === "Full" ||
    entry.game_status === "Not listed"
  )
    panel.append(
      node(
        "p",
        "Full practice or no game designation does not guarantee participation.",
        "small",
      ),
    );
  if (entry.note) panel.append(node("p", entry.note, "small"));
  const source = sourceFor(result.report.source_id),
    block = node("div", undefined, "source-block");
  block.append(
    link(source.label, source.url),
    facts([
      ["Report vintage", vintage(result.report)],
      ["File updated", time(result.report.source_updated_at)],
      ["Collected", time(result.report.retrieved_at)],
    ]),
  );
  panel.append(block);
  return panel;
}
function memberDetails(member, result) {
  const panel = member.injury
    ? entryDetails(member.injury, result)
    : node("div");
  if (!member.injury)
    panel.append(node("h2", member.name + " · " + member.position));
  panel.append(facts([["Roster", member.roster_status.replaceAll("-", " ")]]));
  if (member.depth.length)
    panel.append(
      facts([
        [
          "Depth chart",
          member.depth
            .map((entry) => entry.position + " #" + entry.rank)
            .join(", "),
        ],
        ["Chart observed", time(member.depth[0].observed_at)],
      ]),
    );
  if (member.starter)
    panel.append(
      node(
        "p",
        "First string on the depth chart; the starting lineup and game participation are not confirmed.",
        "small",
      ),
    );
  if (!member.injury)
    panel.append(
      node(
        "p",
        result.report
          ? "No matching injury entry in the available report. This does not establish health or game availability."
          : "Injury report unavailable. Game availability is unknown.",
        "small",
      ),
    );
  if (member.reportOnly)
    panel.append(
      node(
        "p",
        "Listed in the injury report, but this identity is absent from the current team roster.",
        "small",
      ),
    );
  const source = sourceFor(feed.roster.source_id);
  const block = node("div", undefined, "source-block");
  block.append(
    link(source.label, source.url),
    facts([["Roster collected", time(feed.roster.retrieved_at)]]),
  );
  if (member.depth.length) {
    const source = sourceFor(feed.depth.source_id);
    block.append(link(source.label, source.url));
  }
  panel.append(block);
  return panel;
}
function renderMember(member, result) {
  const item = node("li", undefined, "injury"),
    row = button("", null, "injury-row state-" + member.status.key);
  row.dataset.focusKey = "injury:" + member.id;
  row.setAttribute(
    "aria-label",
    member.name +
      ", " +
      member.position +
      ". " +
      member.status.label +
      (member.injury
        ? ". Injury: " +
          member.injury.injury +
          ". Game: " +
          member.injury.game_status +
          ". Practice: " +
          member.injury.practice_status
        : ". No matching injury entry") +
      ". Details.",
  );
  const person = node("span", undefined, "injury-person");
  person.append(
    node("span", member.name, "injury-name"),
    node("span", member.position, "role"),
  );
  const badges = node("span", undefined, "injury-badges");
  badges.setAttribute("aria-hidden", "true");
  badges.append(node("span", member.status.short, "status"));
  if (member.starter && member.status.key !== "starter")
    badges.append(node("span", "1st", "depth-badge"));
  row.append(person, badges);
  if (member.injury)
    row.append(node("span", member.injury.injury, "injury-detail"));
  attachPopover(row, () => memberDetails(member, result), {
    label: member.name + " roster and injury details",
  });
  item.append(row);
  return item;
}
function emptySlot() {
  const slot = node("div", undefined, "empty-slot"),
    add = button("+", openSearch, "empty-add");
  add.setAttribute("aria-label", "Search for a player");
  slot.append(add);
  return slot;
}
function renderCards() {
  const cards = $("cards"),
    focused = document.activeElement;
  const focusPlayer = focused.closest("article")?.dataset.playerId,
    focusKey = focused.dataset.focusKey,
    keepPopoverClosed = focused.getAttribute("aria-expanded") === "false";
  const scrolls = new Map(
    [...cards.querySelectorAll("article")].map((card) => [
      card.dataset.playerId,
      card.querySelector(".injury-list")?.scrollTop || 0,
    ]),
  );
  dismissPopover();
  cards.replaceChildren();
  cards.style.setProperty("--tile-count", Math.max(2, selected.length));
  $("selection-count").textContent =
    selected.length + " of " + MAX_SELECTIONS + " players selected";
  for (const id of selected) {
    const player = feed.players.find((value) => value.id === id);
    const name = player?.name || "Player unavailable",
      card = node("article", undefined, "player-card");
    card.dataset.playerId = id;
    card.setAttribute("aria-label", name);
    const remove = button("×", () => removePlayer(id, name), "remove");
    remove.dataset.focusKey = "remove";
    remove.setAttribute("aria-label", "Remove " + name);
    const header = node("div", undefined, "player-header");
    if (player) header.append(teamMark(player.team));
    header.append(node("h2", name, "player-name"));
    if (player)
      header.append(
        node("p", player.team + " · " + player.position, "player-team"),
      );
    card.append(remove, header);
    if (player) {
      const result = comparePlayer(feed, player, weekKey),
        matchup = node("div", undefined, "matchup");
      if (result.opponent) {
        matchup.append(node("span", "vs", "versus"), teamMark(result.opponent));
        const opponent = node("div", undefined, "opponent-info");
        opponent.append(node("p", result.opponent, "opponent-name"));
        if (result.game) {
          let kickoff = result.game.kickoff
            ? kickoffTime.format(new Date(result.game.kickoff))
            : "Time TBD";
          if (["postponed", "canceled"].includes(result.game.status))
            kickoff = result.game.status;
          else if (result.game.status === "final") kickoff = "Final";
          else if (result.started) kickoff = "Started · " + kickoff;
          opponent.append(node("p", kickoff, "kickoff"));
        }
        matchup.append(opponent);
      } else
        matchup.append(
          node(
            "p",
            result.state === "bye" ? "Bye" : "Matchup unavailable",
            "opponent-name",
          ),
        );
      const info = button(
        "i",
        null,
        "report-info" +
          (result.stale ||
          result.sourceFileStale ||
          result.retrievalStale ||
          result.rosterStale ||
          result.scheduleStale
            ? " stale"
            : ""),
      );
      info.dataset.focusKey = "report-info";
      info.setAttribute(
        "aria-label",
        (result.opponent || "Opponent") + " report source and freshness",
      );
      attachPopover(info, () => reportDetails(result), {
        label: "Report source and freshness",
      });
      matchup.append(info);
      card.append(matchup);
      const members = opponentRoster(feed, result, weekKey);
      if (members.length) {
        if (!result.report)
          card.append(node("p", "Injury report unavailable", "roster-notice"));
        const entries = node("ul", undefined, "injury-list");
        entries.setAttribute(
          "aria-label",
          result.opponent + " available defensive roster and injury entries",
        );
        for (const member of members)
          entries.append(renderMember(member, result));
        card.append(entries);
      } else
        card.append(
          node(
            "p",
            result.state === "bye"
              ? "Bye week"
              : result.report
                ? "No defensive entries · coverage unknown"
                : result.state === "canceled"
                  ? "Canceled"
                  : result.state === "no-week"
                    ? "Week unavailable"
                    : "Report unavailable",
            "report-empty",
          ),
        );
    } else
      card.append(
        node("p", "Absent from the current roster source.", "report-empty"),
      );
    cards.append(card);
    const list = card.querySelector(".injury-list");
    if (list) list.scrollTop = scrolls.get(id) || 0;
    if (focusPlayer === id && focusKey) {
      const target = [...card.querySelectorAll("[data-focus-key]")].find(
        (el) => el.dataset.focusKey === focusKey,
      );
      (target || remove).focus({ preventScroll: true });
    }
  }
  for (let i = selected.length; i < 2; i++) cards.append(emptySlot());
  if (keepPopoverClosed) dismissPopover();
}
async function loadFeed(mode, background = false) {
  if (loading) return;
  loading = true;
  try {
    const response = await fetch(
      mode === "example" ? "./example.json" : "./current.json",
      { cache: "no-cache", signal: AbortSignal.timeout(15000) },
    );
    if (!response.ok)
      throw new Error("The shared data file could not be retrieved.");
    const next = parseFeed(await response.text());
    if (next.mode !== mode)
      throw new Error("The data file has an unexpected mode.");
    if (mode !== activeMode || !feed) {
      selected = mode === "live" ? readSelection() : [];
      weekKey = "";
      autoWeek = true;
    }
    activeMode = mode;
    feed = next;
    lastError = "";
    $("search").disabled = false;
    $("search").placeholder =
      mode === "example" ? "Search example players" : "Search players";
    document.querySelector('label[for="search"]').textContent =
      mode === "example" ? "Find a fictional player" : "Find an NFL player";
    $("search-help").textContent =
      mode === "example"
        ? "Fictional players only. Choose up to six."
        : "Choose up to six. Injured rostered players are included.";
    renderStatus();
    if (!background || !isPopoverOpen()) {
      renderWeeks();
      renderCards();
    }
    if (background && !$("search-results").hidden) renderSearch();
    if (!background) {
      $("search").value = "";
      closeSearch();
      announce("");
    }
  } catch (error) {
    lastError =
      error.name === "TimeoutError" ? "The request timed out." : error.message;
    renderStatus();
    if (!feed) {
      $("search").disabled = true;
      $("week").disabled = true;
    }
  } finally {
    loading = false;
    lastCheck = Date.now();
  }
}
async function loadTeamAssets() {
  try {
    const response = await fetch("./team-assets.json", {
      cache: "no-cache",
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) return;
    const data = await response.json();
    for (const [team, asset] of Object.entries(data)) {
      if (
        /^[A-Z]{2,3}$/.test(team) &&
        asset &&
        ["svg", "png"].some(
          (extension) => asset.url === "team-logos/" + team + "." + extension,
        )
      )
        teamAssets[team] = asset;
    }
    if (feed && !isPopoverOpen()) renderCards();
  } catch {
    /* Team abbreviations remain usable without images. */
  }
}
$("search").addEventListener("input", renderSearch);
$("search").addEventListener("focus", renderSearch);
$("search").addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown") {
    renderSearch();
    const first = $("search-results").querySelector("button:not(:disabled)");
    if (first) {
      event.preventDefault();
      first.focus();
    }
  }
  if (event.key === "Escape") closeSearch();
});
$("search-results").addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeSearch();
    $("search").focus();
    closeSearch();
    return;
  }
  if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
  event.preventDefault();
  const choices = [
      ...$("search-results").querySelectorAll("button:not(:disabled)"),
    ],
    index = choices.indexOf(document.activeElement),
    next = event.key === "ArrowDown" ? index + 1 : index - 1;
  if (next < 0) $("search").focus();
  else choices[Math.min(next, choices.length - 1)]?.focus();
});
$("week").addEventListener("change", () => {
  weekKey = $("week").value;
  autoWeek = false;
  renderCards();
  announce("Opponent reports updated.");
});
document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".search-area")) closeSearch();
});
document.addEventListener("focusin", (event) => {
  if (!event.target.closest(".search-area")) closeSearch();
});
function updateClock() {
  if (!feed) return;
  renderStatus();
  refreshPopover();
  if (!isPopoverOpen()) {
    renderWeeks();
    renderCards();
  }
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && activeMode === "live") {
    updateClock();
    if (Date.now() - lastCheck > 300000) loadFeed("live", true);
  }
});
setInterval(() => {
  if (document.hidden) return;
  updateClock();
  if (activeMode === "live" && Date.now() - lastCheck > 300000)
    loadFeed("live", true);
}, 60000);
attachPopover($("info"), sourceDetails, {
  id: "source-popover",
  label: "Sources and information",
});
renderCards();
await Promise.all([loadFeed("live"), loadTeamAssets()]);
