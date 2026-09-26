import type { Page } from "@playwright/test";

import { BASE_URL, test, expect } from "../fixtures/test";
import { entrySiteId } from "../fixtures/entry-site";
import { listConversations } from "../fixtures/api-client";
import { currentSiteId } from "../pages/navigation";

const SIGNED_OUT_STATUS = { signedIn: false, name: null, email: null };

/** The signed-in shell: no sign-in dialog over the app, composer ready. */
async function expectSignedIn(page: Page) {
  await expect(
    page.getByRole("dialog").filter({ hasText: /sign in/i }),
  ).not.toBeVisible();
  await expect(page.getByTestId("message-composer")).toBeVisible();
}

test.describe("VEuPathDB login gate", () => {
  test("an embedded session with no VEuPathDB login cannot send and is offered sign-in", async ({
    page,
    context,
  }) => {
    const siteId = await entrySiteId(context, BASE_URL);
    // The auth-status route is the gate under test; the rest of the app is real.
    await page.route("**/api/v1/veupathdb/auth/status*", (route) =>
      route.fulfill({ json: SIGNED_OUT_STATUS }),
    );
    await page.goto(`${BASE_URL}/${siteId}/conversation?embedded=true`);

    const prompt = page.getByTestId("veupathdb-signin-required");
    await expect(prompt).toBeVisible({ timeout: 20_000 });
    await expect(prompt).toContainText("Sign in to VEuPathDB to build strategies");
    await expect(page.getByTestId("message-input")).toBeDisabled();
    await expect(page.getByTestId("send-button")).toBeDisabled();

    await prompt.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("the postcondition API client carries both the PathFinder and the VEuPathDB cookie", async ({
    chatPage,
    apiClient,
  }) => {
    await chatPage.goto();

    const cookieNames = (await apiClient.storageState()).cookies.map((c) => c.name);
    expect(cookieNames).toContain("pathfinder-auth");
    expect(cookieNames).toContain("Authorization");

    // Both cookies together are what a WDK-backed route needs.
    const geneSets = await apiClient.get("/api/v1/gene-sets");
    expect(geneSets.status()).toBe(200);
  });
});

test.describe("Auth", () => {
  test("authenticated state shows full UI with working API access", async ({
    chatPage,
    page,
    context,
    sitePicker,
    settingsPage,
    apiClient,
    siteId,
  }) => {
    await chatPage.goto();

    // UI: Signed in - no login modal, composer visible
    await expectSignedIn(page);

    // UI: Site picker shows the site the entry flow chose
    await sitePicker.expectCurrentSite(await entrySiteId(context, BASE_URL));

    // UI: Settings accessible with all tabs
    await settingsPage.open();
    await settingsPage.expectAllTabsVisible();
    await settingsPage.close();

    // API postcondition: real endpoints work
    const strategiesResp = await apiClient.get("/api/v1/conversations");
    expect(strategiesResp.ok()).toBeTruthy();

    const sitesResp = await apiClient.get("/api/v1/sites");
    expect(sitesResp.ok()).toBeTruthy();
    const sites = await sitesResp.json();
    expect(sites.length).toBeGreaterThan(0);
    const siteIds = sites.map((s: { id: string }) => s.id);
    expect(siteIds).toContain(siteId);

    const modelsResp = await apiClient.get("/api/v1/models");
    expect(modelsResp.ok()).toBeTruthy();
    const models = await modelsResp.json();
    expect(models.defaultProvider).toBeTruthy();
  });

  test("page reload preserves session - UI and API intact", async ({
    chatPage,
    sidebarPage,
    page,
    apiClient,
  }) => {
    await chatPage.goto();
    await chatPage.newChat();

    // Send a message to create state.
    await chatPage.send("show me kinase genes");
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await chatPage.expectIdle();

    // Verify sidebar shows conversation
    await sidebarPage.expectAtLeastOneConversation();

    // API: get strategy count before reload
    const siteId = currentSiteId(page);
    const beforeCount = (await listConversations(apiClient, siteId)).length;

    // Reload
    await page.reload();
    await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 15_000 });

    // UI: Still signed in - composer visible, message still there
    await expectSignedIn(page);
    await expect(
      page.locator(".is-user").filter({ hasText: "show me kinase genes" }),
    ).toBeVisible({ timeout: 15_000 });

    // UI: Sidebar still shows conversations
    await sidebarPage.expectAtLeastOneConversation();

    // API: Same strategy count - no data loss
    expect(await listConversations(apiClient, siteId)).toHaveLength(beforeCount);
  });
});
