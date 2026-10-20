import { type Locator, type Page, expect } from "@playwright/test";

import { ROUTE_TIMEOUT_MS, currentSiteId, waitForDraftChatRoute } from "./navigation";

export class SitePickerComponent {
  readonly switcherTrigger: Locator;

  constructor(private page: Page) {
    this.switcherTrigger = page.getByRole("button", { name: /switch site/i });
  }

  /** Pick `siteId` from the switcher and wait for the draft chat route it
   *  opens. An action taken before the route moves runs against the page the
   *  pick is about to replace. */
  async selectSite(siteId: string) {
    await this.switcherTrigger.click();
    await this.page.getByTestId(`site-menu-item-${siteId}`).click();
    await waitForDraftChatRoute(this.page);
    await this.expectCurrentSite(siteId);
  }

  async expectCurrentSite(siteId: string) {
    await expect
      .poll(() => currentSiteId(this.page), { timeout: ROUTE_TIMEOUT_MS })
      .toBe(siteId);
  }
}
