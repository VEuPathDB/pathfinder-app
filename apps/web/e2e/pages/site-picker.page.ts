import { type Locator, type Page, expect } from "@playwright/test";

import { ROUTE_TIMEOUT_MS } from "./navigation";

export class SitePickerComponent {
  readonly switcherTrigger: Locator;

  constructor(private page: Page) {
    this.switcherTrigger = page.getByRole("button", { name: /switch site/i });
  }

  /** Switch to `siteId` and wait for the router to put it in the URL. Picking
   *  a site pushes a new route, so an action taken before the URL moves runs
   *  against the page the switch is about to replace. */
  async selectSite(siteId: string) {
    await this.switcherTrigger.click();
    await this.page.getByTestId(`site-menu-item-${siteId}`).click();
    await this.expectCurrentSite(siteId);
  }

  async expectCurrentSite(siteId: string) {
    // The active site lives in the URL (`/{siteId}/...`) now, not a <select>.
    await expect(this.page).toHaveURL(new RegExp(`/${siteId}(/|$)`), {
      timeout: ROUTE_TIMEOUT_MS,
    });
  }
}
