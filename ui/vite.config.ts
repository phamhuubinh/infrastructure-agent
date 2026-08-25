import { fileURLToPath } from "node:url";

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig(({ mode }) => {
  // The development UI talks to the protected API through Vite. Read Orion's
  // private root .env server-side so the browser never needs to know this key.
  const rootEnv = loadEnv(mode, projectRoot, "ORION_");
  const apiKey = process.env.ORION_API_KEY?.trim() || rootEnv.ORION_API_KEY?.trim();

  return {
    resolve: { tsconfigPaths: true },
    server: {
      proxy: {
        "/api": {
          target: "http://127.0.0.1:61888",
          changeOrigin: true,
          headers: apiKey ? { "X-API-Key": apiKey } : undefined,
        },
      },
    },
    plugins: [
      tanstackStart({ spa: { enabled: true }, server: { entry: "server" } }),
      react(),
      tailwindcss(),
    ],
  };
});
