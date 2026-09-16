"use client";

import {
  Ban,
  BookOpen,
  FileText,
  HelpCircle,
  LineChart,
  Plus,
  Sparkles,
  Trash,
} from "lucide-react";

import { exportCommand, importCommand } from "./commandsIO";
import { fetchJson } from "./registryUtils";
import type { Command } from "./types";

export const commands: Command[] = [
  {
    kind: "deterministic",
    name: "new",
    description: "Clear composer (start fresh message)",
    icon: <Plus className="size-3.5" aria-hidden />,
    params: [],
    run: () => ({
      kind: "prefill",
      text: "",
      submit: false,
    }),
  },
  {
    kind: "deterministic",
    name: "rename",
    description: "Rename this chat",
    icon: <FileText className="size-3.5" aria-hidden />,
    params: [
      {
        kind: "text",
        name: "name",
        label: "New name",
        placeholder: "Descriptive chat title",
      },
    ],
    run: async (values, ctx) => {
      const name = values["name"]?.trim() ?? "";
      if (name.length === 0) {
        return {
          kind: "toast",
          type: "error",
          message: "Name cannot be empty.",
        };
      }
      await fetchJson(`/api/v1/conversations/${ctx.conversationId}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      });
      return {
        kind: "toast",
        type: "success",
        message: `Renamed to "${name}".`,
      };
    },
  },
  exportCommand,
  importCommand,
  {
    kind: "deterministic",
    name: "help",
    aliases: ["?"],
    description: "List available slash commands",
    icon: <HelpCircle className="size-3.5" aria-hidden />,
    params: [],
    run: () => {
      const lines = commands.map((c) => `- /${c.name} - ${c.description}`);
      return {
        kind: "toast",
        type: "info",
        message: `Slash commands:\n${lines.join("\n")}`,
      };
    },
  },
  {
    kind: "llm-prefill",
    name: "clear",
    description: "Clear the current strategy",
    icon: <Trash className="size-3.5 text-destructive" aria-hidden />,
    params: [],
    prompt: () =>
      "Clear the current strategy by calling clear_strategy with confirm=true.",
    autoSubmit: true,
  },
  {
    kind: "llm-prefill",
    name: "analyze",
    description: "Analyze the current strategy and suggest next steps",
    icon: <LineChart className="size-3.5" aria-hidden />,
    params: [],
    prompt: () =>
      "Analyze my current strategy. Summarize topology and step flow, any " +
      "weak spots or redundant steps, concrete improvement suggestions, " +
      "and what I should try next.",
    autoSubmit: false,
  },
  {
    kind: "llm-prefill",
    name: "summarize",
    description: "Summarize this conversation",
    icon: <BookOpen className="size-3.5" aria-hidden />,
    params: [],
    prompt: () =>
      "Summarize this conversation so far: the research question, the " +
      "strategy I've built, key decisions made, and anything still open.",
    autoSubmit: false,
  },
  {
    kind: "llm-prefill",
    name: "diagnose",
    description: "Diagnose why my strategy returns 0 results",
    icon: <Ban className="size-3.5" aria-hidden />,
    params: [],
    prompt: () =>
      "Diagnose my current strategy. Walk through each step, call " +
      "get_estimated_size on each, and identify where results collapse. " +
      "Suggest the likely cause and concrete fixes.",
    autoSubmit: false,
  },
  {
    kind: "llm-prefill",
    name: "explain",
    description: "Explain a specific step",
    icon: <Sparkles className="size-3.5" aria-hidden />,
    params: [
      {
        kind: "text",
        name: "stepHint",
        label: "Which step?",
        placeholder: "step id, name, or position",
      },
    ],
    prompt: (values) => {
      const hint = (values["stepHint"] ?? "").trim();
      if (hint === "") {
        return "Explain what my last step does and why it matters biologically.";
      }
      return `Explain what ${hint} does and why it matters biologically.`;
    },
    autoSubmit: false,
  },
];

export function findCommand(name: string): Command | undefined {
  const lower = name.toLowerCase();
  return commands.find((c) => {
    if (c.name.toLowerCase() === lower) return true;
    return c.aliases?.some((a) => a.toLowerCase() === lower) ?? false;
  });
}
