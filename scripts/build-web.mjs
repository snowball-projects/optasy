import { cp, mkdir, rm, readFile, writeFile } from "node:fs/promises";
import { validateSnapshot } from "../web/model.mjs";

const root = new URL("../", import.meta.url);
validateSnapshot(
  JSON.parse(await readFile(new URL("web/sample.json", root), "utf8")),
);
const files = [
  "index.html",
  "styles.css",
  "app.mjs",
  "model.mjs",
  "sample.json",
  "icon.svg",
];
const html = await readFile(new URL("web/index.html", root), "utf8");
for (const name of ["styles.css", "app.mjs", "icon.svg"]) {
  if (!html.includes(name)) throw new Error(`Missing asset reference: ${name}`);
}
await rm(new URL("dist/", root), { recursive: true, force: true });
await mkdir(new URL("dist/", root));
for (const file of files)
  await cp(new URL(`web/${file}`, root), new URL(`dist/${file}`, root));
for (const file of ["LICENSE", "NOTICE"])
  await cp(new URL(file, root), new URL(`dist/${file}`, root));
await writeFile(new URL("dist/.nojekyll", root), "");
console.log(
  `Built ${files.length} static files. No private inputs or network access required.`,
);
