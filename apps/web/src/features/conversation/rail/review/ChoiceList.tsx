"use client";

import { useAui } from "@assistant-ui/react";

import { Button } from "@/components/ui/button";
import { viewportIsNarrow } from "@/lib/layout/viewport";
import { countOf } from "@/lib/utils/countOf";
import { useRightRailStore } from "@/state/useRightRailStore";

import { focusComposer } from "../../composer/focusComposer";
import type { Choice } from "./reviewModel";
import { ReviewSection } from "./ReviewSection";

const WHO: Record<Choice["source"], string> = {
  chosen: "Assistant's choice.",
  default: "Site default.",
};

export function ChoiceList({ choices }: { choices: readonly Choice[] }) {
  const aui = useAui();
  const closePanel = useRightRailStore((s) => s.closePanel);
  if (choices.length === 0) return null;
  const change = (choice: Choice): void => {
    aui.composer().setText(`Change ${choice.param} (now ${choice.value}) to `);
    if (viewportIsNarrow()) closePanel();
    queueMicrotask(focusComposer);
  };
  return (
    <ReviewSection
      title="Choices made for you"
      meta={`${countOf(choices.length, "value", "values")} you did not state`}
    >
      <ul className="flex flex-col">
        {choices.map((choice) => (
          <li
            key={choice.key}
            className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-2.5 gap-y-0.5 border-t border-dashed border-border py-2 first:border-t-0"
          >
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground">{choice.param}</p>
              <p className="break-words text-sm text-foreground">{choice.value}</p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => change(choice)}
              aria-label={`Change ${choice.param}`}
              className="h-7 px-2 text-xs text-primary transition-transform active:scale-[0.98]"
            >
              Change
            </Button>
            <p className="col-span-2 text-xs text-muted-foreground">
              <span className="font-medium text-warning">{WHO[choice.source]}</span>{" "}
              {choice.sentence}
            </p>
          </li>
        ))}
      </ul>
    </ReviewSection>
  );
}
