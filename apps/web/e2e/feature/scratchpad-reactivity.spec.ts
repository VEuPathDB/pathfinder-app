/**
 * Notes rail E2E: verifies the client reacts to the agent's
 * `note(...)` tool call mid-stream.
 *
 * The real pipeline is bypassed via `page.route()` so we can deterministically
 * emit exactly the SSE chunks the client cares about:
 *
 *   - `data-scratchpad-updated` -> invalidates the scratchpad notes query
 *
 * and control the paged scratchpad GET responses. Full backend pipeline
 * coverage lives in the integration test
 * `apps/api/src/pathfinder/tests/integration/chat/test_multi_turn_pipeline.py`
 * (see the `test_scratchpad_note_persists_across_turns` test).
 *
 * Strict selectors only - testids on the panel, note card, pin button, and
 * delete button (added surgically to `ScratchpadPanel.tsx`).
 */

import type { BrowserContext, Route } from "@playwright/test";

import { test, expect } from "../fixtures/test";
import { entrySiteId } from "../fixtures/entry-site";
import { sseDone, sseFrame, uiMessageStreamHeaders } from "../fixtures/sse";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
const NOTE_ID = "note-e2e-scratchpad-001";
const NOTE_TITLE = "E2E_SCRATCHPAD_NOTE";
const NOTE_SUMMARY = "one-line summary of the finding";
const NOTE_BODY = "Fuller body text saved by the agent.";

interface OpenConversationResponse {
  conversationId?: string;
  strategyId?: string;
  id?: string;
}

async function openConversation(
  context: BrowserContext,
  siteId: string,
): Promise<string> {
  const resp = await context.request.post(`${BASE_URL}/api/v1/conversations/open`, {
    data: { siteId },
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!resp.ok()) {
    throw new Error(`openConversation failed: ${resp.status()}`);
  }
  const body = (await resp.json()) as OpenConversationResponse;
  const id = body.conversationId ?? body.strategyId ?? body.id;
  if (id === undefined || id === "") {
    throw new Error("openConversation returned no id");
  }
  return id;
}

interface StubNote {
  id: string;
  conversationId: string;
  title: string;
  summary: string;
  body: string;
  tags: string[];
  pinned: boolean;
  bodyTokens: number;
  createdAt: string;
  updatedAt: string;
}

function buildNote(
  overrides: Partial<StubNote> & Pick<StubNote, "conversationId">,
): StubNote {
  const now = new Date().toISOString();
  return {
    id: NOTE_ID,
    title: NOTE_TITLE,
    summary: NOTE_SUMMARY,
    body: NOTE_BODY,
    tags: [],
    pinned: false,
    bodyTokens: 12,
    createdAt: now,
    updatedAt: now,
    ...overrides,
  };
}

/**
 * SSE payload emitted by the mocked `/api/v1/chat` endpoint. The client
 * opens a `data-scratchpad-updated` chunk as the signal that the agent
 * called `note(...)` during its phase run.
 */
function scratchpadChatStream(): string {
  return [
    sseFrame({
      type: "start",
      messageId: "22222222-2222-2222-2222-222222222222",
      messageMetadata: {
        phase: "scoping",
        model: "mock:deterministic",
        traceId: "scratchpad-e2e-trace",
        createdAt: new Date().toISOString(),
      },
    }),
    sseFrame({ type: "data-scratchpad-updated", data: {} }),
    sseFrame({ type: "finish", finishReason: "stop" }),
    sseDone(),
  ].join("");
}

test.describe("Notes rail", () => {
  test.describe.configure({ mode: "serial" });

  test("notes panel shows note created by agent mid-stream", async ({
    page,
    context,
  }) => {
    const siteId = await entrySiteId(context, BASE_URL);
    const conversationId = await openConversation(context, siteId);
    const notesUrl = `**/api/v1/conversations/${conversationId}/scratchpad/notes`;

    // State machine: GET returns [] until the agent "creates" the note, then
    // returns [note]. Increments on each call so the refetch triggered by
    // `data-scratchpad-updated` sees the new value.
    let notesVersion = 0;
    let currentNote: StubNote | null = null;

    await page.route(notesUrl, async (route: Route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      const body = currentNote === null ? [] : [currentNote];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    });

    await page.route("**/api/v1/chat", async (route: Route) => {
      // Simulate the agent side-effect: create the note, then stream the
      // scratchpad-updated chunk so the client invalidates and refetches.
      currentNote = buildNote({ conversationId });
      notesVersion += 1;
      await route.fulfill({
        status: 200,
        headers: uiMessageStreamHeaders(),
        body: scratchpadChatStream(),
      });
    });

    await page.goto(`/${siteId}/conversation/${conversationId}`);

    const composer = page.getByPlaceholder(/Ask about/i);
    await expect(composer).toBeVisible({ timeout: 30_000 });

    // Open the notes rail panel up-front: empty state first.
    const openScratchpadButton = page.getByRole("button", {
      name: "Open Notes",
      exact: true,
    });
    await expect(openScratchpadButton).toBeVisible({ timeout: 15_000 });
    await openScratchpadButton.click();

    const panel = page.getByTestId("scratchpad-panel");
    await expect(panel).toBeVisible();
    await expect(page.getByTestId("scratchpad-empty")).toBeVisible();

    // Send any message - our chat-route stub emits `data-scratchpad-updated`
    // regardless of prompt text.
    await composer.click();
    await composer.pressSequentially("trigger scratchpad note", { delay: 10 });
    const submit = page.getByRole("button", { name: "Send", exact: true });
    await expect(submit).toBeEnabled({ timeout: 15_000 });
    await composer.press("Enter");

    const note = page.getByTestId(`scratchpad-note-${NOTE_ID}`);
    await expect(note).toBeVisible({ timeout: 15_000 });
    await expect(note).toContainText(NOTE_TITLE);
    await expect(note).toContainText(NOTE_SUMMARY);

    // Sanity-check the chat route was invoked at least once.
    expect(notesVersion).toBeGreaterThan(0);
  });

  test("user can pin and delete a note", async ({ page, context }) => {
    const siteId = await entrySiteId(context, BASE_URL);
    const conversationId = await openConversation(context, siteId);
    const notesUrl = `**/api/v1/conversations/${conversationId}/scratchpad/notes`;
    const noteUrl = `**/api/v1/conversations/${conversationId}/scratchpad/notes/${NOTE_ID}`;

    // Start with the note already present; no chat needed for this test.
    let currentNote: StubNote | null = buildNote({
      conversationId,
      pinned: false,
    });

    await page.route(notesUrl, async (route: Route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      const body = currentNote === null ? [] : [currentNote];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    });

    await page.route(noteUrl, async (route: Route) => {
      const method = route.request().method();
      if (method === "PATCH") {
        const payload = route.request().postDataJSON() as { pinned?: boolean };
        if (currentNote !== null && payload.pinned !== undefined) {
          currentNote = { ...currentNote, pinned: payload.pinned };
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(currentNote),
        });
        return;
      }
      if (method === "DELETE") {
        currentNote = null;
        await route.fulfill({ status: 204, body: "" });
        return;
      }
      await route.continue();
    });

    await page.goto(`/${siteId}/conversation/${conversationId}`);

    const composer = page.getByPlaceholder(/Ask about/i);
    await expect(composer).toBeVisible({ timeout: 30_000 });

    // Open the notes rail.
    await page.getByRole("button", { name: "Open Notes", exact: true }).click();

    const note = page.getByTestId(`scratchpad-note-${NOTE_ID}`);
    await expect(note).toBeVisible({ timeout: 15_000 });
    await expect(note).toHaveAttribute("data-pinned", "false");

    // Pin.
    const pinButton = page.getByTestId(`scratchpad-pin-${NOTE_ID}`);
    await expect(pinButton).toHaveAccessibleName(/^Pin$/);
    await pinButton.click();
    await expect(note).toHaveAttribute("data-pinned", "true", {
      timeout: 10_000,
    });
    // Button flips to "Unpin" once the refetched state lands.
    await expect(pinButton).toHaveAccessibleName(/^Unpin$/);

    // Delete.
    const deleteButton = page.getByTestId(`scratchpad-delete-${NOTE_ID}`);
    await deleteButton.click();
    await expect(note).toHaveCount(0, { timeout: 10_000 });
    await expect(page.getByTestId("scratchpad-empty")).toBeVisible();
  });
});
