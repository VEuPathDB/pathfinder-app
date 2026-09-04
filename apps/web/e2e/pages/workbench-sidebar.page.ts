import { type Locator, type Page, expect } from "@playwright/test";

export class WorkbenchSidebarPage {
  readonly addButton: Locator;

  constructor(private page: Page) {
    this.addButton = page.getByRole("button", { name: /add/i });
  }

  /** Navigate to the workbench, preserving the currently-selected site so
   *  gene sets are created on the site the test already switched to. */
  async goto() {
    const currentSite = new URL(this.page.url()).pathname.split("/")[1];
    const path =
      currentSite != null && currentSite !== ""
        ? `/${currentSite}/workbench`
        : "/workbench";
    await this.page.goto(path);
    await expect(this.page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
  }

  /** Click the "Add" button to open the Add Gene Set modal. */
  async openAddModal() {
    await this.addButton.click();
    await expect(this.page.getByRole("dialog")).toBeVisible();
  }

  /** Get the filter input (visible at 5+ sets). */
  get filterInput(): Locator {
    return this.page.getByPlaceholder(/filter/i);
  }

  async filterSets(query: string) {
    await this.filterInput.fill(query);
  }

  /** Activate a gene set by clicking its name.
   *  The card's name span carries the set name as its title, so a derived set
   *  whose name contains this one does not match. */
  async activateSet(name: string) {
    await this.page
      .getByRole("button")
      .filter({ has: this.page.locator(`span[title="${name}"]`) })
      .click();
  }

  /** Select a gene set checkbox. */
  async selectSet(name: string) {
    await this.page
      .getByRole("checkbox", { name: new RegExp(`select ${name}`, "i") })
      .check();
  }

  /** Perform a compose bar set operation (union/intersect/minus).
   *  Selects the operation type, then clicks "Create" to execute. */
  async performOperation(operation: "union" | "intersect" | "minus") {
    await this.page.getByRole("button", { name: new RegExp(operation, "i") }).click();

    const createBtn = this.page.getByRole("button", { name: /create/i });
    await expect(createBtn).toBeEnabled();
    await createBtn.click();
  }

  // ── Assertions ─────────────────────────────────────────────────

  async expectSetCount(count: number) {
    const checkboxes = this.page.getByRole("checkbox", {
      name: /select/i,
    });
    await expect(checkboxes).toHaveCount(count);
  }

  /** Verify a gene set card shows a specific gene count number. */
  async expectSetGeneCount(name: string, count: number) {
    const card = this.page.getByRole("button").filter({ hasText: name }).locator("..");
    await expect(card.getByText(count.toLocaleString(), { exact: true })).toBeVisible();
  }

  /** Verify the compose bar shows expected result count before creating.
   *  The main panel names its own gene count, so the read is scoped to the
   *  sidebar that owns the compose zone. */
  async expectComposeResultCount(count: number) {
    const composeSidebar = this.page
      .getByRole("complementary")
      .filter({ has: this.page.getByText("Compose", { exact: true }) });
    await expect(
      composeSidebar.getByText(
        new RegExp(`^${count.toLocaleString()}\\s+genes?$`, "i"),
      ),
    ).toBeVisible({ timeout: 10_000 });
  }

  async expectEmptyState() {
    await expect(this.page.getByText(/no gene sets yet/i)).toBeVisible();
  }
}
