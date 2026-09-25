"use client";

import { Download, FileText, Upload } from "lucide-react";

import { exportGeneSetEndpoint } from "@pathfinder/shared/generated/hooks/useExportGeneSetEndpoint";
import { getStrategyAst } from "@pathfinder/shared/generated/hooks/useGetStrategyAst";
import { importGeneSet } from "@pathfinder/shared/generated/hooks/useImportGeneSet";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { updateStrategy } from "@pathfinder/shared/generated/hooks/useUpdateStrategy";
import { listGeneSets } from "@/lib/api/geneSets";
import { toStrategy, writeStrategy } from "@/lib/api/strategy";
import { queryKeyPrefixes } from "@/lib/query/keys";
import { beginConversation } from "@/features/conversation/api/beginConversation";
import { loadConversationSnapshot } from "@/features/conversation/api/conversationSnapshot";

import { downloadTextFile, renderChatMarkdown } from "./registryUtils";
import type { Command, CommandContext, CommandResult } from "./types";

function failure(message: string): CommandResult {
  return { kind: "toast", type: "error", message };
}

export const renameCommand: Command = {
  kind: "deterministic",
  name: "rename",
  description: "Rename this conversation",
  icon: <FileText className="size-3.5" aria-hidden />,
  params: [
    {
      kind: "text",
      name: "name",
      label: "New name",
      placeholder: "Descriptive conversation title",
    },
  ],
  run: async (values, ctx) => {
    const name = values["name"]?.trim() ?? "";
    if (name.length === 0) return failure("Name cannot be empty.");
    await beginConversation(ctx.conversationId, { siteId: ctx.siteId });
    const updated = await updateStrategy(ctx.conversationId, { name });
    writeStrategy(ctx.queryClient, ctx.conversationId, toStrategy(updated));
    await ctx.queryClient.invalidateQueries({
      queryKey: listStrategiesQueryOptions({ siteId: ctx.siteId }).queryKey,
    });
    return { kind: "toast", type: "success", message: `Renamed to "${name}".` };
  },
};

async function exportStrategy(ctx: CommandContext): Promise<CommandResult> {
  if (ctx.stepCount === 0) return failure("This conversation has no strategy yet.");
  const ast = await getStrategyAst(ctx.conversationId);
  downloadTextFile(
    `strategy-${ctx.conversationId}.json`,
    JSON.stringify(ast, null, 2),
    "application/json",
  );
  return { kind: "toast", type: "success", message: "Strategy downloaded." };
}

async function exportChat(
  ctx: CommandContext,
  format: "md" | "json",
): Promise<CommandResult> {
  if (!ctx.conversationExists) return failure("This conversation has no messages yet.");
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
  return { kind: "toast", type: "success", message: "Conversation exported." };
}

async function exportLatestGeneSet(
  ctx: CommandContext,
  format: "csv" | "txt",
): Promise<CommandResult> {
  const [latest] = await listGeneSets(ctx.siteId);
  if (latest === undefined) return failure("No gene sets to export.");
  const exported = await exportGeneSetEndpoint(latest.id, { format });
  return { kind: "download", url: exported.url, filename: exported.filename };
}

export const exportCommand: Command = {
  kind: "deterministic",
  name: "export",
  aliases: ["save", "download"],
  description: "Export the strategy, this conversation, or your latest gene set",
  icon: <Download className="size-3.5" aria-hidden />,
  params: [
    {
      kind: "select",
      name: "what",
      label: "What to export",
      options: [
        { value: "strategy-json", label: "Current strategy (JSON)" },
        { value: "chat-md", label: "This conversation (Markdown)" },
        { value: "chat-json", label: "This conversation (JSON)" },
        { value: "gene-set-csv", label: "Latest gene set on this site (CSV)" },
        { value: "gene-set-txt", label: "Latest gene set on this site (TXT)" },
      ],
    },
  ],
  run: async (values, ctx) => {
    const what = values["what"] ?? "";
    switch (what) {
      case "strategy-json":
        return exportStrategy(ctx);
      case "chat-md":
        return exportChat(ctx, "md");
      case "chat-json":
        return exportChat(ctx, "json");
      case "gene-set-csv":
        return exportLatestGeneSet(ctx, "csv");
      case "gene-set-txt":
        return exportLatestGeneSet(ctx, "txt");
      default:
        return failure(`Unknown export: ${what}`);
    }
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
      placeholder: "Paste gene IDs - newline, comma, tab, or space separated",
      rows: 6,
    },
  ],
  run: async (values, ctx) => {
    const name = values["name"]?.trim() ?? "";
    const rawText = values["rawText"] ?? "";
    if (name.length === 0) return failure("Name required.");
    if (rawText.trim().length === 0) return failure("Paste at least one gene ID.");
    const created = await importGeneSet({ name, siteId: ctx.siteId, rawText });
    await ctx.queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.geneSets });
    return {
      kind: "toast",
      type: "success",
      message: `Imported "${name}" with ${created.geneCount} gene IDs.`,
    };
  },
};
