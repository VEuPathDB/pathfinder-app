import { QueryCache, QueryClient } from "@tanstack/react-query";

import { siteUnavailableRefusal, wdkAuthRefusal } from "@/lib/api/errors";
import { APIError } from "@/lib/api/http";
import { AppError } from "@/lib/errors/AppError";
import { listModelsQueryKey } from "@pathfinder/shared/generated/hooks/useListModels";

/** What a query tells the global error handler about its own error. */
type AppQueryMeta = {
  /** The error reaches no handler, the VEuPathDB sign-in prompt included. */
  silent?: boolean;
  /** The component shows the error, so only a VEuPathDB account refusal is forwarded. */
  shownInline?: boolean;
};

declare module "@tanstack/react-query" {
  interface Register {
    queryMeta: AppQueryMeta;
  }
}

export interface QueryErrorNotice {
  message: string;
  queryKey: readonly unknown[];
  error: unknown;
  /** Run the query again, for a handler that repaired what refused it. */
  retry: () => void;
}

type NoticeHandler = (notice: QueryErrorNotice) => void;

let handler: NoticeHandler | null = null;

export function setQueryErrorHandler(next: NoticeHandler | null): void {
  handler = next;
}

function extractMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message || fallback;
  return fallback;
}

function makeQueryClient(): QueryClient {
  const client = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.meta?.silent === true) return;
        // A refusal about the VEuPathDB account is the one 401 the user can act on.
        const actionable = wdkAuthRefusal(error) !== null;
        if (!actionable && query.meta?.shownInline === true) return;
        if (!actionable && error instanceof APIError && error.status === 401) return;
        const message = extractMessage(error, "Request failed");
        const retry = (): void => {
          void query.fetch().catch(() => {});
        };
        handler?.({ message, queryKey: query.queryKey, error, retry });
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: (failureCount, error) => {
          // A timeout or a down site gives the same answer at once. The shell asks again later.
          if (error instanceof AppError && error.code === "TIMEOUT") return false;
          if (siteUnavailableRefusal(error) !== null) return false;
          if (error instanceof APIError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return failureCount < 2;
        },
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
      },
      mutations: {
        retry: false,
      },
    },
  });
  client.setQueryDefaults(listModelsQueryKey(), { staleTime: Infinity });
  return client;
}

let browserQueryClient: QueryClient | undefined;

export function __makeQueryClientForTests(): QueryClient {
  return makeQueryClient();
}

export function getQueryClient(): QueryClient {
  if (typeof window === "undefined") {
    return makeQueryClient();
  }
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}
