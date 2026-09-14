import { cp, mkdir, rm, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { parseFeed, TEAMS, safeUrl } from "../web/feed.mjs";
import { sourceDefinitions, PUBLICATION_POLICY } from "./refresh-data.mjs";

const root = new URL("../", import.meta.url);
const requireLive = process.argv.includes("--require-live");
if (process.argv.slice(2).some((arg) => arg !== "--require-live"))
  throw new Error("Unknown build option.");
const example = parseFeed(
  await readFile(new URL("web/example.json", root), "utf8"),
);
if (example.mode !== "example")
  throw new Error("Example asset must be fictional.");
const files = [
  "index.html",
  "styles.css",
  "app.mjs",
  "model.mjs",
  "feed.mjs",
  "popover.mjs",
  "team-assets.json",
  "example.json",
  "icon.svg",
];
const teamAssets = JSON.parse(
  await readFile(new URL("web/team-assets.json", root), "utf8"),
);
if (
  Object.keys(teamAssets).length !== TEAMS.length ||
  TEAMS.some((team) => !teamAssets[team])
)
  throw new Error("Every NFL team must have a reviewed identifying logo.");
for (const [team, asset] of Object.entries(teamAssets)) {
  if (
    !TEAMS.includes(team) ||
    !["svg", "png"].some(
      (extension) => asset.url === `team-logos/${team}.${extension}`,
    ) ||
    !safeUrl(asset.source) ||
    !safeUrl(asset.license_url)
  )
    throw new Error("Invalid team image provenance.");
  const bytes = await readFile(new URL(`web/${asset.url}`, root));
  if (createHash("sha256").update(bytes).digest("hex") !== asset.sha256)
    throw new Error(`Team image changed without provenance review: ${team}`);
  files.push(asset.url);
}
let current;
try {
  current = await readFile(new URL("web/current.json", root), "utf8");
} catch (error) {
  if (error.code !== "ENOENT" || requireLive) throw error;
}
if (current) {
  const data = parseFeed(current);
  if (!PUBLICATION_POLICY.verified || data.mode !== "live")
    throw new Error("Current data must pass the reviewed public-data policy.");
  const season = data.weeks[0]?.season;
  const approved = sourceDefinitions(season);
  if (
    data.sources.length !== approved.length ||
    data.sources.some(
      (source) =>
        !approved.some(
          (entry) =>
            entry.id === source.id &&
            entry.url === source.url &&
            entry.terms_url === source.terms_url,
        ),
    )
  ) {
    throw new Error(
      "Current data sources are outside the reviewed release allowlist.",
    );
  }
  files.push("current.json");
}
const html = await readFile(new URL("web/index.html", root), "utf8");
for (const name of ["styles.css", "app.mjs", "icon.svg"]) {
  if (!html.includes(name)) throw new Error("Missing asset reference: " + name);
}
await rm(new URL("dist/", root), { recursive: true, force: true });
await mkdir(new URL("dist/", root));
await mkdir(new URL("dist/team-logos/", root));
for (const file of files)
  await cp(new URL("web/" + file, root), new URL("dist/" + file, root));
for (const file of ["LICENSE", "NOTICE"])
  await cp(new URL(file, root), new URL("dist/" + file, root));
await writeFile(new URL("dist/.nojekyll", root), "");
console.log(
  "Built " +
    files.length +
    " public static files; " +
    (current
      ? "validated current feed included."
      : "current feed unavailable, fictional fallback only."),
);
