import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
} from "@tanstack/react-router";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { AppSidebar } from "@/components/AppSidebar";
import { HostUpdateNotice } from "@/components/HostUpdateNotice";
import { CommandPalette } from "@/components/CommandPalette";
import { ChatProvider } from "@/lib/chat-store";
import { AUTH_EXPIRED_EVENT, getAuthSession, login, logout, type AuthSession } from "@/lib/api";
import {
  SERVER_CHANGED_EVENT,
  isNativeHost,
  reportNativeStartupReady,
} from "@/lib/server-profiles";
import { ServerConnections } from "@/components/ServerConnections";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <div className="mb-3 text-mono text-xs text-muted-foreground">ERR · 404</div>
        <h1 className="text-display text-6xl text-foreground">Not found</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary-hover active:bg-primary-active"
          >
            Back to chat
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <div className="text-mono text-xs text-destructive mb-3">ERR · 500</div>
        <h1 className="text-display text-4xl text-foreground">Something broke</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The workspace hit an unexpected error. You can retry or head home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary-hover active:bg-primary-active"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
      { title: "Orion" },
      { name: "description", content: "Orion — Chat, Projects and remote commands" },
    ],
    links: [
      {
        rel: "icon",
        href: "/orion-icon-light.png",
        type: "image/png",
        sizes: "512x512",
        media: "(prefers-color-scheme: light)",
      },
      {
        rel: "icon",
        href: "/orion-icon-dark.png",
        type: "image/png",
        sizes: "512x512",
        media: "(prefers-color-scheme: dark)",
      },
      { rel: "shortcut icon", href: "/favicon.ico", type: "image/x-icon" },
      { rel: "apple-touch-icon", href: "/orion-icon.png" },
    ],
  }),
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function useTheme() {
  const [theme] = useState<"light" | "dark">(
    () =>
      (typeof localStorage !== "undefined"
        ? (localStorage.getItem("theme") as "light" | "dark")
        : "dark") ?? "dark",
  );

  useEffect(() => {
    document.documentElement.className = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);
}

function RootComponent() {
  const shellRef = useCallback((shell: HTMLDivElement | null) => {
    const viewport = window.visualViewport;
    if (!viewport || !shell) return;
    const fitViewport = () => {
      // Pin the mobile shell to the visible area when the on-screen keyboard opens.
      shell.style.setProperty("--orion-viewport-height", `${viewport.height}px`);
      shell.style.setProperty("--orion-viewport-top", `${viewport.offsetTop}px`);
    };
    fitViewport();
    viewport.addEventListener("resize", fitViewport);
    viewport.addEventListener("scroll", fitViewport);
    return () => {
      viewport.removeEventListener("resize", fitViewport);
      viewport.removeEventListener("scroll", fitViewport);
    };
  }, []);
  const readyShellRef = useCallback(
    (shell: HTMLDivElement | null) => {
      if (shell) reportNativeStartupReady();
      return shellRef(shell);
    },
    [shellRef],
  );
  const { queryClient } = Route.useRouteContext();
  useTheme();
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [authError, setAuthError] = useState("");
  const [password, setPassword] = useState("");
  const [authCode, setAuthCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [serverGeneration, setServerGeneration] = useState(0);
  useEffect(() => {
    const changed = () => {
      queryClient.clear();
      setAuth(null);
      setPassword("");
      setAuthCode("");
      setAuthError("");
      setServerGeneration((value) => value + 1);
    };
    window.addEventListener(SERVER_CHANGED_EVENT, changed);
    return () => window.removeEventListener(SERVER_CHANGED_EVENT, changed);
  }, [queryClient]);
  useEffect(() => {
    let active = true;
    void getAuthSession()
      .then((state) => {
        if (active) setAuth(state);
      })
      .catch(() => {
        if (active) setAuthError("Cannot reach Orion.");
      });
    const expired = () => {
      setAuth((current) =>
        current?.remote_access ? { ...current, authenticated: false } : current,
      );
      queryClient.clear();
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    return () => {
      active = false;
      window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
    };
  }, [queryClient, serverGeneration]);
  useEffect(() => {
    if (!auth?.remote_access || !auth.authenticated || !auth.expires_at) return;
    const remaining = Math.max(0, auth.expires_at * 1000 - Date.now());
    const timer = window.setTimeout(() => {
      setAuth({ remote_access: true, authenticated: false, expires_at: null });
      queryClient.clear();
    }, remaining);
    return () => window.clearTimeout(timer);
  }, [auth, queryClient]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setAuthError("");
    try {
      await login(password, authCode.trim());
      setPassword("");
      setAuthCode("");
      setAuth(await getAuthSession());
    } catch {
      setAuthError("Thông tin xác thực không hợp lệ hoặc đăng nhập đang bị giới hạn.");
    } finally {
      setSubmitting(false);
    }
  }

  async function signOut() {
    try {
      await logout();
      if (!isNativeHost()) {
        window.location.reload();
        return;
      }
      queryClient.clear();
      setAuth({ remote_access: true, authenticated: false, expires_at: null });
    } catch {
      setAuthError("Could not sign out. Try again.");
    }
  }

  if (!auth)
    return (
      <div
        ref={shellRef}
        className="space-y-4 bg-background p-6 text-foreground md:min-h-screen max-md:fixed max-md:inset-x-0 max-md:top-[var(--orion-viewport-top,0px)] max-md:h-[var(--orion-viewport-height,100dvh)] max-md:overflow-y-auto"
      >
        <p role="status">{authError || "Loading Orion…"}</p>
        {authError && <ServerConnections />}
      </div>
    );
  if (auth.remote_access && !auth.authenticated) {
    if (isNativeHost())
      return (
        <div
          ref={shellRef}
          className="bg-background p-6 text-foreground md:min-h-screen max-md:fixed max-md:inset-x-0 max-md:top-[var(--orion-viewport-top,0px)] max-md:h-[var(--orion-viewport-height,100dvh)] max-md:overflow-y-auto"
        >
          <ServerConnections />
        </div>
      );
    return (
      <main className="flex h-screen items-center justify-center bg-background text-foreground">
        <form
          onSubmit={(event) => void submitLogin(event)}
          className="flex w-full max-w-sm flex-col gap-4 rounded-lg border p-6"
        >
          <h1 className="text-2xl font-semibold">Sign in to Orion</h1>
          <label htmlFor="orion-password">Password</label>
          <input
            id="orion-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="rounded border bg-background p-2"
          />
          {auth.mfa_required && (
            <label className="space-y-1">
              <span> Mã Authenticator hoặc mã khôi phục</span>
              <input
                className="w-full rounded border bg-background p-2"
                autoComplete="one-time-code"
                value={authCode}
                onChange={(event) => setAuthCode(event.target.value)}
                required
              />
            </label>
          )}
          {authError && (
            <p role="alert" className="text-sm text-destructive">
              {authError}
            </p>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="rounded bg-primary p-2 text-primary-foreground"
          >
            Sign in
          </button>
        </form>
      </main>
    );
  }
  return (
    <QueryClientProvider client={queryClient}>
      <HeadContent />
      <ChatProvider key={serverGeneration}>
        <div
          ref={readyShellRef}
          className="grain flex h-dvh w-full flex-col overflow-hidden bg-background pt-[env(safe-area-inset-top)] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] text-foreground max-md:fixed max-md:inset-x-0 max-md:top-[var(--orion-viewport-top,0px)] max-md:h-[var(--orion-viewport-height,100dvh)] max-md:pb-[env(safe-area-inset-bottom)] md:flex-row"
        >
          <AppSidebar
            mobileFooter={
              auth.remote_access && (
                <div className="space-y-1 px-2 md:hidden">
                  {authError && (
                    <span role="alert" className="text-xs text-destructive">
                      {authError}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => void signOut()}
                    className="w-full rounded px-2.5 py-1.5 text-left text-sm hover:bg-sidebar-accent"
                  >
                    Sign out
                  </button>
                </div>
              )
            }
          />
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
            <HostUpdateNotice />
            <div className="relative flex min-h-0 min-w-0 flex-1">
              <Outlet />
            </div>
          </div>
          <CommandPalette />
          {auth.remote_access && (
            <div className="fixed bottom-16 left-3 z-50 hidden flex-col gap-1 md:flex">
              {authError && (
                <span role="alert" className="text-xs text-destructive">
                  {authError}
                </span>
              )}
              <button
                type="button"
                onClick={() => void signOut()}
                className="rounded border bg-background px-2 py-1 text-xs"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </ChatProvider>
    </QueryClientProvider>
  );
}
