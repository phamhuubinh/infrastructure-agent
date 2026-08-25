import { readdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

const clientDirectory = new URL("../dist/client/", import.meta.url);
const assetsDirectory = new URL("assets/", clientDirectory);
const assets = await readdir(assetsDirectory);
const entry = assets.find((name) => /^index-.*\.js$/.test(name));

if (!entry) {
  throw new Error("TanStack client entry was not produced by vite build.");
}

// TanStack Start's normal build also emits an SSR server. Orion deliberately
// ships only the client bundle: every current route is client-owned and calls
// the same-origin FastAPI API. Hydration reconstructs the route from location.
const shell = `<!doctype html>
<html lang="vi" class="dark">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="description" content="Orion — Infrastructure Investigation Platform" />
    <title>Orion</title>
    <link rel="icon" href="/orion-icon-light.png" type="image/png" sizes="512x512" />
    <link rel="shortcut icon" href="/favicon.ico" type="image/x-icon" />
  </head>
  <body>
    <script type="module" src="/assets/${entry}"></script>
  </body>
</html>
`;

await writeFile(join(clientDirectory.pathname, "index.html"), shell, "utf8");
