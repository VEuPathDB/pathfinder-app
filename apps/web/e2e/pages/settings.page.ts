import { type Locator, type Page, expect } from "@playwright/test";

type SettingsTab = "Model" | "Data" | "Advanced" | "Seeding";

/** The class the active tab alone carries. */
const ACTIVE_TAB = /border-primary/;

export class SettingsPage {
  constructor(private page: Page) {}

  private dialog(): Locator {
    return this.page.getByRole("dialog").filter({ hasText: /settings/i });
  }

  tab(tabName: SettingsTab): Locator {
    return this.dialog().getByRole("button", { name: tabName, exact: true });
  }

  /** Open settings via the nav rail settings button. */
  async open() {
    await this.page.getByTestId("nav-rail-settings-button").click();
    await expect(this.dialog()).toBeVisible();
  }

  /** Close settings with Escape. The modal unmounts, so no dialog is left. */
  async close() {
    await this.page.keyboard.press("Escape");
    await expect(this.dialog()).toHaveCount(0);
  }

  /** Switch to a tab and wait for it to become the active one. */
  async openTab(tabName: SettingsTab) {
    await this.tab(tabName).click();
    await expect(this.tab(tabName)).toHaveClass(ACTIVE_TAB);
  }

  /** One tab is active and no other is. */
  async expectOnlyTabActive(tabName: SettingsTab) {
    for (const tab of ["Model", "Data", "Advanced", "Seeding"] as const) {
      if (tab === tabName) {
        await expect(this.tab(tab)).toHaveClass(ACTIVE_TAB);
      } else {
        await expect(this.tab(tab)).not.toHaveClass(ACTIVE_TAB);
      }
    }
  }

  async expectTabVisible(tabName: SettingsTab) {
    await expect(this.tab(tabName)).toBeVisible();
  }

  async expectAllTabsVisible() {
    for (const tab of ["Model", "Data", "Advanced", "Seeding"] as const) {
      await this.expectTabVisible(tab);
    }
  }
}
