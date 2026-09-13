import { parseFeed } from "./feed.mjs";
import {
  searchPlayers,
  currentWeek,
  comparePlayer,
  MAX_SELECTIONS,
  safeUrl,
} from "./model.mjs";

const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "optasy.selected.v2";
let feed = null,
  selected = [],
  weekKey = "",
  activeMode = "live",
  loading = false;
let lastCheck = 0,
  autoWeek = true,
  lastError = "";
const dateTime = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});
const day = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function button(text, action, className) {
  const el = node("button", text, className);
  el.type = "button";
  el.addEventListener("click", action);
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
    /* Storage is optional. */
  }
}
function sourceFor(id) {
  return feed.sources.find((source) => source.id === id);
}
function closeSearch() {
  $("search-results").hidden = true;
}
function renderSearch() {
  const list = $("search-results");
  const focusId = document.activeElement.dataset.playerId;
  list.replaceChildren();
  if (!feed || !$("search").value.trim()) {
    closeSearch();
    return;
  }
  const matches = searchPlayers(feed, $("search").value, selected).slice(0, 20);
  list.hidden = false;
  if (!matches.length)
    list.append(
      node(
        "p",
        "No matching rostered players. Try a name or team abbreviation.",
        "search-empty",
      ),
    );
  if (selected.length >= MAX_SELECTIONS)
    list.append(
      node(
        "p",
        "Six players selected. Remove one to add another.",
        "search-empty",
      ),
    );
  for (const player of matches) {
    const chosen = selected.includes(player.id);
    const choice = button("", () => addPlayer(player), "search-choice");
    choice.dataset.playerId = player.id;
    choice.disabled = chosen || selected.length >= MAX_SELECTIONS;
    choice.setAttribute(
      "aria-label",
      (chosen ? "Selected: " : "Add ") +
        player.name +
        ", " +
        player.team +
        ", " +
        player.position,
    );
    const info = node("span", undefined, "player-info");
    info.append(node("strong", player.name));
    const roster =
      player.roster_status !== "active"
        ? " · " + player.roster_status.replaceAll("-", " ")
        : "";
    info.append(node("small", player.team + " · " + player.position + roster));
    choice.append(info, node("span", chosen ? "Added" : "+", "add"));
    list.append(choice);
    if (focusId === player.id) choice.focus({ preventScroll: true });
  }
  $("search-status").textContent =
    matches.length +
    " matching players shown. Use Tab or Down Arrow to reach results.";
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
  renderCards();
  announce(player.name + " added.");
  $("search").focus();
}
function removePlayer(id, name) {
  const index = selected.indexOf(id);
  selected = selected.filter((value) => value !== id);
  saveSelection();
  renderCards();
  announce(name + " removed.");
  const removes = [...document.querySelectorAll(".remove")];
  (removes[Math.min(index, removes.length - 1)] || $("search")).focus();
}
function renderWeeks() {
  const select = $("week");
  select.replaceChildren();
  const current = currentWeek(feed);
  if (activeMode === "example") {
    if (!weekKey) weekKey = feed.weeks.at(-1)?.key || "";
  } else if (autoWeek || !feed.weeks.some((week) => week.key === weekKey)) {
    weekKey = current?.key || "";
  }
  if (!weekKey) {
    const option = node("option", "Current week unavailable");
    option.value = "";
    select.append(option);
  }
  for (const week of feed.weeks) {
    const option = node(
      "option",
      week.label +
        (activeMode === "live" && current?.key === week.key
          ? " · current"
          : ""),
    );
    option.value = week.key;
    select.append(option);
  }
  select.value = weekKey;
  select.disabled = feed.weeks.length === 0;
  const season = feed.weeks.find((week) => week.key === weekKey)?.season;
  document.querySelector('label[for="week"]').textContent =
    "NFL week" + (season ? " · " + season : "");
}
function renderStatus(error = lastError) {
  const status = $("data-status");
  status.replaceChildren();
  status.className = "notice";
  if (error) {
    status.classList.add("warning");
    const retained =
      feed && activeMode === "example"
        ? "Current NFL data is unavailable. The fictional example is still shown; these players, games and injuries are invented. "
        : feed
          ? "Refresh unavailable. Showing the previously loaded data; check its collection time. "
          : "Current NFL data is unavailable. ";
    status.append(node("p", retained + error));
    status.append(button("Try again", () => loadFeed("live")));
    if (!feed)
      status.append(button("Try fictional example", () => loadFeed("example")));
    return;
  }
  if (activeMode === "example") {
    status.classList.add("warning");
    status.append(
      node(
        "p",
        "Fictional example. Players, matchups and injuries below are invented; this is not current NFL data.",
      ),
    );
    status.append(button("Back to NFL players", () => loadFeed("live")));
    return;
  }
  const age = (Date.now() - Date.parse(feed.generated_at)) / 3600000;
  if (age > 24) status.classList.add("warning");
  const prefix = age > 24 ? "Collection is over 24 hours old. " : "";
  status.append(
    node(
      "p",
      prefix +
        "NFL reports via nflverse. Injury files update daily; the source does not supply report timestamps.",
    ),
  );
  status.append(node("span", "Collected " + time(feed.generated_at), "small"));
}
function renderSources() {
  const details = $("source-details");
  details.replaceChildren();
  if (!feed) {
    details.append(
      node(
        "p",
        "Current roster, schedule and injury data could not be loaded.",
      ),
    );
  } else {
    details.append(
      node(
        "p",
        activeMode === "example"
          ? "This fixture was created by snowball to demonstrate search, complete reports and missing-data states."
          : "One shared collection runs hourly, subject to GitHub Actions delays. nflverse injury and roster files normally update once daily; its schedule updates more often. An hourly download cannot make a daily report live. nflverse data are used under CC BY 4.0; optasy filters roster membership, normalizes fields and joins weekly opponents. No endorsement is implied.",
      ),
    );
    for (const [label, meta] of [
      ["Roster", feed.roster],
      ["Schedule", feed.schedule],
    ]) {
      const source = sourceFor(meta.source_id);
      const row = node("p", undefined, "source-meta");
      row.append(
        node("strong", label + ": "),
        link(source.label, source.url),
        document.createTextNode(
          " · source vintage " +
            vintage(meta) +
            " · file updated " +
            time(meta.source_updated_at) +
            " · collected " +
            time(meta.retrieved_at) +
            ".",
        ),
      );
      details.append(row);
    }
    for (const source of feed.sources) {
      const row = node("p", undefined, "source-meta");
      row.append(
        link(source.label, source.url),
        document.createTextNode(" · "),
        link(
          activeMode === "example" ? "Source & license" : "Data license",
          source.terms_url,
        ),
      );
      details.append(row);
    }
    details.append(
      node(
        "p",
        "Report vintage is when the underlying injury report was issued. File update is when the publisher changed its download. Collection is when optasy retrieved it. These are separate facts. Unknown vintage or missing entries never establish a healthy opponent.",
      ),
    );
  }
  details.append(
    link(
      "Source review and operating limits",
      "https://github.com/snowball-projects/optasy/blob/main/docs/DATA_SOURCES.md",
    ),
  );
  details.append(
    node(
      "p",
      "Selections are stored only in this browser. Search makes no requests to data providers. No accounts, league connections or analytics.",
    ),
  );
}
function renderEntry(entry) {
  const item = node("li", undefined, "injury");
  const row = node("div", undefined, "injury-main");
  row.append(node("span", entry.position, "role"));
  const info = node("div");
  info.append(node("p", entry.name, "injury-name"));
  info.append(
    node(
      "p",
      (entry.injury || "Injury not supplied") +
        " · Practice: " +
        entry.practice_status,
      "injury-detail",
    ),
  );
  row.append(info);
  const gameLabel =
    entry.game_status === "Not listed"
      ? "No game designation"
      : entry.game_status === "Unknown"
        ? "Game status unknown"
        : entry.game_status;
  const status = node(
    "span",
    gameLabel,
    "status" +
      (entry.game_status === "Out"
        ? " absent"
        : ["Not listed", "Unknown"].includes(entry.game_status)
          ? " unknown"
          : ""),
  );
  status.title = "Reported game designation";
  row.append(status);
  item.append(row);
  const context = node("details", undefined, "injury-context");
  context.dataset.entryId = entry.id;
  context.append(
    node(
      "summary",
      entry.relevance ? "Possible role relevance" : "Status context",
    ),
  );
  if (entry.relevance)
    context.append(
      node(
        "p",
        entry.relevance +
          ". A broad positional possibility; individual assignment and fantasy impact are not established.",
      ),
    );
  if (entry.availability) context.append(node("p", entry.availability));
  if (entry.status_source !== "official")
    context.append(
      node(
        "p",
        "Official game and practice designations are not established by this source.",
      ),
    );
  else
    context.append(
      node(
        "p",
        "Game and practice designations as supplied by the report source. Full practice or no game designation is not a guarantee of participation.",
      ),
    );
  if (entry.roster_status !== "active" && entry.roster_status !== "unknown")
    context.append(
      node(
        "p",
        "Roster status: " + entry.roster_status.replaceAll("-", " ") + ".",
      ),
    );
  if (entry.note) context.append(node("p", entry.note));
  item.append(context);
  return item;
}
function renderCards() {
  const cards = $("cards");
  const open = new Set(
    [...cards.querySelectorAll("details[open]")].map(
      (el) => el.closest("article").dataset.playerId + "/" + el.dataset.entryId,
    ),
  );
  const focused = document.activeElement;
  const focusedPlayer = focused.closest("article")?.dataset.playerId;
  const focusedEntry = focused.closest("details")?.dataset.entryId;
  const focusedRemove = focused.classList.contains("remove");
  cards.replaceChildren();
  $("selection-count").textContent =
    selected.length + " / " + MAX_SELECTIONS + " players";
  if (!selected.length) {
    const empty = node("div", undefined, "empty");
    const mark = node("span", "↗", "empty-mark");
    mark.setAttribute("aria-hidden", "true");
    empty.append(
      mark,
      node("h3", "Start with a player"),
      node(
        "p",
        "The matchup and full available opponent report will appear here.",
      ),
    );
    cards.append(empty);
    return;
  }
  for (const id of selected) {
    const player = feed.players.find((value) => value.id === id);
    const card = node("article", undefined, "player-card");
    card.dataset.playerId = id;
    const heading = node("div", undefined, "card-heading");
    const identity = node("div", undefined, "identity");
    const name = player?.name || "Player no longer in current roster";
    identity.append(node("h3", name));
    if (player)
      identity.append(
        node(
          "p",
          player.team +
            " · " +
            player.position +
            (player.roster_status === "active"
              ? ""
              : " · " + player.roster_status.replaceAll("-", " ")),
          "position",
        ),
      );
    heading.append(identity);
    const matchup = node("div", undefined, "matchup-area");
    const remove = button("×", () => removePlayer(id, name), "remove");
    remove.setAttribute("aria-label", "Remove " + name);
    const evidence = node("div", undefined, "evidence");
    if (player) {
      const result = comparePlayer(feed, player, weekKey);
      const opponent = node("div");
      opponent.append(
        node(
          "p",
          result.opponent
            ? "vs " + result.opponent
            : result.state === "bye"
              ? "Bye week"
              : "Opponent unknown",
          "matchup",
        ),
      );
      if (result.game) {
        const state = result.game.status;
        let kickoff = result.game.kickoff
          ? time(result.game.kickoff)
          : "Kickoff to be announced";
        if (["postponed", "canceled", "tbd"].includes(state))
          kickoff =
            state.charAt(0).toUpperCase() + state.slice(1) + " · " + kickoff;
        else if (state === "final") kickoff = "Final · " + kickoff;
        else if (result.started) kickoff = "Game has started · " + kickoff;
        opponent.append(node("p", kickoff, "kickoff"));
      }
      matchup.append(opponent);
      if (result.rosterStale)
        evidence.append(
          node(
            "p",
            "Roster file or collection is over 24 hours old; the player’s team may have changed.",
            "report-warning",
          ),
        );
      if (result.scheduleStale)
        evidence.append(
          node(
            "p",
            "Schedule file or collection is over 24 hours old. Kickoff and opponent may have changed.",
            "report-warning",
          ),
        );
      if (result.report) {
        const report = result.report;
        const title = node("div", undefined, "report-heading");
        title.append(
          node("strong", result.opponent + " injury report"),
          node(
            "span",
            "All " +
              report.entries.length +
              " available entries · " +
              (report.coverage === "complete"
                ? "complete source report"
                : "coverage " + report.coverage),
            "coverage",
          ),
        );
        evidence.append(title);
        const meta = node("div", undefined, "meta");
        const source = sourceFor(report.source_id);
        meta.append(
          link(source.label, source.url),
          node("span", "Report vintage: " + vintage(report)),
        );
        if (report.source_updated_at)
          meta.append(
            node("span", "File updated: " + time(report.source_updated_at)),
          );
        meta.append(node("span", "Collected: " + time(report.retrieved_at)));
        evidence.append(meta);
        if (!report.reported_at && !report.reported_date)
          evidence.append(
            node(
              "p",
              "Report date and time are not supplied. Current game availability cannot be confirmed from this file.",
              "report-warning",
            ),
          );
        if (result.stale)
          evidence.append(
            node(
              "p",
              "This report is old. Check the source before relying on its statuses.",
              "report-warning",
            ),
          );
        if (result.sourceFileStale)
          evidence.append(
            node(
              "p",
              "The source injury file is over 24 hours old, even if collected recently.",
              "report-warning",
            ),
          );
        if (result.sourceFileUnknown)
          evidence.append(
            node(
              "p",
              "Source file update time is not supplied; file freshness is unknown.",
              "report-warning",
            ),
          );
        if (result.retrievalStale)
          evidence.append(
            node(
              "p",
              "Collection is over 24 hours old. Newer reports may be missing.",
              "report-warning",
            ),
          );
        if (result.started)
          evidence.append(
            node(
              "p",
              "This game has started. This report is context, not a preserved pre-game recommendation.",
              "report-warning",
            ),
          );
        if (result.reportedAfterKickoff)
          evidence.append(
            node(
              "p",
              "Report issued at or after kickoff; not pre-game evidence.",
              "report-warning",
            ),
          );
        evidence.append(node("p", result.message, "report-message"));
        const entries = node("ul", undefined, "injury-list");
        entries.setAttribute(
          "aria-label",
          result.opponent + " complete available injury entries",
        );
        for (const entry of result.entries) entries.append(renderEntry(entry));
        evidence.append(entries);
      } else evidence.append(node("p", result.message, "report-message"));
    } else {
      evidence.append(
        node(
          "p",
          "This saved identity is absent from the latest roster source. Search again to confirm current team membership.",
          "report-message",
        ),
      );
    }
    matchup.append(remove);
    heading.append(matchup);
    card.append(heading, evidence);
    cards.append(card);
    for (const detail of card.querySelectorAll("details"))
      detail.open = open.has(id + "/" + detail.dataset.entryId);
    if (focusedPlayer === id) {
      if (focusedRemove) remove.focus({ preventScroll: true });
      else if (focusedEntry)
        [...card.querySelectorAll("details")]
          .find((el) => el.dataset.entryId === focusedEntry)
          ?.querySelector("summary")
          .focus({ preventScroll: true });
    }
  }
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
    const content = await response.text();
    const next = parseFeed(content);
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
      mode === "example" ? "Try Kai, BUF or WR" : "Name, team or position";
    document.querySelector('label[for="search"]').textContent =
      mode === "example" ? "Find a fictional player" : "Find an NFL player";
    $("search-help").textContent =
      mode === "example"
        ? "Fictional players only. Choose up to six."
        : "Choose up to six. Injured rostered players are included.";
    renderWeeks();
    renderStatus();
    renderSources();
    renderCards();
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
      renderSources();
    }
  } finally {
    loading = false;
    lastCheck = Date.now();
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
  ];
  const index = choices.indexOf(document.activeElement);
  const next = event.key === "ArrowDown" ? index + 1 : index - 1;
  if (next < 0) $("search").focus();
  else choices[Math.min(next, choices.length - 1)]?.focus();
});
document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".search-area")) closeSearch();
});
document.addEventListener("focusin", (event) => {
  if (!event.target.closest(".search-area")) closeSearch();
});
$("week").addEventListener("change", () => {
  weekKey = $("week").value;
  autoWeek = false;
  renderCards();
  announce("Opponent reports updated for the selected week.");
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && activeMode === "live") {
    renderWeeksIfLoaded();
    if (Date.now() - lastCheck > 300000) loadFeed("live", true);
  }
});
function renderWeeksIfLoaded() {
  if (feed) {
    renderWeeks();
    renderStatus();
    renderCards();
  }
}
// A visible tab must cross kickoff/week/freshness boundaries without a provider
// request. Keep open details and their keyboard focus while updating the clock.
setInterval(() => {
  if (document.hidden) return;
  renderWeeksIfLoaded();
  // Conditional same-origin refresh checks the shared published artifact only.
  // It never calls a provider, even with many simultaneous visitors.
  if (activeMode === "live" && Date.now() - lastCheck > 300000)
    loadFeed("live", true);
}, 60000);
await loadFeed("live");
