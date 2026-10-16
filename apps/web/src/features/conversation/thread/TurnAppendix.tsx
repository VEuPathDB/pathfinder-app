"use client";

import { useAuiState } from "@assistant-ui/react";
import { ChevronRight } from "lucide-react";
import { useState, useSyncExternalStore, type ReactElement } from "react";
import type {
  ControlTestResults,
  EdaSubsetPreview,
  ResearchSourcesPayload,
  TurnFacts,
} from "@pathfinder/shared";

import { cn } from "@/lib/utils/cn";

import {
  APPENDIX_KINDS,
  FULL_WIDTH,
  LATEST_ONLY,
  SECTION_TITLES,
  appendixComponents,
  isAppendixKind,
  type AppendixKind,
} from "../content/appendixParts";
import { figureNumberFor } from "../content/parts/figureNumbers";
import { tableNumberFor } from "../content/parts/tableNumbers";
import { protocolPart, type StructuralPart } from "../parts";
import { useChatHelpers, type ChatHelpers } from "../runtime/chatHelpersContext";
import { exhibitAnchorId } from "./exhibits";
import { FigureSectionContext } from "./figureSection";

const TWO_COLUMNS_FROM = 3;
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

interface Section {
  kind: AppendixKind;
  data: unknown;
}

function draws(kind: AppendixKind, data: unknown): boolean {
  if (kind !== "data-research.sources") return true;
  return ((data as ResearchSourcesPayload).sources ?? []).length > 0;
}

function sectionsOf(content: readonly StructuralPart[]): Section[] {
  const found = new Map<AppendixKind, unknown[]>();
  for (const part of content) {
    const { type, data } = protocolPart(part);
    if (!isAppendixKind(type) || !draws(type, data)) continue;
    found.set(type, [...(found.get(type) ?? []), data]);
  }
  return APPENDIX_KINDS.flatMap((kind) => {
    const all = found.get(kind) ?? [];
    return (LATEST_ONLY.has(kind) ? all.slice(-1) : all).map((data) => ({
      kind,
      data,
    }));
  });
}

function plural(count: number, noun: string): string {
  return `${count.toLocaleString()} ${count === 1 ? noun : `${noun}s`}`;
}

function summaryOf(sections: readonly Section[]): string {
  const facts = [...sections].reverse().find((section) => section.kind === "data-facts")
    ?.data as TurnFacts | undefined;
  const parts = ["Appendix", plural(sections.length, "section")];
  if (facts?.rootCount != null) {
    parts.push(plural(facts.rootCount, facts.recordNoun ?? "gene"));
  }
  const caveats = (facts?.caveats ?? []).length + (facts?.gaps ?? []).length;
  if (caveats > 0) parts.push(plural(caveats, "caveat"));
  return parts.join(" · ");
}

function anchorsOf(sections: readonly Section[], chat: ChatHelpers): Set<string> {
  const anchors = new Set<string>();
  for (const { kind, data } of sections) {
    if (kind === "data-control-test-results") {
      const number = tableNumberFor(chat.messages, data as ControlTestResults);
      if (number !== null) anchors.add(exhibitAnchorId("table", number));
    }
    if (kind === "data-eda.subset-preview") {
      const number = figureNumberFor(chat.messages, data as EdaSubsetPreview);
      if (number !== null) anchors.add(exhibitAnchorId("figure", number));
    }
  }
  return anchors;
}

function subscribeToHash(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function currentHash(): string {
  return window.location.hash.replace(/^#/, "");
}

function noHash(): string {
  return "";
}

export function TurnAppendix(): ReactElement | null {
  const content = useAuiState((s) => s.message.content);
  const chat = useChatHelpers();
  const hash = useSyncExternalStore(subscribeToHash, currentHash, noHash);
  const [chosen, setChosen] = useState<boolean | null>(null);
  const [furled, setFurled] = useState(true);
  const sections = sectionsOf(content);
  if (sections.length === 0) return null;
  const open = chosen ?? anchorsOf(sections, chat).has(hash);
  const columns = sections.length >= TWO_COLUMNS_FROM ? 2 : 1;
  const toggle = () => {
    if (!open) setFurled(false);
    setChosen(!open);
  };
  return (
    <section data-testid="turn-appendix" aria-label="Appendix" className="mt-2">
      <button
        type="button"
        data-testid="turn-appendix-toggle"
        aria-expanded={open}
        onClick={toggle}
        className="flex h-7 w-full items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <ChevronRight
          className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
          aria-hidden
        />
        <span data-testid="turn-appendix-summary">{summaryOf(sections)}</span>
      </button>
      <div
        className="grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.23,1,0.32,1)]"
        style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
        onTransitionEnd={() => {
          if (!open) setFurled(true);
        }}
      >
        <div
          className="overflow-hidden"
          style={{ visibility: furled && !open ? "hidden" : "visible" }}
        >
          <div
            data-testid="turn-appendix-body"
            data-columns={String(columns)}
            className={cn(
              "turn-appendix-body pt-3 pb-1",
              columns === 2 && "md:columns-2 md:gap-8",
            )}
          >
            {sections.map((section, index) => {
              const Component = appendixComponents[section.kind] as (props: {
                data: unknown;
              }) => ReactElement | null;
              return (
                <div
                  key={`${section.kind}-${String(index)}`}
                  data-testid="appendix-section"
                  className={cn(
                    "mb-6 last:mb-0",
                    FULL_WIDTH.has(section.kind) && "[column-span:all]",
                  )}
                >
                  <FigureSectionContext
                    value={{
                      letter: LETTERS[index] ?? String(index + 1),
                      title: SECTION_TITLES[section.kind],
                    }}
                  >
                    <Component data={section.data} />
                  </FigureSectionContext>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
