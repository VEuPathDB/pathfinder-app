import { type BrowserContext, expect } from "@playwright/test";

import { CSRF_HEADERS } from "./api-client";
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

  const notice = await context.request.patch(`${BASE_URL}/api/v1/me/privacy`, {
    data: { noticeSeen: true },
    headers: CSRF_HEADERS,
  });
  expect(notice.ok(), `eval-data notice acknowledgement ${notice.status()}`).toBe(true);
}
