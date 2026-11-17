import { useEffect } from "react";

/** Refresh server-owned snapshots while visible, including after an interrupted connection. */
export function observeHostRefresh(
  refresh: (current: () => boolean) => Promise<unknown>,
  interval = 5000,
  immediate = true,
) {
  let disposed = false;
  let running = false;
  let repeat = false;
  let timer: number | undefined;
  const current = () => !disposed;
  const run = async () => {
    if (disposed || document.hidden || navigator.onLine === false) return;
    if (running) {
      repeat = true;
      return;
    }
    window.clearTimeout(timer);
    running = true;
    try {
      await refresh(current);
    } catch {
      // Keep the last confirmed snapshot on transport errors.
    } finally {
      running = false;
      if (repeat) {
        repeat = false;
        void run();
      } else if (current()) {
        timer = window.setTimeout(() => void run(), interval);
      }
    }
  };
  const wake = () => void run();
  if (immediate) wake();
  else timer = window.setTimeout(wake, interval);
  window.addEventListener("focus", wake);
  window.addEventListener("online", wake);
  document.addEventListener("visibilitychange", wake);
  return () => {
    disposed = true;
    window.clearTimeout(timer);
    window.removeEventListener("focus", wake);
    window.removeEventListener("online", wake);
    document.removeEventListener("visibilitychange", wake);
  };
}

export function useHostRefresh(
  refresh: (current: () => boolean) => Promise<unknown>,
  interval = 5000,
  immediate = true,
) {
  useEffect(() => observeHostRefresh(refresh, interval, immediate), [refresh, interval, immediate]);
}
