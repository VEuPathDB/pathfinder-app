import { BASE_URL, expect, test } from "../fixtures/test";
import { ROUTE_TIMEOUT_MS } from "../pages/navigation";

test.describe("Help and the data statement", () => {
  test("help opens from the rail and leads to the data statement and its date", async ({
    page,
    chatPage,
  }) => {
    await chatPage.goto();

    await page.getByRole("link", { name: "Help", exact: true }).click();
    await expect(page).toHaveURL(`${BASE_URL}/help`, { timeout: ROUTE_TIMEOUT_MS });
    await expect(page.getByRole("heading", { level: 1, name: "Help" })).toBeVisible();

    await page.getByRole("link", { name: "Your data in PathFinder" }).click();
    await expect(page).toHaveURL(`${BASE_URL}/help/your-data`, {
      timeout: ROUTE_TIMEOUT_MS,
    });
    await expect(
      page.getByRole("heading", { level: 1, name: "Your data in PathFinder" }),
    ).toBeVisible();
    await expect(page.getByText("Last updated: October 9, 2026")).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 2, name: "In brief" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 2, name: "Learning from your strategies" }),
    ).toBeVisible();
  });
});
