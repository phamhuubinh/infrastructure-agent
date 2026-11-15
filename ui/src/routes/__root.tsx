import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
} from "@tanstack/react-router";
import { useEffect, useState, type FormEvent } from "react";

import { AppSidebar } from "@/components/AppSidebar";
import { CommandPalette } from "@/components/CommandPalette";
import { ChatProvider } from "@/lib/chat-store";
import { AUTH_EXPIRED_EVENT, getAuthSession, login, logout, type AuthSession } from "@/lib/api";
import { SERVER_CHANGED_EVENT, isNativeHost } from "@/lib/server-profiles";
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
      { name: "viewport", content: "width=device-width, initial-scale=1" },
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
  const { queryClient } = Route.useRouteContext();
  useTheme();
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [authError, setAuthError] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [serverGeneration, setServerGeneration] = useState(0);
  useEffect(() => {
    const changed = () => {
      queryClient.clear();
      setAuth(null);
      setPassword("");
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
      await login(password);
      setPassword("");
      setAuth(await getAuthSession());
    } catch {
      setAuthError("Invalid password or login temporarily unavailable.");
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
      <main className="min-h-screen bg-background text-foreground p-6 space-y-4">
        <p role="status">{authError || "Loading Orion…"}</p>
        {authError && <ServerConnections />}
      </main>
    );
  if (auth.remote_access && !auth.authenticated) {
    if (isNativeHost())
      return (
        <main className="min-h-screen bg-background text-foreground p-6">
          <ServerConnections />
        </main>
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
        <div className="flex h-dvh w-full overflow-hidden bg-background text-foreground grain pt-[env(safe-area-inset-top)] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)]">
          <AppSidebar />
          <div className="flex-1 min-w-0 flex pb-14 md:pb-0">
            <Outlet />
          </div>
          <CommandPalette />
          <nav
            aria-label="Điều hướng mobile"
            className="fixed bottom-0 inset-x-0 z-40 grid grid-cols-5 border-t bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
          >
            {(
              [
                { to: "/", label: "Chat" },
                { to: "/projects", label: "Projects" },
                { to: "/endpoints", label: "Remote" },
                { to: "/commands", label: "Commands" },
                { to: "/settings", label: "Settings" },
              ] as const
            ).map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="flex min-h-12 items-center justify-center px-1 text-xs focus-visible:outline focus-visible:outline-2"
                activeProps={{ className: "font-semibold bg-accent" }}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          {auth.remote_access && (
            <div className="fixed bottom-16 left-3 z-50 flex flex-col gap-1">
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
