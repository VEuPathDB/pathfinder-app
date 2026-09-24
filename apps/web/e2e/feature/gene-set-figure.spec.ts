import { test, expect } from "../fixtures/test";

/** The set the mock model saves when a message asks for one "as a gene set". */
const SAVED_SET = "mock gene set";

interface GeneSetRow {
  id: string;
  name: string;
}

/**
 * The thread's gene-set figure carries the set's own actions: a delete asks
 * first, and after it the figure says the set was deleted and offers nothing.
 * Real WDK and Postgres; only the LLM is mocked.
 */
test.describe("Gene set figure", () => {
  test("deletes the set after a confirmation and says so", async ({
    chatPage,
    page,
    apiClient,
    sitePicker,
  }) => {
    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");
    await chatPage.newChat("plasmodb");
    await chatPage.send("test message for plasmodb");
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await chatPage.expectIdle();

    await chatPage.send("Save PF3D7_0709000 and PF3D7_1133400 as a gene set");
    const figure = page.getByTestId("data-gene-set");
    await expect(figure).toContainText(SAVED_SET, { timeout: 90_000 });
    await chatPage.expectIdle();

    await expect(
      figure.getByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    ).toBeVisible();
    await figure.getByRole("button", { name: "Delete gene set" }).click();
    const confirm = page.getByRole("alertdialog", { name: `Delete ${SAVED_SET}?` });
    await expect(confirm).toBeVisible();
    await confirm.getByRole("button", { name: "Delete" }).click();

    await expect(figure).toContainText("Gene set deleted");
    await expect(figure.getByRole("button")).toHaveCount(0);

    const resp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    expect(resp.ok()).toBeTruthy();
    const names = ((await resp.json()) as GeneSetRow[]).map((gs) => gs.name);
    expect(names).not.toContain(SAVED_SET);
  });
});
