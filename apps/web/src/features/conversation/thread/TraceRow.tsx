"use client";

import { ChevronRight } from "lucide-react";
import { useState, type ReactElement } from "react";

import { ToolInput, ToolOutput } from "@/components/ai-elements/tool";
import { cn } from "@/lib/utils/cn";

import { TRACE_GLYPHS } from "./traceGlyphs";
import type { TraceRowView } from "./traceTypes";

const THINK_TOOL = "think";
const DETAIL_LIMIT = 120;

/** Clip an error to one line, on a word boundary, with an ASCII ellipsis. */
function clip(text: string): string {
  if (text.length <= DETAIL_LIMIT) return text;
  const head = text.slice(0, DETAIL_LIMIT);
  const boundary = head.lastIndexOf(" ");
  const body = boundary > 0 ? head.slice(0, boundary) : head;
  return `${body.trimEnd()}...`;
}

/** The line beside the verb. An empty line is no line, so it draws nothing. */
function detailOf(row: TraceRowView, stoppedLabel: string | undefined): string | null {
  const text = lineOf(row) ?? (row.status === "stopped" ? stoppedLabel : undefined);
  if (text === undefined || text === "") return null;
  return clip(text);
}

function lineOf(row: TraceRowView): string | undefined {
  if (row.status === "error" && row.errorText !== null) return row.errorText;
  return row.summary ?? undefined;
}

export interface TraceRowProps {
  row: TraceRowView;
  showRaw: boolean;
  nameFor: (toolName: string) => string;
  /** What a call reads when its turn ended before it did. */
  stoppedLabel?: string;
}

export function TraceRow({
  row,
  showRaw,
  nameFor,
  stoppedLabel,
}: TraceRowProps): ReactElement {
  const [open, setOpen] = useState(false);
  const glyph = TRACE_GLYPHS[row.status];
  const detail = detailOf(row, stoppedLabel);
  return (
    <div data-testid={row.toolName === THINK_TOOL ? "tool-think" : "tool-call-part"}>
      <div data-testid="trace-row" className="flex h-6 items-center gap-2 text-xs">
        <glyph.Icon
          data-testid="trace-row-status"
          className={cn("size-3 shrink-0", glyph.className)}
          aria-hidden
        />
        <span className="shrink-0 text-foreground/80">{nameFor(row.toolName)}</span>
        {detail !== null && (
          <span
            data-testid="trace-row-summary"
            className="truncate text-muted-foreground"
          >
            {detail}
          </span>
        )}
        {showRaw && (
          <button
            type="button"
            onClick={() => setOpen((held) => !held)}
            aria-expanded={open}
            aria-label="Raw"
            className="ml-auto shrink-0 text-muted-foreground hover:text-foreground"
          >
            <ChevronRight
              className={cn("size-3 transition-transform", open && "rotate-90")}
            />
          </button>
        )}
      </div>
      {showRaw && (
        <div
          data-testid="trace-row-raw"
          className="grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.23,1,0.32,1)]"
          style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
        >
          <div className="overflow-hidden py-1 pl-5">
            <ToolInput input={row.input} className="p-0" />
            <ToolOutput output={row.output} errorText={row.errorText ?? undefined} />
          </div>
        </div>
      )}
    </div>
  );
}
