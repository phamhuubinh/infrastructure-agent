import { QueryClient } from "@tanstack/react-query";
import { createMemoryHistory, createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";

let _queryClient: QueryClient | null = null;
let _router: ReturnType<typeof createRouter> | null = null;

export const getRouter = (native = false) => {
  if (_router) return _router;
  _queryClient = new QueryClient();

  _router = createRouter({
    routeTree,
    context: { queryClient: _queryClient },
    history: native ? createMemoryHistory({ initialEntries: ["/"] }) : undefined,
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return _router;
};
