import { type BrowserContext, expect } from "@playwright/test";

import { continuePastDataNotice } from "./api-client";
import { BASE_URL, addWebsiteLogin } from "./test";

export async function signInAsWdkAccount(context: BrowserContext): Promise<void> {
  await addWebsiteLogin(context);

  const notice = await continuePastDataNotice(context.request, BASE_URL);
  expect(notice.ok(), `data notice ${notice.status()}`).toBe(true);
}
