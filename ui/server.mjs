import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

import app from "./dist/server/server.js";

const root = fileURLToPath(new URL(".", import.meta.url));
const clientRoot = resolve(root, "dist/client");
const host = process.env.HOST || "0.0.0.0";
const port = Number.parseInt(process.env.PORT || "3000", 10);

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".gif", "image/gif"],
  [".ico", "image/x-icon"],
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webp", "image/webp"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
]);

function publicFile(pathname) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  const filePath = resolve(clientRoot, decoded.replace(/^\/+/, ""));
  if (filePath !== clientRoot && !filePath.startsWith(`${clientRoot}${sep}`)) {
    return null;
  }
  return filePath;
}

async function serveStatic(request, response, pathname) {
  if (request.method !== "GET" && request.method !== "HEAD") return false;
  const filePath = publicFile(pathname);
  if (!filePath) return false;
  try {
    const details = await stat(filePath);
    if (!details.isFile()) return false;
    const headers = {
      "Content-Length": details.size,
      "Content-Type": contentTypes.get(extname(filePath)) || "application/octet-stream",
    };
    if (pathname.startsWith("/assets/")) {
      headers["Cache-Control"] = "public, max-age=31536000, immutable";
    }
    response.writeHead(200, headers);
    if (request.method === "HEAD") {
      response.end();
    } else {
      createReadStream(filePath).pipe(response);
    }
    return true;
  } catch (error) {
    if (error?.code === "ENOENT" || error?.code === "ENOTDIR") return false;
    throw error;
  }
}

async function requestBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return Buffer.concat(chunks);
}

async function handle(request, response) {
  const origin = `http://${request.headers.host || "localhost"}`;
  const url = new URL(request.url || "/", origin);
  if (await serveStatic(request, response, url.pathname)) return;

  const init = { method: request.method, headers: request.headers };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await requestBody(request);
  }
  const result = await app.fetch(new Request(url, init));
  for (const [name, value] of result.headers) response.setHeader(name, value);
  if (typeof result.headers.getSetCookie === "function") {
    const cookies = result.headers.getSetCookie();
    if (cookies.length) response.setHeader("set-cookie", cookies);
  }
  response.writeHead(result.status);
  if (request.method === "HEAD" || !result.body) {
    response.end();
    return;
  }
  Readable.fromWeb(result.body).pipe(response);
}

const server = createServer((request, response) => {
  handle(request, response).catch((error) => {
    console.error(error);
    if (!response.headersSent) response.writeHead(500, { "Content-Type": "text/plain" });
    response.end("Internal Server Error");
  });
});

server.listen(port, host, () => {
  console.log(`Orion UI listening on http://${host}:${port}`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
