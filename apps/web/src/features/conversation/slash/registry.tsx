"use client";

import {
  Ban,
  BookOpen,
  HelpCircle,
  LineChart,
  Plus,
  Sparkles,
  Trash,
} from "lucide-react";

import { chatRoot } from "@/lib/routes";

import { exportCommand, importCommand, renameCommand } from "./commandsIO";
import type { Command, CommandContext } from "./types";

const NO_STRATEGY = "This conversation has no strategy yet.";

function needsStrategy(ctx: CommandContext): string | null {
  return ctx.stepCount === 0 ? NO_STRATEGY : null;
}

export const commands: Command[] = [
  {
    kind: "deterministic",
    name: "new",
    description: "Start a new conversation",
    icon: <Plus className="size-3.5" aria-hidden />,
    params: [],
    run: (_values, ctx) => ({ kind: "navigate", href: chatRoot(ctx.siteId) }),
  },
  renameCommand,
  exportCommand,
  importCommand,
  {
    kind: "deterministic",
    name: "help",
    aliases: ["?"],
    description: "List the slash commands",
    icon: <HelpCircle className="size-3.5" aria-hidden />,
    params: [],
    run: () => ({ kind: "prefill", text: "/" }),
  },
  {
    kind: "llm-prefill",
    name: "clear",
    description: "Clear the current strategy",
    icon: <Trash className="size-3.5 text-destructive" aria-hidden />,
    params: [],
    disabledReason: needsStrategy,
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
    disabledReason: needsStrategy,
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
    disabledReason: needsStrategy,
    prompt: () =>
      "Diagnose my current strategy. Call get_live_strategy_state, walk through " +
      "each step's count, and identify where results collapse. Suggest the " +
      "likely cause and concrete fixes.",
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
    disabledReason: needsStrategy,
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
