"use client";

import { Download, Upload } from "lucide-react";

import { listGeneSets } from "@/features/workbench/api/geneSets";
import { loadConversationSnapshot } from "@/features/conversation/api/conversationSnapshot";

import { downloadTextFile, fetchJson, renderChatMarkdown } from "./registryUtils";
import type { Command } from "./types";

export const exportCommand: Command = {
  kind: "deterministic",
  name: "export",
  aliases: ["save", "download"],
  description: "Export strategy, chat, or gene set",
  icon: <Download className="size-3.5" aria-hidden />,
  params: [
    {
      kind: "select",
      name: "what",
      label: "What to export",
      options: [
        {
          value: "strategy",
          label: "Current strategy",
          description: "JSON dump of the active strategy",
        },
        {
          value: "chat",
          label: "This conversation",
          description: "All messages (JSON or Markdown)",
        },
        {
          value: "gene-set",
          label: "A gene set",
          description: "Your most-recent saved gene set (CSV/TXT)",
        },
      ],
    },
    {
      kind: "select",
      name: "format",
      label: "Format",
      options: [
        { value: "json", label: "JSON (strategy / chat)" },
        { value: "md", label: "Markdown (chat)" },
        { value: "csv", label: "CSV (gene set)" },
        { value: "txt", label: "TXT (gene set)" },
      ],
    },
  ],
  run: async (values, ctx) => {
    const what = values["what"];
    const format = values["format"];
    if (what === "strategy") {
      if (format !== "json") {
        return {
          kind: "toast",
          type: "error",
          message: "Strategy export supports JSON only.",
        };
      }
      const chat = await fetchJson<{ wdkStrategyId: number | null }>(
        `/api/v1/conversations/${ctx.conversationId}`,
      );
      const strategies = await fetchJson<
        Array<{ id: string; wdkStrategyId: number | null }>
      >(`/api/v1/conversations?siteId=${encodeURIComponent(ctx.siteId)}`);
      const target = strategies.find((s) => s.wdkStrategyId === chat.wdkStrategyId);
      if (target === undefined) {
        return {
          kind: "toast",
          type: "error",
          message: "No strategy linked to this chat.",
        };
      }
      const payload = await fetchJson<Record<string, unknown>>(
        `/api/v1/conversations/${target.id}`,
      );
      downloadTextFile(
        `strategy-${target.id}.json`,
        JSON.stringify(payload, null, 2),
        "application/json",
      );
      return {
        kind: "toast",
        type: "success",
        message: "Strategy downloaded.",
      };
    }
    if (what === "chat") {
      const { messages } = await loadConversationSnapshot(ctx.conversationId);
      if (format === "md") {
        const md = renderChatMarkdown(messages);
        downloadTextFile(`chat-${ctx.conversationId}.md`, md, "text/markdown");
      } else {
        downloadTextFile(
          `chat-${ctx.conversationId}.json`,
          JSON.stringify(messages, null, 2),
          "application/json",
        );
      }
      return {
        kind: "toast",
        type: "success",
        message: "Chat exported.",
      };
    }
    if (what === "gene-set") {
      const fmt = format === "txt" ? "txt" : "csv";
      const sets = await listGeneSets(ctx.siteId);
      if (sets.length === 0) {
        return {
          kind: "toast",
          type: "error",
          message: "No gene sets to export.",
        };
      }
      const target = sets[0];
      if (target === undefined) {
        return {
          kind: "toast",
          type: "error",
          message: "Gene set not found.",
        };
      }
      const resp = await fetchJson<{ url: string; filename: string }>(
        `/api/v1/gene-sets/${target.id}/export?format=${fmt}`,
        { method: "POST" },
      );
      return {
        kind: "download",
        url: resp.url,
        filename: resp.filename,
      };
    }
    return {
      kind: "toast",
      type: "error",
      message: `Unknown target: ${what}`,
    };
  },
};

export const importCommand: Command = {
  kind: "deterministic",
  name: "import",
  description: "Import a gene set from pasted IDs",
  icon: <Upload className="size-3.5" aria-hidden />,
  params: [
    {
      kind: "text",
      name: "name",
      label: "Gene set name",
      placeholder: "e.g. my uploaded list",
    },
    {
      kind: "textarea",
      name: "rawText",
      label: "Gene IDs",
      placeholder: "Paste gene IDs — newline, comma, tab, or space separated",
      rows: 6,
    },
  ],
  run: async (values, ctx) => {
    const name = values["name"]?.trim() ?? "";
    const rawText = values["rawText"] ?? "";
    if (name.length === 0) {
      return {
        kind: "toast",
        type: "error",
        message: "Name required.",
      };
    }
    if (rawText.trim().length === 0) {
      return {
        kind: "toast",
        type: "error",
        message: "Paste at least one gene ID.",
      };
    }
    const resp = await fetchJson<{ geneCount: number; id: string }>(
      "/api/v1/gene-sets/import",
      {
        method: "POST",
        body: JSON.stringify({ name, siteId: ctx.siteId, rawText }),
      },
    );
    return {
      kind: "toast",
      type: "success",
      message: `Imported "${name}" with ${resp.geneCount} gene IDs.`,
    };
  },
};
