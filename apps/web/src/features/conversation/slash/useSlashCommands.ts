"use client";

import { useAui, useAuiState } from "@assistant-ui/react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import type { KeyboardEvent } from "react";
import { useState } from "react";
import { toast } from "sonner";

import { toUserMessage } from "@/lib/api/errors";
import { handleWdkAuthRefusal } from "@/state/useAuthGateStore";

import { filterCommands, parseSlashInput, unknownCommandToken } from "./parser";
import { commands } from "./registry";
import { disabledReasonFor } from "./SlashPopover";
import type { Command, CommandContext, CommandResult, ParamValues } from "./types";

interface UseSlashCommandsArgs {
  conversationId: string;
  siteId: string;
  stepCount: number;
  conversationExists: boolean;
}

function triggerDownload(url: string, filename: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** The composer's slash menu: what it lists, which row is active, and what a
 *  pick does. The composer input is the only place its keys are read. */
export function useSlashCommands(args: UseSlashCommandsArgs) {
  const aui = useAui();
  const router = useRouter();
  const queryClient = useQueryClient();
  const text = useAuiState((s) => s.composer.text);
  const [pendingCommand, setPendingCommand] = useState<Command | null>(null);
  const [activeIdx, setActiveIdx] = useState(0);
  const [filterKey, setFilterKey] = useState("");

  const ctx: CommandContext = { ...args, queryClient };
  const parsed = parseSlashInput(text);
  const query = parsed?.token ?? "";
  const menuOpen = pendingCommand === null && parsed !== null && parsed.rest === "";
  const filtered = menuOpen ? filterCommands(commands, query) : [];

  const unknownToken = unknownCommandToken(text, commands);
  const [refusedText, setRefusedText] = useState<string | null>(null);
  const refusal =
    unknownToken !== null && refusedText === text
      ? `No command /${unknownToken}. Type / to see the list.`
      : null;

  const nextFilterKey = `${query}|${filtered.length}`;
  if (filterKey !== nextFilterKey) {
    setFilterKey(nextFilterKey);
    setActiveIdx(0);
  }

  function apply(result: CommandResult): void {
    switch (result.kind) {
      case "toast":
        if (result.type === "success") toast.success(result.message);
        else if (result.type === "error") toast.error(result.message);
        else toast.info(result.message);
        return;
      case "download":
        triggerDownload(result.url, result.filename);
        toast.success(`Downloading ${result.filename}`);
        return;
      case "prefill":
        aui.composer().setText(result.text);
        return;
      case "navigate":
        router.push(result.href);
        return;
    }
  }

  async function run(command: Command, values: ParamValues): Promise<void> {
    setPendingCommand(null);
    if (command.kind === "llm-prefill") {
      aui.composer().setText(command.prompt(values, ctx));
      if (command.autoSubmit === true) aui.composer().send();
      return;
    }
    aui.composer().setText("");
    try {
      apply(await command.run(values, ctx));
    } catch (err) {
      const retry = (): void => void run(command, values);
      if (!handleWdkAuthRefusal(err, retry)) {
        toast.error(toUserMessage(err, `/${command.name} failed.`));
      }
    }
  }

  function select(command: Command): void {
    if (disabledReasonFor(command, ctx) !== null) return;
    if (command.params.length === 0) {
      void run(command, {});
      return;
    }
    setPendingCommand(command);
  }

  function cancel(): void {
    setPendingCommand(null);
    aui.composer().setText("");
  }

  /** Holds back a send of a command no command answers; true when it did. */
  function refuseUnknown(): boolean {
    if (unknownToken === null) return false;
    setRefusedText(text);
    return true;
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && !event.shiftKey && refuseUnknown()) {
      event.preventDefault();
      return;
    }
    if (filtered.length === 0) return;
    const count = filtered.length;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIdx((i) => (i + 1) % count);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIdx((i) => (i - 1 + count) % count);
    } else if ((event.key === "Enter" && !event.shiftKey) || event.key === "Tab") {
      event.preventDefault();
      const command = filtered[activeIdx];
      if (command !== undefined) select(command);
    } else if (event.key === "Escape") {
      event.preventDefault();
      aui.composer().setText("");
    }
  }

  return {
    ctx,
    menuOpen,
    query,
    activeIdx,
    setActiveIdx,
    pendingCommand,
    select,
    run,
    cancel,
    onKeyDown,
    refusal,
    refuseUnknown,
  };
}
