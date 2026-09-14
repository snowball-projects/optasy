import test from "node:test";
import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, writeFile, rm, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { validateFeed } from "../web/feed.mjs";
import {
  normalizeContributions,
  refreshContributions,
} from "../scripts/contribution-data.mjs";

const exec = promisify(execFile);
const root = new URL("../", import.meta.url);

test("offline publication pipeline keeps fresh core data through failed history and omits missing or invalid history", async (t) => {
  const directory = await mkdtemp(join(tmpdir(), "optasy-pipeline-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  for (const name of [
    "scripts",
    "web",
    "tests/fixtures",
    "package.json",
    "LICENSE",
    "NOTICE",
  ])
    await cp(new URL(name, root), join(directory, name), {
      recursive: true,
      filter: (path) =>
        !/\/(?:current|contributions)\.json(?:\.pending)?$/.test(path),
    });
  // Run the real package command and collectors offline. Only transport is
  // replaced: core CSVs are source-shaped fixtures; history returns HTTP 503.
  const preload = join(directory, "offline-fetch.mjs");
  await writeFile(
    preload,
    `
    import { readFile } from 'node:fs/promises';
    import { gzipSync } from 'node:zlib';
    const RealDate = Date;
    globalThis.Date = class extends RealDate {
      constructor(...args) { super(...(args.length ? args : ['2026-09-14T00:00:00.000Z'])); }
      static now() { return RealDate.parse('2026-09-14T00:00:00.000Z'); }
    };
    globalThis.fetch = async (url) => {
      const path = new URL(url).pathname;
      if (path.includes('/stats_player/') || process.env.OPTASY_TEST_CORE_FAIL)
        return new Response('unavailable', { status: 503 });
      const kind = path.includes('/rosters/') ? 'roster'
        : path.includes('/schedules/') ? 'schedule'
        : path.includes('/injuries/') ? 'injuries' : 'depth';
      const csv = await readFile(new URL('./tests/fixtures/source-' + kind + '.csv', import.meta.url));
      return new Response(kind === 'depth' ? gzipSync(csv) : csv, {
        headers: { 'content-type': 'application/octet-stream', 'last-modified': 'Sat, 12 Sep 2026 11:35:55 GMT' }
      });
    };
  `,
  );
  const pkg = JSON.parse(
    await readFile(join(directory, "package.json"), "utf8"),
  );
  const env = { ...process.env, NODE_OPTIONS: `--import=${preload}` };
  delete env.OPTASY_TEST_CORE_FAIL;
  const refresh = await exec("/bin/sh", ["-c", pkg.scripts.refresh], {
    cwd: directory,
    env,
  });
  assert.match(refresh.stderr, /Historical refresh unavailable/);
  const currentPath = join(directory, "web/current.json");
  const core = await readFile(currentPath, "utf8");
  const feed = validateFeed(JSON.parse(core));
  assert.equal(feed.generated_at, "2026-09-14T00:00:00.000Z");
  assert.ok(feed.reports.some((report) => report.entries.length));
  const historyPath = join(directory, "web/contributions.json");
  for (const content of [null, "not json", '{"schema_version":1}']) {
    if (content !== null) await writeFile(historyPath, content);
    await exec(process.execPath, ["scripts/build-web.mjs", "--require-live"], {
      cwd: directory,
    });
    assert.equal(
      await readFile(join(directory, "dist/current.json"), "utf8"),
      core,
    );
    await assert.rejects(access(join(directory, "dist/contributions.json")), {
      code: "ENOENT",
    });
  }
  // Failed core acquisition is still fatal and leaves its last valid file intact.
  await assert.rejects(
    exec("/bin/sh", ["-c", pkg.scripts.refresh], {
      cwd: directory,
      env: { ...env, OPTASY_TEST_CORE_FAIL: "1" },
    }),
  );
  assert.equal(await readFile(currentPath, "utf8"), core);
  await writeFile(currentPath, "{}");
  await assert.rejects(
    exec(process.execPath, ["scripts/build-web.mjs", "--require-live"], {
      cwd: directory,
    }),
  );
  await rm(currentPath);
  await assert.rejects(
    exec(process.execPath, ["scripts/build-web.mjs", "--require-live"], {
      cwd: directory,
    }),
  );
});

test("failed optional acquisition retains only independently revalidated historical artifacts", async (t) => {
  const directory = await mkdtemp(join(tmpdir(), "optasy-history-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const output = new URL(`file://${directory}/contributions.json`);
  const history = normalizeContributions(
    [
      "player_id,position_group,season,season_type,week,game_id,team,opponent_team,def_sacks,def_qb_hits,def_pass_defended,def_interceptions",
      "00-0012345,LB,2025,REG,1,2025_01_ARI_NO,ARI,NO,0.5,2,0,0",
    ].join("\n"),
    {
      retrieved_at: "2026-09-13T01:00:00Z",
      source_updated_at: "2026-08-13T01:00:00Z",
    },
  );
  const collect = async () => {
    throw new Error("offline");
  };
  await writeFile(output, JSON.stringify(history));
  const retained = await refreshContributions({ output, collect });
  assert.equal(retained.status, "retained");
  assert.deepEqual(retained.artifact, history);
  assert.deepEqual(JSON.parse(await readFile(output, "utf8")), history);
  await writeFile(output, JSON.stringify({ ...history, season: 2026 }));
  assert.equal(
    (await refreshContributions({ output, collect })).status,
    "unavailable",
  );
  await assert.rejects(access(output), { code: "ENOENT" });
  assert.equal(
    (await refreshContributions({ output, collect })).status,
    "unavailable",
  );
});
