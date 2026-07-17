const { app, BrowserWindow } = require("electron");
const { createServer } = require("node:http");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const DIST_CLIENT = join(__dirname, "..", "ui", "dist", "client");
const DIST_SERVER = join(__dirname, "..", "ui", "dist", "server");
const BACKEND_PORT = 61888;

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".json": "application/json",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function serveStatic(res, filePath) {
  const ext = filePath.slice(filePath.lastIndexOf("."));
  const contentType = MIME[ext] || "application/octet-stream";
  try {
    const content = readFileSync(filePath);
    res.writeHead(200, { "Content-Type": contentType });
    res.end(content);
  } catch {
    return false;
  }
  return true;
}

async function createLocalServer() {
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://localhost");
    const pathname = url.pathname;

    if (pathname.startsWith("/api")) {
      const target = `http://127.0.0.1:${BACKEND_PORT}${pathname}${url.search}`;
      const opts = {
        method: req.method,
        headers: { ...req.headers, host: `127.0.0.1:${BACKEND_PORT}` },
      };
      try {
        const proxyRes = await fetch(target, opts);
        res.writeHead(proxyRes.status, Object.fromEntries(proxyRes.headers));
        for await (const chunk of proxyRes.body) {
          res.write(chunk);
        }
        res.end();
      } catch {
        res.writeHead(502, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Backend unavailable" }));
      }
      return;
    }

    if (pathname === "/" || !pathname.includes(".")) {
      try {
        const ssrModule = await import(join(DIST_SERVER, "server.js"));
        const ssrHandler = ssrModule.default || ssrModule;
        const ssrReq = new Request(`http://localhost${pathname}${url.search}`, {
          method: req.method,
          headers: req.headers,
        });
        const ssrRes = await ssrHandler.fetch(ssrReq);
        res.writeHead(ssrRes.status, Object.fromEntries(ssrRes.headers));
        const text = await ssrRes.text();
        res.end(text);
      } catch (err) {
        console.error("SSR error:", err);
        res.writeHead(500, { "Content-Type": "text/html" });
        res.end("<h1>Internal Server Error</h1>");
      }
      return;
    }

    const clientPath = join(DIST_CLIENT, pathname === "/" ? "index.html" : pathname);
    if (!serveStatic(res, clientPath)) {
      res.writeHead(404, { "Content-Type": "text/html" });
      res.end("<h1>Not Found</h1>");
    }
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

let mainWindow;

async function start() {
  const server = await createLocalServer();
  const addr = server.address();

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    title: "Orion",
    show: false,
  });

  mainWindow.loadURL(`http://127.0.0.1:${addr.port}/`);
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("closed", () => { mainWindow = null; });
}

app.whenReady().then(start);

app.on("window-all-closed", () => {
  app.quit();
});

app.on("activate", () => {
  if (mainWindow === null) start();
});
