"use client";

import { FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { countOf } from "@/lib/utils/countOf";

import { RailEmptyState, RailPanelShell } from "./RailPanelShell";
import type { RailSource } from "./railSource";

export function EdaPanel({ source }: { source: RailSource }) {
  const analysis = source.study;
  const owner = source.owner;

  return (
    <RailPanelShell title="Study">
      <div data-testid="rail-eda-panel" className="h-full">
        {analysis !== null ? (
          <div className="flex flex-col gap-3 px-4 py-4">
            <div className="flex flex-col gap-0.5">
              <h3 className="text-sm font-semibold text-foreground">
                {analysis.studyDisplayName.length > 0
                  ? analysis.studyDisplayName
                  : analysis.datasetId}
              </h3>
              <p className="text-sm text-muted-foreground">{analysis.displayName}</p>
            </div>
            <p className="text-xs tabular-nums text-muted-foreground">
              {`${countOf(analysis.numFilters, "filter", "filters")} · ${countOf(analysis.numComputations, "computation", "computations")}`}
            </p>
            {owner !== null && (
              <Button
                variant="outline"
                size="sm"
                onClick={owner.openStudy}
                data-testid="rail-eda-open"
                className="h-7 self-start px-2.5 text-xs transition-transform active:scale-[0.98]"
              >
                Open study
              </Button>
            )}
          </div>
        ) : (
          <RailEmptyState
            icon={<FlaskConical className="size-8" aria-hidden />}
            heading="No study is open"
            description="Ask the assistant to explore a study, and the subset and its plots appear here."
          />
        )}
      </div>
    </RailPanelShell>
  );
}
