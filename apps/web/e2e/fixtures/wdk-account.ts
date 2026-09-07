import { type APIRequestContext, expect, test } from "@playwright/test";

/** The one reason a credentialed WDK spec skips. */
const NO_CREDENTIALS =
  "set WDK_TEST_EMAIL/WDK_TEST_PASSWORD to run real-account WDK tests";

/**
 * The registered VEuPathDB token every worker acts with. VEuPathDB refuses
 * guest service calls, so a run without it cannot reach any WDK-backed route.
 * The value is never logged.
 */
export function wdkTestToken(): string {
  const token = process.env["WDK_TEST_TOKEN"] ?? "";
  if (token === "") {
    throw new Error(
      "WDK_TEST_TOKEN is not set. VEuPathDB refuses guest service calls, so the " +
        "e2e suite must run as a registered VEuPathDB account. Export the token " +
        "in the shell that starts Playwright.",
    );
  }
  return token;
}

/**
 * Sign the running test in as the real VEuPathDB account on `siteId`, or skip
 * it when the account credentials are not in the environment.
 */
export async function signInAsWdkAccount(
  apiClient: APIRequestContext,
  siteId: string,
): Promise<void> {
  const email = process.env["WDK_TEST_EMAIL"] ?? "";
  const password = process.env["WDK_TEST_PASSWORD"] ?? "";
  test.skip(email === "" || password === "", NO_CREDENTIALS);

  const resp = await apiClient.post("/api/v1/veupathdb/auth/login", {
    params: { siteId },
    data: { email, password },
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  expect(resp.ok(), `wdk login ${resp.status()}: ${await resp.text()}`).toBeTruthy();

  // The account is its own user, with its own first-login eval-data notice;
  // a fresh database shows it over the app until the account acknowledges it.
  const notice = await apiClient.patch("/api/v1/me/privacy", {
    data: { noticeSeen: true },
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  expect(
    notice.ok(),
    `eval-data notice acknowledgement ${notice.status()}`,
  ).toBeTruthy();
}
