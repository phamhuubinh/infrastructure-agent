import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";

let _queryClient: QueryClient | null = null;
let _router: ReturnType<typeof createRouter> | null = null;

export const getRouter = () => {
  if (_router) return _router;
  _queryClient = new QueryClient();

  _router = createRouter({
    routeTree,
    context: { queryClient: _queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return _router;
};
