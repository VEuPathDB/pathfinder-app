"use client";

import { useRouter } from "next/navigation";
import { FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { countOf } from "@/lib/utils/countOf";
import { edaTabUrl } from "@/lib/routes";
import { useEdaStore } from "@/state/eda";

import { RailEmptyState, RailPanelShell } from "./RailPanelShell";

interface EdaPanelProps {
  conversationId: string;
}

export function EdaPanel({ conversationId }: EdaPanelProps) {
  const router = useRouter();
  const analysis = useEdaStore((s) => s.analysis);

  const openTab = (): void => {
    router.push(edaTabUrl(conversationId));
  };

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
            <Button
              variant="outline"
              size="sm"
              onClick={openTab}
              data-testid="rail-eda-open"
              className="h-7 self-start px-2.5 text-xs transition-transform active:scale-[0.98]"
            >
              Open study
            </Button>
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
