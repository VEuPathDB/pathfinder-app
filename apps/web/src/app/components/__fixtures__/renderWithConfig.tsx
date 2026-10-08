import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { systemConfigQueryOptions } from "@pathfinder/shared/generated/hooks/useSystemConfig";
import type { SystemConfigResponse } from "@pathfinder/shared/generated/types/SystemConfigResponse";

import { createTestWrapper } from "@/lib/query/testing";

export const SITE_SIGN_IN_URL =
  "https://muharram.veupathdb.org/eupathdb.amuharram/app/user/login";

export function renderWithConfig(ui: ReactElement): RenderResult {
  const { queryClient, Wrapper } = createTestWrapper();
  const { queryKey } = systemConfigQueryOptions();
  const config: SystemConfigResponse = {
    chatProvider: "mock",
    llmConfigured: true,
    providers: { openai: false, anthropic: false, google: false, ollama: false },
    siteId: "veupathdb",
    siteSignInUrl: SITE_SIGN_IN_URL,
  };
  queryClient.setQueryDefaults(queryKey, { staleTime: Infinity });
  queryClient.setQueryData(queryKey, config);
  return render(ui, { wrapper: Wrapper });
}
