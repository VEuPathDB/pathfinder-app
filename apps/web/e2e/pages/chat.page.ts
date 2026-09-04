import { type Locator, type Page, expect } from "@playwright/test";

import { waitForConversationRoute } from "./navigation";

/**
 * Wall clock one mock turn needs end to end.
 *
 * A turn runs in the worker, so the budget covers the turn itself plus the
 * time it waits for a free worker slot behind other turns. Measured turns run
 * 4 s to 40 s; one queued behind a build waits minutes.
 */
const TURN_BUDGET_MS = 240_000;

export class ChatPage {
  readonly composer: Locator;
  readonly messageInput: Locator;
  readonly sendButton: Locator;
  readonly stopButton: Locator;
  readonly newChatButton: Locator;
  readonly refreshConversationsButton: Locator;
  readonly variantComparison: Locator;

  constructor(private page: Page) {
    this.composer = page.getByTestId("message-composer");
    this.messageInput = page.getByTestId("message-input");
    this.sendButton = page.getByTestId("send-button");
    this.stopButton = page.getByTestId("stop-button");
    this.newChatButton = page.getByRole("button", { name: "New chat" });
    this.refreshConversationsButton = page.getByTestId("conversations-refresh-button");
    this.variantComparison = page.getByTestId("data-variant-comparison");
  }

  async goto() {
    await this.page.goto("/");
    // The app holds a "Starting up..." gate until the readiness probe
    // answers, and that probe lags while the API serves long enrichment
    // calls from concurrently running specs.
    await expect(this.composer).toBeVisible({ timeout: 60_000 });
  }

  /** The strategy ID created by the last `newChat()` call. */
  lastStrategyId: string | null = null;

  /** The sidebar row for one conversation. The same id also marks its
   *  dismissed row and its subtree rows, so the testid names which one. */
  private conversationRow(strategyId: string): Locator {
    return this.page.locator(
      `[data-testid="conversation-item"][data-conversation-id="${strategyId}"]`,
    );
  }

  /** Open one conversation from the sidebar and wait for the router to put its
   *  id in the URL. A send() before the URL moves posts into the previous
   *  conversation. */
  private async openConversationRow(strategyId: string) {
    const conversationItem = this.conversationRow(strategyId);
    await expect(conversationItem).toBeVisible({ timeout: 10_000 });
    await conversationItem.click();
    await waitForConversationRoute(this.page, strategyId);
  }

  /** Start a fresh conversation so the test is isolated from prior state. */
  async newChat(siteId?: string) {
    const url = new URL(this.page.url());
    const baseUrl = url.origin;
    // Default to the site the test already switched to (from the URL), so the
    // new conversation lands on it rather than a hardcoded default.
    const firstSegment = url.pathname.split("/")[1];
    const selectedSite =
      siteId ??
      (firstSegment !== undefined && firstSegment !== "" ? firstSegment : "veupathdb");

    const strategyCreated = await this.page
      .context()
      .request.post(`${baseUrl}/api/v1/conversations/open`, {
        data: { siteId: selectedSite },
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });

    if (!strategyCreated.ok()) {
      const failureBody = await strategyCreated.text().catch(() => "");
      throw new Error(
        `openStrategy failed: ${strategyCreated.status()} ${failureBody}`.trim(),
      );
    }

    const body = (await strategyCreated.json()) as {
      conversationId?: string;
      strategyId?: string;
      id?: string;
    };
    const strategyId = body.conversationId ?? body.strategyId ?? body.id ?? null;
    if (strategyId == null || strategyId === "") {
      throw new Error("openStrategy returned no conversationId");
    }
    this.lastStrategyId = strategyId;

    await this.refreshConversationsButton.click();
    await this.openConversationRow(strategyId);

    await expect(this.composer).toBeVisible({ timeout: 10_000 });
    await expect(this.userMessages).toHaveCount(0, { timeout: 10_000 });
    await expect(this.assistantMessages).toHaveCount(0, { timeout: 10_000 });
  }

  /** Send `message`, then wait until the reply matching `pattern` is on the
   *  thread and the composer accepts input again. */
  async sendTurn(message: string, pattern: RegExp) {
    await this.send(message);
    await this.awaitTurn(pattern);
  }

  /** Wait out a turn the app started on its own, such as the edit a revert
   *  re-sends, on the same budget a sent turn gets. */
  async awaitTurn(pattern: RegExp) {
    await this.expectAssistantMessage(pattern, { timeout: TURN_BUDGET_MS });
    await this.expectIdle(TURN_BUDGET_MS);
  }

  async send(message: string) {
    await expect(async () => {
      await this.messageInput.fill(message);
      await expect(this.sendButton).toBeEnabled();
      await this.sendButton.click({ trial: false, timeout: 2_000 });
    }).toPass({ timeout: 30_000 });
  }

  async stopStreaming() {
    await this.stopButton.click();
  }

  get assistantMessages(): Locator {
    return this.page.locator(".is-assistant");
  }

  get userMessages(): Locator {
    return this.page.locator(".is-user");
  }

  // ── Thread surgery: branching and reverting ─────────────────────

  /** The one assistant reply that matches `pattern`. */
  assistantReply(pattern: RegExp): Locator {
    return this.assistantMessages.filter({ hasText: pattern });
  }

  /** The one user message that carries `text`. */
  userMessage(text: string): Locator {
    return this.userMessages.filter({ hasText: text });
  }

  /**
   * Branch into a new chat from the assistant reply matching `pattern`, and
   * return the id the router lands on. The fork response is read so a refused
   * branch fails here rather than as a missing message later.
   */
  async branchFromAssistantReply(pattern: RegExp): Promise<string> {
    const reply = this.assistantReply(pattern);
    await expect(reply).toHaveCount(1, { timeout: 30_000 });
    const forkResponse = this.page.waitForResponse(
      (r) =>
        /\/api\/v1\/conversations\/[^/]+\/fork$/.test(r.url()) &&
        r.request().method() === "POST",
    );
    await reply.hover();
    await reply
      .getByRole("button", { name: /branch to a new chat from here/i })
      .click();
    const fork = await forkResponse;
    if (!fork.ok()) {
      throw new Error(`fork refused: ${fork.status()} ${await fork.text()}`);
    }
    const { id } = (await fork.json()) as { id: string };
    await waitForConversationRoute(this.page, id);
    return id;
  }

  /** The edit composer of the message being edited. One is open at a time. */
  get editComposer(): Locator {
    return this.page.getByTestId("user-edit-composer");
  }

  /** The branch-or-revert dialog's inline error line. */
  get editDialogError(): Locator {
    return this.page.getByTestId("edit-dialog-error");
  }

  /**
   * Open the edit composer on the user message carrying `text`, replace the
   * text with `replacement`, and open the branch-or-revert dialog.
   *
   * The dialog is offered only on a message that is not the thread's last, so
   * an earlier turn is the only valid target.
   */
  async openEditDialog(text: string, replacement: string) {
    const message = this.userMessage(text);
    await expect(message).toHaveCount(1, { timeout: 30_000 });
    await message.hover();
    await message.getByRole("button", { name: "Edit" }).click();
    const input = this.editComposer.getByRole("textbox");
    await expect(input).toBeVisible({ timeout: 15_000 });
    await input.fill(replacement);
    await this.page.getByTestId("edit-composer-branch-or-revert").click();
    await expect(this.page.getByTestId("edit-revert-button")).toBeEnabled({
      timeout: 10_000,
    });
  }

  /** Confirm Revert in the open branch-or-revert dialog. */
  async confirmRevert() {
    const revert = this.page.getByTestId("edit-revert-button");
    const revertResponse = this.page.waitForResponse(
      (r) =>
        /\/api\/v1\/conversations\/[^/]+\/revert-to-message$/.test(r.url()) &&
        r.request().method() === "POST",
    );
    await revert.click();
    return revertResponse;
  }

  // ── Assertions ──────────────────────────────────────────────────

  /**
   * Wait until the composer accepts input again, which happens when the turn
   * ends. Measured turns reach 43 s when two run at once, and a third waits
   * for a free worker slot on top of that.
   */
  async expectIdle(timeout = 90_000) {
    await expect(this.sendButton).toBeVisible({ timeout });
    await expect(this.messageInput).toBeEditable({ timeout });
  }

  /**
   * Assert that an assistant message matching `pattern` is on the thread.
   *
   * Any assistant message counts, so a stale message from a prior
   * conversation does not decide the result.
   *
   * The reply lands when the worker finishes the turn, so the wait covers the
   * turn plus the time it spends queued behind another worker's turn. Measured
   * turns run 4 s to 16 s, and a queued one waits about as long again.
   */
  async expectAssistantMessage(pattern: RegExp, options?: { timeout?: number }) {
    const matching = this.assistantMessages.filter({ hasText: pattern });
    await expect(matching).not.toHaveCount(0, {
      timeout: options?.timeout ?? 90_000,
    });
  }

  /** Text content of the most recently rendered assistant message. */
  async lastAssistantMessageText(): Promise<string> {
    return this.assistantMessages.evaluateAll((els) => {
      const last = els[els.length - 1];
      return last?.textContent ?? "";
    });
  }

  async expectVariantComparison() {
    await expect(this.variantComparison).toBeVisible({ timeout: 60_000 });
  }

  /**
   * Pick the opening option of the slide that is on screen now.
   *
   * The carousel animates the answered slide out while the next one comes in,
   * so the attached slide can still be the one that is leaving. The read and
   * the click retry together, and the advance button is enabled only once the
   * current question holds an answer, so a click on a leaving slide is
   * discarded and repeated on the slide that stays.
   */
  private async pickSlideOption(slide: Locator, advance: Locator) {
    await expect(async () => {
      const optionTestIds = await slide
        .locator('[data-testid^="consult-option-"]')
        .evaluateAll((els) => els.map((el) => el.getAttribute("data-testid") ?? ""));
      const optionTestId = optionTestIds[0];
      if (optionTestId === undefined || optionTestId === "") {
        throw new Error("consult slide offers no option to pick");
      }
      await slide.getByTestId(optionTestId).click({ timeout: 2_000 });
      await expect(advance).toBeEnabled({ timeout: 2_000 });
    }).toPass({ timeout: 30_000 });
  }

  /** Answer every consult-carousel slide by picking its opening option,
   *  advancing with Next, and submitting on the last slide. */
  async answerConsultCarousel() {
    const carousel = this.page.getByTestId("consult-carousel");
    await expect(carousel).toBeVisible({ timeout: 60_000 });
    const slide = carousel.getByTestId("consult-slide");
    const submit = carousel.getByTestId("consult-submit");
    // Loop until Submit appears (last slide), answering each question on the way.
    for (let guard = 0; guard < 10; guard++) {
      await expect(slide).toHaveCount(1, { timeout: 10_000 });
      // The last slide replaces Next with Submit.
      const isLastSlide = (await submit.count()) > 0;
      const advance = isLastSlide ? submit : carousel.getByTestId("consult-next");
      await this.pickSlideOption(slide, advance);
      await advance.click();
      if (isLastSlide) return;
    }
    throw new Error("consult carousel did not reach a submit slide");
  }

  /** Attach a gene-ID file via the composer's native attachment button. The
   *  AddAttachment button opens a transient file chooser, so intercept it. */
  async attachGeneIdFile(name: string, contents: string) {
    const chooserPromise = this.page.waitForEvent("filechooser");
    await this.page.getByTestId("add-attachment").click();
    const chooser = await chooserPromise;
    await chooser.setFiles({
      name,
      mimeType: "text/csv",
      buffer: Buffer.from(contents),
    });
    await expect(this.composer.getByText(name)).toBeVisible({ timeout: 10_000 });
  }

  /** Assert at least one user-blocking question (from a scoping AWAITING_USER outcome). */
  async expectClarifyingQuestions(
    pattern: RegExp = /clarify|which|what evidence|how strict/i,
  ) {
    await this.expectAssistantMessage(pattern, { timeout: 60_000 });
  }

  /** Assert a verification success digest is visible (typed by characteristic phrases). */
  async expectVerificationSuccess(
    pattern: RegExp = /verified end-to-end|verification passed|root size|candidate drug targets/i,
  ) {
    await this.expectAssistantMessage(pattern, { timeout: 90_000 });
  }

  /** Assert a verification failure digest is visible (any failed-leaf signal). */
  async expectVerificationFeedback(
    pattern: RegExp = /returned 0|root size is 0|too narrow|loosen/i,
  ) {
    await this.expectAssistantMessage(pattern, { timeout: 90_000 });
  }

  async expectSendDisabled() {
    await expect(this.sendButton).toBeDisabled();
  }
}
