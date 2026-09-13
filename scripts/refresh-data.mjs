// One bounded build-time download per source. Visitors read only the generated
// same-origin JSON. No provider payload is saved by this collector.
import { rename, rm, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { normalizeSources } from "./source-adapter.mjs";

const RELEASE_ROOT =
  "https://github.com/nflverse/nflverse-data/releases/download";
const TERMS_URL =
  "https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md";
const OUTPUT = new URL("../web/current.json", import.meta.url);
const MAX_BYTES = 20 * 1024 * 1024;
const TIMEOUT_MS = 30000;
const MAX_REDIRECTS = 3;
const REDIRECT_HOSTS = new Set([
  "github.com",
  "release-assets.githubusercontent.com",
  "objects.githubusercontent.com",
]);

// Set true only after the source-specific public-data provenance review. This
// cannot be bypassed using command-line flags, input files or browser settings.
export const PUBLICATION_POLICY = Object.freeze({
  verified: true,
  checked_on: "2026-09-13",
  reason:
    "nflverse-data explicitly releases these datasets under CC BY 4.0. optasy filters the season and current roster, normalizes teams and timestamps, and groups every available injury row by game. Original report dates are not supplied. No endorsement is implied.",
});

export function sourceDefinitions(season) {
  if (!Number.isInteger(season) || season < 2026 || season > 2100)
    throw new Error("Unsupported source season.");
  return [
    {
      id: "nflverse-roster",
      key: "roster",
      label: "nflverse season roster",
      url: `${RELEASE_ROOT}/rosters/roster_${season}.csv`,
    },
    {
      id: "nflverse-schedule",
      key: "schedule",
      label: "nflverse schedule",
      url: `${RELEASE_ROOT}/schedules/games.csv`,
    },
    {
      id: "nflverse-injuries",
      key: "injuries",
      label: "nflverse injury report data",
      url: `${RELEASE_ROOT}/injuries/injuries_${season}.csv`,
    },
  ].map((source) => ({
    ...source,
    terms_url: TERMS_URL,
    permission: PUBLICATION_POLICY.verified ? "verified" : "example",
    permission_note: PUBLICATION_POLICY.reason,
  }));
}

function safeRedirect(value) {
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.port ||
    !REDIRECT_HOSTS.has(url.hostname)
  )
    throw new Error("Source redirected outside the HTTPS release allowlist.");
  return url;
}

/** An overall timeout, byte cap and redirect allowlist apply to each source. */
export async function fetchSource(
  source,
  {
    fetchImpl = fetch,
    now = () => new Date(),
    timeoutMs = TIMEOUT_MS,
    maxBytes = MAX_BYTES,
  } = {},
) {
  const seasonPattern = "(?:202[6-9]|20[3-9][0-9]|2100)";
  const sourcePattern = new RegExp(
    `^https://github\\.com/nflverse/nflverse-data/releases/download/(?:rosters/roster_${seasonPattern}\\.csv|injuries/injuries_${seasonPattern}\\.csv|schedules/games\\.csv)$`,
  );
  if (!sourcePattern.test(source.url))
    throw new Error("Source URL is outside the fixed dataset allowlist.");
  const signal = AbortSignal.timeout(timeoutMs);
  let url = safeRedirect(source.url),
    response;
  for (let redirects = 0; redirects <= MAX_REDIRECTS; redirects++) {
    response = await fetchImpl(url, {
      signal,
      redirect: "manual",
      headers: {
        Accept: "text/csv",
        "User-Agent":
          "optasy-source-refresh/1.0 (https://github.com/snowball-projects/optasy)",
      },
    });
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      await response.body?.cancel();
      if (redirects === MAX_REDIRECTS)
        throw new Error("Source exceeded the redirect limit.");
      const location = response.headers.get("location");
      if (!location) throw new Error("Source redirect omitted a location.");
      url = safeRedirect(new URL(location, url).href);
      continue;
    }
    break;
  }
  if (!response.ok) {
    const retryAfter = response.headers.get("retry-after");
    await response.body?.cancel();
    throw new Error(
      `Source ${source.id} returned HTTP ${response.status}; the published snapshot was not replaced.${retryAfter ? ` Retry-After: ${retryAfter.slice(0, 100)}. No immediate retry is attempted.` : ""}`,
    );
  }
  const contentLength = Number(response.headers.get("content-length"));
  if (contentLength > maxBytes) {
    await response.body?.cancel();
    throw new Error("Source exceeds the download size limit.");
  }
  const contentType = response.headers.get("content-type") || "";
  if (/text\/html|application\/(?:json|xml)/i.test(contentType)) {
    await response.body?.cancel();
    throw new Error("Source returned an unexpected content type.");
  }
  if (!response.body) throw new Error("Source returned no body.");
  const chunks = [];
  let bytes = 0;
  const reader = response.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maxBytes) {
        await reader.cancel();
        throw new Error("Source exceeds the download size limit.");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const retrievedAt = now().toISOString();
  const modified = response.headers.get("last-modified");
  const parsed = modified ? Date.parse(modified) : NaN;
  if (Number.isFinite(parsed) && parsed > Date.parse(retrievedAt) + 300000)
    throw new Error("Source asset timestamp is in the future.");
  return {
    csv: new TextDecoder("utf-8", { fatal: true }).decode(
      Buffer.concat(chunks),
    ),
    bytes,
    metadata: {
      source_id: source.id,
      reported_at: null,
      source_updated_at: Number.isFinite(parsed)
        ? new Date(parsed).toISOString()
        : null,
      retrieved_at: retrievedAt,
    },
  };
}

export async function collectFeed({
  season,
  inspect = false,
  fetchImpl = fetch,
  now = () => new Date(),
} = {}) {
  if (!inspect && !PUBLICATION_POLICY.verified)
    throw new Error(PUBLICATION_POLICY.reason);
  const definitions = sourceDefinitions(season);
  // Three total source fetches, with no retry storm. The next scheduled run is
  // the retry. No source data or partially assembled feed is written on failure.
  const outcomes = await Promise.allSettled(
    definitions.map((source) => fetchSource(source, { fetchImpl, now })),
  );
  const failures = outcomes.flatMap((result, index) =>
    result.status === "rejected"
      ? [`${definitions[index].key}: ${result.reason.message}`]
      : [],
  );
  if (failures.length) throw new Error(failures.join("\n"));
  const inputs = Object.fromEntries(
    definitions.map((source, index) => [source.key, outcomes[index].value]),
  );
  const generatedAt = now().toISOString();
  const feed = normalizeSources({
    rosterCsv: inputs.roster.csv,
    scheduleCsv: inputs.schedule.csv,
    injuryCsv: inputs.injuries.csv,
    season,
    metadata: Object.fromEntries(
      Object.entries(inputs).map(([key, value]) => [key, value.metadata]),
    ),
    sources: definitions.map(({ key, ...source }) => source),
    generatedAt,
    mode: PUBLICATION_POLICY.verified ? "live" : "example",
  });
  if (!inspect) {
    // Imported lazily so source inspection remains possible while schema work
    // evolves. Publication always passes the browser's actual feed validator.
    const { validateFeed } = await import("../web/feed.mjs");
    validateFeed(feed, Date.parse(generatedAt));
  }
  return {
    feed,
    summary: {
      generated_at: generatedAt,
      season,
      players: feed.players.length,
      games: feed.games.length,
      reports: feed.reports.length,
      entries: feed.reports.reduce(
        (sum, report) => sum + report.entries.length,
        0,
      ),
      source_updated_at: Object.fromEntries(
        Object.entries(inputs).map(([key, value]) => [
          key,
          value.metadata.source_updated_at,
        ]),
      ),
      reported_at: null,
      publication_permitted: PUBLICATION_POLICY.verified,
    },
  };
}

async function main() {
  const args = process.argv.slice(2);
  if (args.some((arg) => arg !== "--inspect"))
    throw new Error("Usage: node scripts/refresh-data.mjs [--inspect]");
  const inspect = args.includes("--inspect");
  const now = new Date(),
    season =
      now.getUTCMonth() < 3 ? now.getUTCFullYear() - 1 : now.getUTCFullYear();
  const { feed, summary } = await collectFeed({ season, inspect });
  if (!inspect) {
    const temporary = new URL("./current.json.pending", OUTPUT);
    try {
      await writeFile(temporary, `${JSON.stringify(feed)}\n`, { flag: "wx" });
      await rename(temporary, OUTPUT);
    } catch (error) {
      await rm(temporary, { force: true });
      throw error;
    }
  }
  console.log(JSON.stringify({ ...summary, written: !inspect }, null, 2));
}

if (
  process.argv[1] &&
  pathToFileURL(process.argv[1]).href === import.meta.url
) {
  main().catch((error) => {
    console.error(`Source refresh failed: ${error.message}`);
    process.exitCode = 1;
  });
}
