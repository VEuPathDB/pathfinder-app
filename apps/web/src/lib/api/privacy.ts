import {
  DATA_STATEMENT_VERSION,
  type DataNoticeContinue,
  type PrivacySettings,
  type PrivacyUpdate,
} from "@pathfinder/shared";

import { buildUrl, getAuthHeaders } from "@/lib/api/http";

const PRIVACY_PATH = "/api/v1/me/privacy";

export const PRIVACY_QUERY_KEY = ["me", "privacy"] as const;

async function sendPrivacy(
  path: string,
  method: "PATCH" | "POST",
  body: PrivacyUpdate | DataNoticeContinue,
): Promise<PrivacySettings> {
  const res = await fetch(buildUrl(path), {
    method,
    credentials: "include",
    headers: getAuthHeaders({ contentType: "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${method} ${path}: ${res.status}`);
  return (await res.json()) as PrivacySettings;
}

export async function getPrivacySettings(): Promise<PrivacySettings> {
  const res = await fetch(buildUrl(PRIVACY_PATH), {
    credentials: "include",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`getPrivacySettings: ${res.status}`);
  return (await res.json()) as PrivacySettings;
}

export async function updatePrivacySettings(
  body: PrivacyUpdate,
): Promise<PrivacySettings> {
  return await sendPrivacy(PRIVACY_PATH, "PATCH", body);
}

export async function continuePastDataNotice(
  evalDataConsent: boolean,
): Promise<PrivacySettings> {
  return await sendPrivacy(`${PRIVACY_PATH}/data-notice`, "POST", {
    version: DATA_STATEMENT_VERSION,
    evalDataConsent,
  });
}
