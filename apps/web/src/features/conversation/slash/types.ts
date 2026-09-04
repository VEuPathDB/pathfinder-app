import type { ReactNode } from "react";

export interface SelectOption {
  value: string;
  label: string;
  description?: string;
}

export type ParamDef =
  | {
      kind: "select";
      name: string;
      label: string;
      options: SelectOption[];
      optionsFn?: undefined;
    }
  | {
      kind: "select";
      name: string;
      label: string;
      options?: undefined;
      optionsFn: (ctx: CommandContext) => Promise<SelectOption[]> | SelectOption[];
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
    }
  | {
      kind: "file";
      name: string;
      label: string;
      accept: string;
    };

export type ParamValues = Record<string, string>;

export interface CommandContext {
  conversationId: string;
  siteId: string;
  /** Step count from the current strategy. Used by deterministic
   * commands to enforce preconditions (e.g. `/clear` requires ≥1 step). */
  stepCount: number;
}

interface DeterministicHandlerResult {
  kind: "toast";
  type: "success" | "error" | "info";
  message: string;
}

interface DeterministicDownloadResult {
  kind: "download";
  url: string;
  filename: string;
}

interface PrefillResult {
  kind: "prefill";
  text: string;
  submit?: boolean;
}

export type CommandResult =
  | DeterministicHandlerResult
  | DeterministicDownloadResult
  | PrefillResult
  | { kind: "noop" };

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
