import { test, expect } from "../fixtures/test";
import { attach, postAttachment, readerIs, toast } from "../fixtures/composer";

/** A reader model that reads no image is offered none, by the composer and by the api. */

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
  "base64",
);
const TABLE_PNG = { name: "table.png", mimeType: "image/png", buffer: PNG };
const SONNET_READS_NO_FILE =
  "Claude Sonnet 5 does not read images or PDFs; choose a model that does in Settings.";

test.describe("Attachments for a reader that reads no image", () => {
  test("a reader that reads no image is not offered one and says why", async ({
    page,
    chatPage,
    settingsPage,
    siteId,
  }) => {
    await chatPage.startOn(siteId);
    await readerIs(page, settingsPage, "Claude Sonnet 5");
    const button = page.getByTestId("add-attachment");
    await expect(button).toHaveAccessibleName("Attach a gene-ID list");
    await expect(button).toHaveAttribute("title", SONNET_READS_NO_FILE);
    await attach(page, [TABLE_PNG]);
    await expect(toast(page, SONNET_READS_NO_FILE)).toBeVisible();
    await expect(page.getByTestId("composer-attachment")).toHaveCount(0);
  });

  test("the chat api refuses an image for a model that reads none", async ({
    apiClient,
    siteId,
  }) => {
    const refused = await postAttachment(
      apiClient,
      siteId,
      "anthropic:claude-sonnet-5",
      TABLE_PNG,
    );
    expect(refused.status()).toBe(422);
    expect(await refused.json()).toMatchObject({
      code: "ATTACHMENT_NOT_READABLE",
      detail: expect.stringMatching(/^Claude Sonnet 5 does not read images;/),
    });
  });
});
