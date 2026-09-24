import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { QueryErrorToasts } from "@/app/components/QueryErrorToasts";
import { __makeQueryClientForTests } from "@/lib/query/client";

/** The app's own query client with retries off, since a retry only delays the error. */
export function appTestQueryClient(): QueryClient {
  const client = __makeQueryClientForTests();
  const defaults = client.getDefaultOptions();
  client.setDefaultOptions({
    ...defaults,
    queries: { ...defaults.queries, retry: false },
  });
  return client;
}

/**
 * A render wrapper with the app's own query client and its error toasts, so a
 * test counts every toast a failed query raises.
 */
export function appQueryClientWrapper(
  client: QueryClient = appTestQueryClient(),
): (props: { children: ReactNode }) => ReactNode {
  function AppQueryClientWrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <QueryErrorToasts />
        {children}
      </QueryClientProvider>
    );
  }
  return AppQueryClientWrapper;
}
