import { request } from "@playwright/test";

import { heldTestToken } from "./wire";

export function wdkTestToken(): string {
  const token = heldTestToken();
  if (token === "") {
    throw new Error("No test holds a VEuPathDB token; read it inside a test.");
  }
  return token;
}

export function accountToken(): string {
  const token = process.env["WDK_TEST_TOKEN"] ?? "";
  if (token === "") {
    throw new Error(
      "WDK_TEST_TOKEN is not set. A record run acts as the registered VEuPathDB " +
        "account: export WDK_TEST_TOKEN, or WDK_TEST_EMAIL and WDK_TEST_PASSWORD.",
    );
  }
  return token;
}

const AUTHORIZATION = "Authorization=";

function registered(token: string): boolean {
  const payload = token.split(".")[1] ?? "";
  try {
    const claims = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
      is_guest?: boolean;
    };
    return claims.is_guest !== true;
  } catch {
    return false;
  }
}

export async function siteLoginToken(
  serviceUrl: string,
  email: string,
  password: string,
): Promise<string> {
  const site = await request.newContext();
  try {
    const response = await site.post(`${serviceUrl}/login`, {
      data: { email, password, redirectUrl: "/" },
      maxRedirects: 0,
    });
    const token = response
      .headersArray()
      .filter((header) => header.name.toLowerCase() === "set-cookie")
      .map((header) => header.value.split(";", 1)[0] ?? "")
      .filter((cookie) => cookie.startsWith(AUTHORIZATION))
      .map((cookie) => cookie.slice(AUTHORIZATION.length).replace(/^"|"$/g, ""))
      .find((value) => value !== "" && registered(value));
    if (token === undefined) {
      throw new Error(
        `the VEuPathDB login answered ${response.status()} with no registered Authorization cookie`,
      );
    }
    return token;
  } finally {
    await site.dispose();
  }
}
