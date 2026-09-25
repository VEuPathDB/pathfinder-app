import { expect } from "@playwright/test";
import { test } from "../fixtures/test";

test.describe("Settings / Memory tab", () => {
  test("Memory tab renders four namespace sections", async ({ page }) => {
    await page.goto("/conversation");

    // Wait for the chat view to settle so the nav-rail Settings button is
    // mounted with its onClick wired up.
    await expect(page.getByTestId("message-input")).toBeVisible({
      timeout: 15_000,
    });

    // Click settings, retrying click until the dialog appears (guards against
    // the React strict-mode render-during-render warning that can swallow
    // the first click on dev builds).
    const dialog = page.getByRole("dialog");
    const settingsButton = page.getByTestId("nav-rail-settings-button");
    await expect(async () => {
      await settingsButton.click();
      await expect(dialog).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 20_000 });

    // Switch to the Memory tab and verify the four sections + search field.
    await dialog.getByRole("tab", { name: "Memory", exact: true }).click();

    await expect(dialog.getByRole("button", { name: /Gene sets/i })).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Strategies/i })).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Preferences/i })).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Knowledge/i })).toBeVisible();

    await expect(dialog.getByPlaceholder(/search memories/i)).toBeVisible();
  });
});
