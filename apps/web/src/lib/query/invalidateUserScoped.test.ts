import { describe, expect, it } from "vitest";
import { getMyQuotaQueryKey } from "@pathfinder/shared/generated/hooks/useGetMyQuota";
import { listDismissedStrategiesQueryKey } from "@pathfinder/shared/generated/hooks/useListDismissedStrategies";
import { listStrategiesQueryKey } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { listModelsQueryKey } from "@pathfinder/shared/generated/hooks/useListModels";

import { strategyQueryKey } from "@/lib/api/strategy";
import { authRefreshOptions, authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestQueryClient } from "@/lib/query/testing";

import { invalidateUserScopedQueries } from "./invalidateUserScoped";

const USER_SCOPED = [
  ["gene-sets", "list", "plasmodb"],
  ["strategies", "step-counts", "plasmodb", "h1"],
  listStrategiesQueryKey({ siteId: "plasmodb" }),
  listDismissedStrategiesQueryKey({ siteId: "plasmodb" }),
  getMyQuotaQueryKey(),
  strategyQueryKey("c1"),
] as const;

const SHARED = [
  authStatusOptions("plasmodb").queryKey,
  authRefreshOptions("plasmodb").queryKey,
  listModelsQueryKey(),
  ["conversations", "c1", "reattach", "t1", 0],
] as const;

describe("invalidateUserScopedQueries", () => {
  it("marks every read of the account's data stale and leaves the rest", () => {
    const client = createTestQueryClient();
    for (const key of [...USER_SCOPED, ...SHARED]) client.setQueryData(key, "cached");

    invalidateUserScopedQueries(client);

    const stale = (key: readonly unknown[]) =>
      client.getQueryState(key)?.isInvalidated ?? false;
    expect(USER_SCOPED.map(stale)).toEqual(USER_SCOPED.map(() => true));
    expect(SHARED.map(stale)).toEqual(SHARED.map(() => false));
  });
});
