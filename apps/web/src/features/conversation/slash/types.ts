import type { QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

export interface SelectOption {
  value: string;
  label: string;
}

export type ParamDef =
  | {
      kind: "select";
      name: string;
      label: string;
      options: SelectOption[];
    }
  | {
      kind: "text";
      name: string;
      label: string;
      placeholder?: string;
    }
  | {
      kind: "textarea";
      name: string;
      label: string;
      placeholder?: string;
      rows?: number;
    };

export type ParamValues = Record<string, string>;

export interface CommandContext {
  conversationId: string;
  siteId: string;
  stepCount: number;
  /** False on a draft chat, which has no row to read or change. */
  conversationExists: boolean;
  queryClient: QueryClient;
}

interface ToastResult {
  kind: "toast";
  type: "success" | "error" | "info";
  message: string;
}

interface DownloadResult {
  kind: "download";
  url: string;
  filename: string;
}

interface PrefillResult {
  kind: "prefill";
  text: string;
}

interface NavigateResult {
  kind: "navigate";
  href: string;
}

export type CommandResult =
  ToastResult | DownloadResult | PrefillResult | NavigateResult;

type DisabledReasonResolver = (ctx: CommandContext) => string | null;

interface DeterministicCommand {
  kind: "deterministic";
  name: string;
  aliases?: string[];
  description: string;
  icon?: ReactNode;
  params: ParamDef[];
  disabledReason?: DisabledReasonResolver;
  run: (
    values: ParamValues,
    ctx: CommandContext,
  ) => Promise<CommandResult> | CommandResult;
}

interface LlmPrefillCommand {
  kind: "llm-prefill";
  name: string;
  aliases?: string[];
  description: string;
  icon?: ReactNode;
  params: ParamDef[];
  disabledReason?: DisabledReasonResolver;
  prompt: (values: ParamValues, ctx: CommandContext) => string;
  autoSubmit?: boolean;
}

export type Command = DeterministicCommand | LlmPrefillCommand;
