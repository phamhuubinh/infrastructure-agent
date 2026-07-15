import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";

export default defineConfig({
  resolve: {
    tsconfigPaths: true,
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:61888",
        changeOrigin: true,
      },
    },
  },
  plugins: [tanstackStart({ server: { entry: "server" } }), react(), tailwindcss()],
});
