import { type Locator, type Page, expect } from "@playwright/test";

import { waitForConversationRoute, waitForDraftChatRoute } from "./navigation";

export class SidebarPage {
  readonly refreshButton: Locator;
  readonly newButton: Locator;
  readonly searchInput: Locator;

  constructor(private page: Page) {
    this.refreshButton = page.getByTestId("conversations-refresh-button");
    this.newButton = page.getByTestId("conversations-new-button");
    this.searchInput = page.getByTestId("conversations-search-input");
  }

  /** All conversation items in the sidebar. */
  get items(): Locator {
    return this.page.getByTestId("conversation-item");
  }

  /** A specific conversation by its data-conversation-id attribute. */
  item(conversationId: string): Locator {
    return this.page.locator(
      `[data-testid="conversation-item"][data-conversation-id="${conversationId}"]`,
    );
  }

  /** Open a fresh draft chat and wait for the router to drop the previous
   *  conversation id from the URL. A send() before the URL moves posts into
   *  the previous conversation. */
  async createNew() {
    await this.newButton.click();
    await waitForDraftChatRoute(this.page);
  }

  async search(query: string) {
    await this.searchInput.fill(query);
  }

  async clearSearch() {
    await this.searchInput.clear();
  }

  /** Open one conversation and wait for the router to put its id in the URL. */
  async selectConversation(conversationId: string) {
    await this.item(conversationId).click();
    await waitForConversationRoute(this.page, conversationId);
  }

  /** Open the dropdown menu on a conversation item via the "..." button. */
  private async openMenu(conversationId: string) {
    // Hover to reveal the overflow menu button, then click it
    await this.item(conversationId).hover();
    await this.item(conversationId)
      .getByRole("button", { name: /conversation actions/i })
      .click();
  }

  async rename(conversationId: string, newName: string) {
    await this.openMenu(conversationId);
    await this.page.getByRole("menuitem", { name: /rename/i }).click();
    const renameInput = this.page.getByTestId("conversation-rename-input");
    await renameInput.clear();
    await renameInput.fill(newName);
    await renameInput.press("Enter");
  }

  async delete(conversationId: string) {
    await this.openMenu(conversationId);
    await this.page.getByRole("menuitem", { name: /delete/i }).click();
    // Confirm in the delete modal
    await this.page
      .getByRole("dialog")
      .getByRole("button", { name: /delete/i })
      .click();
  }

  async refresh() {
    await this.refreshButton.click();
  }

  /** Assert at least one conversation item is rendered. */
  async expectAtLeastOneConversation(timeout = 15_000) {
    await expect.poll(() => this.items.count(), { timeout }).toBeGreaterThan(0);
  }

  async expectConversationName(conversationId: string, name: string | RegExp) {
    const pattern = typeof name === "string" ? new RegExp(name) : name;
    await expect(this.item(conversationId)).toContainText(pattern);
  }

  /** Get the first conversation item's data-conversation-id. */
  async firstConversationId(): Promise<string> {
    await expect.poll(() => this.items.count(), { timeout: 15_000 }).toBeGreaterThan(0);
    const ids = await this.items.evaluateAll((rows) =>
      rows.map((row) => row.getAttribute("data-conversation-id") ?? ""),
    );
    return ids[0] ?? "";
  }

  // ── Dismissed section ──────────────────────────────────────────

  /** The "Dismissed (N)" toggle button. */
  get dismissedToggle(): Locator {
    return this.page.getByTestId("dismissed-toggle");
  }

  /** All dismissed items inside the expanded dismissed section. */
  get dismissedItems(): Locator {
    return this.page.getByTestId("dismissed-item");
  }

  /** A specific dismissed item by its data-conversation-id attribute. */
  dismissedItem(conversationId: string): Locator {
    return this.page.locator(
      `[data-testid="dismissed-item"][data-conversation-id="${conversationId}"]`,
    );
  }

  /** Expand the dismissed section (idempotent — no-op if already expanded). */
  async expandDismissed() {
    await expect(this.dismissedToggle).toBeVisible({ timeout: 15_000 });
    // The rows are in the DOM only while the section is open, so their count
    // says whether the toggle still has to be clicked.
    if ((await this.dismissedItems.count()) === 0) {
      await this.dismissedToggle.click();
    }
    await expect(this.dismissedItems).not.toHaveCount(0, { timeout: 5_000 });
  }

  /** Click the Restore button on a specific dismissed item. */
  async restoreDismissed(conversationId: string) {
    const item = this.dismissedItem(conversationId);
    await expect(item).toBeVisible({ timeout: 10_000 });
    await item.getByTestId("dismissed-restore-button").click();
  }

  /** Assert the dismissed toggle shows the expected count. */
  async expectDismissedCount(count: number) {
    await expect(this.dismissedToggle).toContainText(`Dismissed (${count})`, {
      timeout: 15_000,
    });
  }

  /** Assert the dismissed toggle is not visible (no dismissed items). */
  async expectNoDismissedSection() {
    await expect(this.dismissedToggle).not.toBeVisible({ timeout: 10_000 });
  }

  /** Assert a dismissed item is visible (section must be expanded). */
  async expectDismissedItemVisible(conversationId: string) {
    await expect(this.dismissedItem(conversationId)).toBeVisible({
      timeout: 10_000,
    });
  }
}
