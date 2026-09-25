"use client";

import { AnimatePresence, motion } from "motion/react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

import { filterCommands } from "./parser";
import type { Command, CommandContext } from "./types";

export interface SlashPopoverProps {
  open: boolean;
  query: string;
  commands: Command[];
  ctx?: CommandContext;
  activeIdx: number;
  onSelect: (command: Command) => void;
  onHover: (index: number) => void;
}

export function disabledReasonFor(
  command: Command,
  ctx: CommandContext | undefined,
): string | null {
  const resolver = command.disabledReason;
  if (resolver === undefined || ctx === undefined) return null;
  return resolver(ctx);
}

export function SlashPopover({
  open,
  query,
  commands,
  ctx,
  activeIdx,
  onSelect,
  onHover,
}: SlashPopoverProps) {
  const filtered = filterCommands(commands, query);
  const entrance = useEntrance({
    initial: { opacity: 0, y: 6 },
    exit: { opacity: 0, y: 6 },
    transition: { duration: 0.12 },
  });

  return (
    <AnimatePresence>
      {open && filtered.length > 0 && (
        <motion.div
          key="slash-popover"
          {...entrance}
          animate={{ opacity: 1, y: 0 }}
          role="listbox"
          aria-label="Slash commands"
          data-testid="slash-popover"
          className={cn(
            "absolute bottom-full left-0 right-0 z-20 mb-2",
            "max-h-72 overflow-y-auto rounded-lg border border-border bg-popover",
            "shadow-[var(--shadow-float)]",
          )}
        >
          <TooltipProvider delayDuration={150}>
            {filtered.map((cmd, i) => {
              const disabled = disabledReasonFor(cmd, ctx);
              const aliases = cmd.aliases ?? [];
              const row = (
                <button
                  key={cmd.name}
                  type="button"
                  role="option"
                  aria-selected={i === activeIdx}
                  data-testid={`slash-item-${cmd.name}`}
                  data-disabled={disabled !== null ? "true" : undefined}
                  disabled={disabled !== null}
                  onMouseEnter={() => onHover(i)}
                  onClick={() => {
                    if (disabled !== null) return;
                    onSelect(cmd);
                  }}
                  className={cn(
                    "flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors",
                    disabled !== null
                      ? "cursor-not-allowed opacity-50"
                      : i === activeIdx
                        ? "bg-accent text-accent-foreground"
                        : "text-foreground",
                  )}
                >
                  <span className="text-muted-foreground">{cmd.icon}</span>
                  <span className="font-mono text-[12px] font-medium">/{cmd.name}</span>
                  <span className="truncate text-[12px] text-muted-foreground">
                    {cmd.description}
                  </span>
                  {aliases.length > 0 && (
                    <span className="ml-auto shrink-0 font-mono text-[11px] text-muted-foreground">
                      {aliases.map((a) => `/${a}`).join(" ")}
                    </span>
                  )}
                </button>
              );
              if (disabled === null) return row;
              return (
                <Tooltip key={cmd.name}>
                  <TooltipTrigger asChild>
                    <span className="block">{row}</span>
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-xs">
                    {disabled}
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </TooltipProvider>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
