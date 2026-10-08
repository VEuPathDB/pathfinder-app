import type { PrivacySettings, PrivacyUpdate } from "@pathfinder/shared";

import { buildUrl, getAuthHeaders } from "@/lib/api/http";

const PRIVACY_PATH = "/api/v1/me/privacy";

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
  const res = await fetch(buildUrl(PRIVACY_PATH), {
    method: "PATCH",
    credentials: "include",
    headers: getAuthHeaders({ contentType: "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`updatePrivacySettings: ${res.status}`);
  return (await res.json()) as PrivacySettings;
}
