import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const ui = dirname(dirname(fileURLToPath(import.meta.url)));
const client = join(ui, "dist", "client");
const secretMarker = "packaged-ui-test-secret-marker";

if (await loopbackAvailable()) {
  const npmCli = process.env.npm_execpath;
  assert.ok(npmCli, "Run this check using npm run test:packaged-ui.");
  const build = spawnSync(process.execPath, [npmCli, "run", "build"], {
    cwd: ui,
    env: {
      ...process.env,
      ORION_API_KEY: secretMarker,
      ORION_TEST_SECRET_MARKER: secretMarker,
    },
    stdio: "inherit",
  });
  if (build.error) {
    throw build.error;
  }
  assert.equal(build.status, 0, `production UI build failed with signal ${build.signal}`);

  const shell = join(client, "_shell.html");
  assert.ok(existsSync(shell), "production build did not generate dist/client/_shell.html");
  assert.ok(!existsSync(join(client, "index.html")), "production build generated index.html");
  assert.ok(
    !existsSync(join(ui, "scripts", "write-static-shell.mjs")),
    "obsolete static-shell script still exists",
  );

  const html = readFileSync(shell, "utf8");
  const stylesheet = assetReference(html, /\/assets\/[^" ]+\.css/);
  const entrypoint = assetReference(html, /\/assets\/index-[^"]+\.js/);
  const stylesheetPath = join(client, stylesheet.slice(1));
  const entrypointPath = join(client, entrypoint.slice(1));
  assert.ok(existsSync(stylesheetPath), `SPA shell referenced missing asset ${stylesheet}`);
  assert.ok(existsSync(entrypointPath), `SPA shell referenced missing asset ${entrypoint}`);
  assert.ok(readFileSync(stylesheetPath, "utf8").includes("grain"), "generated CSS is incomplete");
  assert.ok(!packagedText(client).includes(secretMarker), "production UI leaked a secret marker");

  process.stdout.write("packaged UI assertions passed\n");
} else {
  throw new Error("Packaged UI verification requires available loopback sockets.");
}

function assetReference(html, pattern) {
  const match = html.match(pattern);
  assert.ok(match, `SPA shell did not reference generated asset matching ${pattern}`);
  return match[0];
}

function packagedText(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .map((entry) => {
      const path = join(directory, entry.name);
      return entry.isDirectory() ? packagedText(path) : readFileSync(path, "utf8");
    })
    .join("\n");
}

function loopbackAvailable() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", (error) => {
      if (error.code === "EACCES" || error.code === "EPERM") {
        resolve(false);
      } else {
        reject(error);
      }
    });
    server.listen(0, "127.0.0.1", () => server.close(() => resolve(true)));
  });
}
