import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";

export default defineConfig({
  resolve: { tsconfigPaths: true },
  server: {
    host: "127.0.0.1",
    open: "/_shell.html",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:61888",
        changeOrigin: true,
      },
    },
  },
  plugins: [
    {
      name: "orion-static-development-shell",
      configureServer(server) {
        server.middlewares.use((request, _response, next) => {
          const path = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
          if (
            request.headers.accept?.includes("text/html") &&
            !path.startsWith("/api/") &&
            !path.split("/").pop()?.includes(".")
          ) {
            request.url = "/_shell.html";
          }
          next();
        });
      },
    },
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  build: { outDir: "dist/client", rollupOptions: { input: { index: "_shell.html" } } },
});
