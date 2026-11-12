import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";
import { isTauri } from "@tauri-apps/api/core";
import { getRouter } from "./router";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Orion application root is unavailable");
const native = isTauri();

async function start(container: HTMLElement) {
  if (native) {
    const { installTauriHost } = await import("./lib/tauri-host");
    await installTauriHost();
  }
  createRoot(container).render(
    <StrictMode>
      <RouterProvider router={getRouter(native)} />
    </StrictMode>,
  );
}

void start(root).catch(() => {
  root.textContent = "Không thể khởi động Orion.";
});
