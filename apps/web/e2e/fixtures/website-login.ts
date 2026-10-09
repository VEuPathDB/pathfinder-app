import { type BrowserContext, expect } from "@playwright/test";

import { CSRF_HEADERS, continuePastDataNotice } from "./api-client";
import { BASE_URL, addWebsiteLogin } from "./test";

export async function signInAsWdkAccount(
  context: BrowserContext,
  siteId: string,
): Promise<void> {
  await context.clearCookies({ name: "pathfinder-auth" });
  await addWebsiteLogin(context);

  const refreshed = await context.request.post(
    `${BASE_URL}/api/v1/veupathdb/auth/refresh`,
    { params: { siteId }, headers: CSRF_HEADERS },
  );
  expect(refreshed.ok(), `session refresh ${refreshed.status()}`).toBe(true);

  const notice = await continuePastDataNotice(context.request, BASE_URL);
  expect(notice.ok(), `data notice ${notice.status()}`).toBe(true);
}
