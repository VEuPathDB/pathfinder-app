"use client";

import type { UIMessage } from "ai";

import { getAuthHeaders } from "@/lib/api/http";

export function downloadTextFile(filename: string, text: string, mime: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5_000);
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: getAuthHeaders({
      ...(init?.headers as Record<string, string> | undefined),
      contentType: "application/json",
    }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(body || `${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export function renderChatMarkdown(messages: UIMessage[]): string {
  const lines: string[] = ["# Pathfinder Chat Export", ""];
  for (const msg of messages) {
    lines.push(`## ${msg.role}`);
    for (const part of msg.parts) {
      if (part.type === "text") lines.push(part.text);
    }
    lines.push("", "---", "");
  }
  return lines.join("\n");
}
