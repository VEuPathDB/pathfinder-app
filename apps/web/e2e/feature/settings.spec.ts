import { test } from "../fixtures/test";

/** Moving between the Settings tabs by pointer and by keyboard. */
test.describe("Settings", () => {
  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
  });

  test("switch between settings tabs", async ({ settingsPage }) => {
    await settingsPage.open();

    for (const tab of ["Data", "Advanced", "Seeding", "Model"] as const) {
      await settingsPage.openTab(tab);
      await settingsPage.expectOnlyTabActive(tab);
    }
  });

  test("arrow keys, Home and End move between settings tabs", async ({
    page,
    settingsPage,
  }) => {
    await settingsPage.open();
    await settingsPage.openTab("Advanced");

    await page.keyboard.press("ArrowRight");
    await settingsPage.expectOnlyTabActive("Seeding");
    await page.keyboard.press("Home");
    await settingsPage.expectOnlyTabActive("Model");
    await page.keyboard.press("End");
    await settingsPage.expectOnlyTabActive("Seeding");
  });
});
