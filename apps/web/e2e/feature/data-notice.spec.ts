import type { Browser, BrowserContext } from "@playwright/test";

import { CSRF_HEADERS } from "../fixtures/api-client";
import {
  BASE_URL,
  DEFAULT_SITE,
  addWebsiteLogin,
  expect,
  test,
} from "../fixtures/test";

async function newResearcher(browser: Browser): Promise<BrowserContext> {
  const context = await browser.newContext({
    storageState: { cookies: [], origins: [] },
  });
  await addWebsiteLogin(context);
  const login = await context.request.post(
    `${BASE_URL}/api/v1/dev/login?user_id=data-notice-${Date.now()}`,
    { headers: CSRF_HEADERS },
  );
  expect(login.ok(), `dev login ${login.status()}`).toBe(true);
  return context;
}

test.describe("The data notice at first sign-in", () => {
  test("shows once, and Continue with the box unticked turns learning off", async ({
    browser,
  }) => {
    test.setTimeout(180_000);
    const context = await newResearcher(browser);
    const page = await context.newPage();
    await page.goto(`${BASE_URL}/${DEFAULT_SITE}/conversation`);

    const notice = page.getByRole("alertdialog", { name: "Your data in PathFinder" });
    await expect(notice).toBeVisible({ timeout: 60_000 });
    await expect(
      notice.getByRole("link", { name: "Read the full statement" }),
    ).toHaveAttribute("target", "_blank");
    const learn = notice.getByRole("checkbox", {
      name: "Let PathFinder learn from my strategies",
    });
    await expect(learn).toBeChecked();
    await page.keyboard.press("Escape");
    await expect(notice).toBeVisible();

    await learn.click();
    await expect(learn).not.toBeChecked();
    await notice.getByRole("button", { name: "Continue" }).click();
    await expect(notice).toHaveCount(0);

    const privacy = await context.request.get(`${BASE_URL}/api/v1/me/privacy`);
    expect(await privacy.json()).toEqual({
      evalDataConsent: false,
      dataNoticeSeen: "2026-10-09",
      noticeDue: false,
    });

    await page.reload();
    await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 60_000 });
    await expect(notice).toHaveCount(0);
    await context.close();
  });
});
