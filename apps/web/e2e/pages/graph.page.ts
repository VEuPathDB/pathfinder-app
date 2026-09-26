import { type Locator, type Page, expect, test } from "@playwright/test";

import { ROUTE_TIMEOUT_MS } from "./navigation";

/**
 * Wall clock a build turn needs before the rail can list its steps.
 *
 * The rail panel appears on the `data-graph-snapshot` chunk, so the bound is
 * the turn's own duration plus the time it waits for a free worker slot.
 * Measured build turns run 12 s to 30 s across sites, and a turn queued behind
 * another adds about as much again. A budget only costs wall clock when the
 * assertion fails.
 */
const BUILD_TURN_BUDGET_MS = 180_000;

/**
 * Page object for the strategy graph + step editor surfaces.
 *
 * Targets the post-overhaul UI:
 * - Read-only rail panel on `/conversation/[id]` with an "Open" button
 * - Full-page editor at `/conversation/[id]/strategy` with a CanvasTopbar +
 *   CanvasControls + SelectionActionBar
 * - Right-anchored Sheet step editor (auto-saves; no Save button)
 * - Combine creation by drag -> INTERSECT default -> Sheet opens with venn picker
 */
export class GraphPage {
  constructor(private page: Page) {}

  private buildBudgetGranted = false;

  // Rail panel (read-only step list on /conversation/[id])
  /** The vertical step list panel rendered in the right rail. */
  get railPanel(): Locator {
    return this.page.getByTestId("rail-strategy-panel");
  }

  /** The "Open" button in the rail header that navigates to /strategy. */
  get railOpenButton(): Locator {
    return this.page.getByTestId("rail-strategy-open");
  }

  /** All clickable step rows inside the compact view in the rail. */
  get railStepRows(): Locator {
    return this.page
      .getByTestId("compact-strategy-view")
      .locator("[data-testid^='compact-step-row-']");
  }

  /**
   * Resolve the topologically-first rail row's step id once the rail panel
   * has rendered. Prefer this helper over `.first()` so the spec layer
   * remains free of strict-mode escape hatches.
   */
  async firstRailStepId(timeout = 30_000): Promise<string> {
    await expect.poll(() => this.railStepRows.count(), { timeout }).toBeGreaterThan(0);
    const idList = await this.railStepRows.evaluateAll((rows) =>
      rows.map((r) => r.getAttribute("data-testid") ?? ""),
    );
    const first = idList[0] ?? "";
    return first.replace(/^compact-step-row-/, "");
  }

  /** Bounding box of the topologically-first canvas node. */
  async firstNodeBoundingBox(): Promise<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null> {
    return this.nodes.evaluateAll((els) => {
      const first = els[0];
      if (first == null) return null;
      const rect = first.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    });
  }

  /** Text content of the topologically-first rail step row. */
  async firstRailStepText(): Promise<string> {
    return this.railStepRows.evaluateAll((rows) => rows[0]?.textContent ?? "");
  }

  /** A specific step row in the rail by step id. */
  railStepRow(stepId: string): Locator {
    return this.page.getByTestId(`compact-step-row-${stepId}`);
  }

  /** Footer row with "N steps". */
  get railFooter(): Locator {
    return this.page.getByTestId("rail-strategy-footer");
  }

  /**
   * Bring the rail's Strategy panel on screen.
   *
   * The rail auto-opens Progress on the thread's first user message, so the
   * Strategy toggle reads "Open Strategy" until a spec clicks it.
   */
  async openRailStrategyPanel() {
    await this.showRailStrategy();
    await this.expectRailPanel();
  }

  /** Bring the rail's Strategy panel on screen, with steps or without. */
  async showRailStrategy() {
    // The rail mounts with the conversation, so a page still rendering is not
    // read as one whose panel is already open.
    await expect(this.page.getByTestId("message-composer")).toBeVisible({
      timeout: ROUTE_TIMEOUT_MS,
    });
    const open = this.page.getByRole("button", { name: "Open Strategy", exact: true });
    if ((await open.count()) > 0) {
      await open.click();
    }
  }

  /** The Strategy panel's heading when the conversation holds no strategy. */
  get railEmptyHeading(): Locator {
    return this.page.getByText("No strategy built yet", { exact: true });
  }

  /** How many step rows the rail lists, once it lists any. */
  async railStepCount(): Promise<number> {
    await expect
      .poll(() => this.railStepRows.count(), { timeout: 60_000 })
      .toBeGreaterThan(0);
    return this.railStepRows.count();
  }

  // Strategy page chrome (/conversation/[id]/strategy)
  /** The CanvasTopbar mounted on the /strategy route. */
  get strategyPageTopbar(): Locator {
    return this.page.getByTestId("canvas-topbar");
  }

  /** "Back to conversation" button in the canvas topbar. */
  get strategyPageBackButton(): Locator {
    return this.page.getByTestId("canvas-topbar-back");
  }

  /** Step count text in the canvas topbar. */
  get strategyPageStepCount(): Locator {
    return this.page.getByTestId("canvas-topbar-step-count");
  }

  /** Sync state pill in the canvas topbar (idle/saving/error). */
  get strategyPageSyncState(): Locator {
    return this.page.getByTestId("canvas-topbar-sync-state");
  }

  /** Inline-editable strategy name input in the canvas topbar. */
  get strategyPageNameInput(): Locator {
    return this.page.getByLabel("Strategy name");
  }

  /** Floating canvas controls (relayout/fit/zoom) bottom-right. */
  get canvasControls(): Locator {
    return this.page.getByTestId("canvas-controls");
  }

  /** Contextual selection action bar (top-right; visible when ≥1 node selected). */
  get selectionActionBar(): Locator {
    return this.page.getByTestId("selection-action-bar");
  }

  /** Validation alert banner shown when the strategy has record-type mismatches. */
  get validationAlert(): Locator {
    return this.page.getByTestId("validation-alert");
  }

  // Editor Sheet (right-anchored, opens on step click)
  /** The Sheet container (Radix Dialog) with the step editor inside. */
  get editorSheet(): Locator {
    return this.page.getByTestId("step-editor-sheet");
  }

  /** Editor footer (sync status + result count + WDK link). */
  get editorFooter(): Locator {
    return this.page.getByTestId("step-editor-footer");
  }

  /** Editor sync state indicator (data-sync-state="idle|saving|error"). */
  get editorSyncState(): Locator {
    return this.page.getByTestId("step-editor-sync-state");
  }

  /** Inline-editable step name input in the editor sheet header. */
  get editorStepNameInput(): Locator {
    return this.editorSheet.getByLabel("Step name");
  }

  // Edge context menu
  /** Operator grid inside the edge context menu (Popover). */
  get edgeContextMenuOperatorGrid(): Locator {
    return this.page.getByTestId("edge-context-menu-operator-grid");
  }

  // ReactFlow nodes (canvas)
  /** All strategy graph nodes in the ReactFlow canvas. */
  get nodes(): Locator {
    return this.page.locator("[data-testid^='rf-node-']");
  }

  node(stepId: string): Locator {
    return this.page.getByTestId(`rf-node-${stepId}`);
  }

  async clickNode(stepId: string) {
    await this.node(stepId).click();
  }

  async deleteStep(stepId: string) {
    await this.node(stepId).hover();
    await this.page.getByTestId(`rf-more-${stepId}`).click();
    await this.page.getByRole("menuitem", { name: "Delete step" }).click();
    const dialog = this.page.getByTestId("graph-action-confirm");
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    // The kebab delete must not open the editor sheet (its overlay would block
    // the confirm dialog).
    await expect(this.editorSheet).toBeHidden({ timeout: 5_000 });
    await this.page.getByTestId("graph-action-confirm-apply").click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
  }

  async expandEditorAdvanced() {
    const trigger = this.editorSheet.getByRole("button", {
      name: /Advanced Parameters/,
    });
    if (await trigger.isVisible().catch(() => false)) {
      await trigger.click();
    }
  }

  async toggleEditorCheckbox(label: string) {
    await this.editorSheet.getByRole("checkbox", { name: label }).click();
  }

  async saveEditor() {
    await this.editorSheet.getByTestId("step-editor-save").click();
    await expect(this.editorSyncState).toHaveAttribute("data-sync-state", "idle", {
      timeout: 30_000,
    });
    await this.editorSheet.getByRole("button", { name: "Close" }).click();
    await expect(this.editorSheet).toBeHidden({ timeout: 10_000 });
  }

  /**
   * Save the editor and wait up to 60 s for the save to settle. A save the
   * site refuses or lets time out ends in "Save failed"; the answer says which.
   */
  async saveEditorOrSiteRefusal(): Promise<"saved" | "site-refused"> {
    await this.editorSheet.getByTestId("step-editor-save").click();
    await expect(this.editorSyncState).not.toHaveAttribute(
      "data-sync-state",
      "saving",
      {
        timeout: 60_000,
      },
    );
    if ((await this.editorSyncState.getAttribute("data-sync-state")) === "error") {
      await expect(this.editorSyncState).toHaveText("Save failed");
      return "site-refused";
    }
    await expect(this.editorSyncState).toHaveAttribute("data-sync-state", "idle");
    await this.editorSheet.getByRole("button", { name: "Close" }).click();
    await expect(this.editorSheet).toBeHidden({ timeout: 10_000 });
    return "saved";
  }

  primaryEdgeInto(targetStepId: string): Locator {
    return this.page.locator(
      `[data-testid^='step-edge-hit-'][data-testid$='-${targetStepId}-primary']`,
    );
  }

  async openEdgeMenu(targetStepId: string) {
    const edge = this.primaryEdgeInto(targetStepId);
    // A step has one primary input, so the hit area settles at one element.
    await expect(edge).toHaveCount(1, { timeout: 10_000 });
    await edge.click();
    await expect(this.edgeContextMenuOperatorGrid).toBeVisible({
      timeout: 5_000,
    });
  }

  async changeOperator(
    targetStepId: string,
    op: "UNION" | "INTERSECT" | "MINUS" | "RMINUS",
  ) {
    await this.openEdgeMenu(targetStepId);
    const labelByOp: Record<typeof op, string> = {
      UNION: "Set operator to Union",
      INTERSECT: "Set operator to Intersect",
      MINUS: "Set operator to Minus",
      RMINUS: "Set operator to Right minus",
    };
    await this.edgeContextMenuOperatorGrid
      .getByRole("menuitemradio", { name: labelByOp[op] })
      .click();
  }

  // Navigation helpers
  /** Navigate directly to the strategy editor route for a conversation. */
  async goToStrategy(siteId: string, conversationId: string) {
    await this.page.goto(`/${siteId}/conversation/${conversationId}/strategy`);
    await this.expectOnStrategyRoute(conversationId);
  }

  async expectOnStrategyRoute(conversationId: string) {
    await expect(this.page).toHaveURL(
      new RegExp(`/conversation/${conversationId}/strategy(?:/|$)`),
      { timeout: ROUTE_TIMEOUT_MS },
    );
  }

  async expectOnChatRoute(conversationId: string) {
    await expect(this.page).toHaveURL(
      new RegExp(`/conversation/${conversationId}(?:\\?.*)?$`),
      { timeout: ROUTE_TIMEOUT_MS },
    );
  }

  // Compound assertions
  /**
   * Assert the rail panel with steps is visible (planning artifact applied).
   *
   * A test that waits on a build turn carries that turn's budget on top of its
   * own. The grant is made once per test.
   */
  async expectRailPanel() {
    if (!this.buildBudgetGranted) {
      this.buildBudgetGranted = true;
      test.setTimeout(test.info().timeout + BUILD_TURN_BUDGET_MS);
    }
    await expect(this.railPanel).toBeVisible({ timeout: BUILD_TURN_BUDGET_MS });
  }

  async expectStrategyTopbar() {
    await expect(this.strategyPageTopbar).toBeVisible({ timeout: 15_000 });
  }

  async expectEditorSheetOpen() {
    await expect(this.editorSheet).toBeVisible({ timeout: 10_000 });
  }

  async expectEditorSheetClosed() {
    await expect(this.editorSheet).toBeHidden({ timeout: 10_000 });
  }

  async expectNodeCount(count: number) {
    await expect(this.nodes).toHaveCount(count, { timeout: 30_000 });
  }

  async expectNodeVisible(stepId: string) {
    await expect(this.node(stepId)).toBeVisible({ timeout: 10_000 });
  }
}
