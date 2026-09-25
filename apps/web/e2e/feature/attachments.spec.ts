import type { Page } from "@playwright/test";

import { test, expect } from "../fixtures/test";
import type { ApiClient } from "../fixtures/api-client";
import { currentSiteId } from "../pages/navigation";
import type { SettingsPage } from "../pages/settings.page";

/** An attached image or PDF rides the message as a file part, survives a reload,
 * and is refused by the composer and the api for a model that does not read it. */

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
  "base64",
);
const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");
const SONNET_READS_NO_FILE =
  "Claude Sonnet 5 does not read images or PDFs; choose a model that does in Settings.";

function png(name: string) {
  return { name, mimeType: "image/png", buffer: PNG };
}

/** Put `modelName` on the role that reads the user's message. */
async function readerIs(page: Page, settingsPage: SettingsPage, modelName: string) {
  await settingsPage.open();
  await settingsPage.openTab("Model");
  await page
    .getByTestId("phase-row-lead")
    .getByRole("button", { name: /^Select model:/ })
    .click();
  await page
    .getByRole("row")
    .filter({ hasText: modelName })
    .getByRole("button", { name: "Select" })
    .click();
  await expect(
    page.getByTestId("phase-row-lead").getByRole("button", { name: /^Select model:/ }),
  ).toHaveAccessibleName(`Select model: ${modelName}`);
  await settingsPage.close();
}

async function attach(
  page: Page,
  files: { name: string; mimeType: string; buffer: Buffer }[],
) {
  const chooser = page.waitForEvent("filechooser");
  await page.getByTestId("add-attachment").click();
  await (await chooser).setFiles(files);
}

interface LoggedPart {
  type: string;
  filename?: string;
  mediaType?: string;
}

async function loggedUserParts(
  apiClient: ApiClient,
  id: string,
): Promise<LoggedPart[]> {
  const resp = await apiClient.get(`/api/v1/conversations/${id}/events/snapshot`);
  const { chunks } = (await resp.json()) as {
    chunks: { type: string; message?: { parts?: LoggedPart[] } }[];
  };
  return chunks.find((c) => c.type === "user-message")?.message?.parts ?? [];
}

test.describe("Attachments", () => {
  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("a reader that reads no image is not offered one and says why", async ({
    page,
    settingsPage,
  }) => {
    await readerIs(page, settingsPage, "Claude Sonnet 5");
    const button = page.getByTestId("add-attachment");
    await expect(button).toHaveAccessibleName("Attach a gene-ID list");
    await expect(button).toHaveAttribute("title", SONNET_READS_NO_FILE);
    await attach(page, [png("table.png")]);
    await expect(page.getByText(SONNET_READS_NO_FILE)).toBeVisible();
    await expect(page.getByTestId("composer-attachment")).toHaveCount(0);
  });

  test("an image and a PDF reach the thread and survive a reload", async ({
    page,
    chatPage,
    settingsPage,
    apiClient,
  }) => {
    await readerIs(page, settingsPage, "GPT-5.6 Luna");
    await expect(page.getByTestId("add-attachment")).toHaveAccessibleName(
      "Attach a gene-ID list, an image or a PDF",
    );
    await attach(page, [
      png("table.png"),
      { name: "paper.pdf", mimeType: "application/pdf", buffer: PDF },
    ]);
    await expect(page.getByTestId("composer-attachment")).toHaveText([
      "table.png",
      "paper.pdf",
    ]);
    await chatPage.sendTurn(
      "which genes are in these?",
      /\[mock\] which genes are in these\?/,
    );

    const message = chatPage.userMessage("which genes are in these?");
    await expect(message.getByTestId("user-attachment-image")).toHaveAttribute(
      "alt",
      "table.png",
    );
    await expect(message.getByTestId("user-attachment-file")).toHaveText("paper.pdf");
    expect(
      await loggedUserParts(apiClient, chatPage.lastStrategyId ?? ""),
    ).toMatchObject([
      { type: "text" },
      { type: "file", filename: "table.png", mediaType: "image/png" },
      { type: "file", filename: "paper.pdf", mediaType: "application/pdf" },
    ]);

    await page.reload();
    await expect(
      chatPage
        .userMessage("which genes are in these?")
        .getByTestId("user-attachment-image"),
    ).toHaveAttribute("alt", "table.png");
  });

  test("more than six files are refused before the send", async ({
    page,
    chatPage,
    settingsPage,
  }) => {
    await readerIs(page, settingsPage, "GPT-5.6 Luna");
    await attach(
      page,
      Array.from({ length: 7 }, (_, n) => png(`${n}.png`)),
    );
    await expect(page.getByRole("alert").filter({ hasText: "at most 6" })).toHaveText(
      "One message can carry at most 6 attachments; this one has 7.",
    );
    await chatPage.messageInput.fill("which genes?");
    await expect(chatPage.sendButton).toBeDisabled();
  });
});

test.describe("The chat api refuses what the reader cannot take", () => {
  async function post(apiClient: ApiClient, page: Page, lead: string, bytes: Buffer) {
    return apiClient.post("/api/v1/chat", {
      data: {
        conversationId: crypto.randomUUID(),
        siteId: currentSiteId(page),
        phaseModels: { lead },
        messages: [
          {
            id: crypto.randomUUID(),
            role: "user",
            parts: [
              { type: "text", text: "which genes are in this image?" },
              {
                type: "file",
                mediaType: "image/png",
                filename: "table.png",
                url: `data:image/png;base64,${bytes.toString("base64")}`,
              },
            ],
          },
        ],
      },
    });
  }

  test("an image for a model that reads none, and a file over 10 MB", async ({
    page,
    chatPage,
    apiClient,
  }) => {
    await chatPage.goto();
    const unreadable = await post(apiClient, page, "anthropic:claude-sonnet-5", PNG);
    expect(unreadable.status()).toBe(422);
    expect(await unreadable.json()).toMatchObject({
      code: "ATTACHMENT_NOT_READABLE",
      detail: expect.stringMatching(/^Claude Sonnet 5 does not read images;/),
    });

    const large = await post(
      apiClient,
      page,
      "openai:gpt-5.6-luna",
      Buffer.alloc(11 * 1024 * 1024),
    );
    expect(large.status()).toBe(413);
    expect(await large.json()).toMatchObject({
      code: "ATTACHMENT_TOO_LARGE",
      detail: "table.png is 11.0 MB; one attachment can be at most 10 MB.",
    });
  });
});
