import { test } from "../fixtures/test";

test.describe("Settings", () => {
  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
  });

  test("open settings shows all tabs", async ({ settingsPage }) => {
    await settingsPage.open();
    await settingsPage.expectAllTabsVisible();
  });

  test("switch between settings tabs", async ({ settingsPage }) => {
    await settingsPage.open();

    for (const tab of ["Data", "Advanced", "Seeding", "Model"] as const) {
      await settingsPage.openTab(tab);
      await settingsPage.expectOnlyTabActive(tab);
    }
  });

  test("close settings modal", async ({ settingsPage }) => {
    await settingsPage.open();
    await settingsPage.close();

    await settingsPage.open();
    await settingsPage.expectAllTabsVisible();
  });
});
