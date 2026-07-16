import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import viteTsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [viteTsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
  },
});
