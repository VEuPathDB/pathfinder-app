"use client";

import type { UIMessage } from "ai";

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

export function renderChatMarkdown(messages: UIMessage[]): string {
  const lines: string[] = ["# PathFinder conversation export", ""];
  for (const msg of messages) {
    lines.push(`## ${msg.role}`);
    for (const part of msg.parts) {
      if (part.type === "text") lines.push(part.text);
    }
    lines.push("", "---", "");
  }
  return lines.join("\n");
}
