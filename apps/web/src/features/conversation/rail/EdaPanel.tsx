"use client";

import { useRouter } from "next/navigation";
import { FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
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
    <RailPanelShell
      title="Studies"
      headerActions={
        analysis !== null ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={openTab}
            data-testid="rail-eda-open"
            className="h-7 gap-1 px-2 text-xs"
          >
            Open
          </Button>
        ) : null
      }
    >
      <div data-testid="rail-eda-panel" className="h-full">
        {analysis !== null ? (
          <div className="space-y-1 px-3 py-2 text-xs">
            <p className="font-medium text-foreground">
              {analysis.studyDisplayName.length > 0
                ? analysis.studyDisplayName
                : analysis.datasetId}
            </p>
            <p className="text-muted-foreground">{analysis.displayName}</p>
            <p className="text-[11px] text-muted-foreground">
              {`${analysis.numFilters.toLocaleString()} ${analysis.numFilters === 1 ? "filter" : "filters"} - ${analysis.numComputations.toLocaleString()} ${analysis.numComputations === 1 ? "computation" : "computations"}`}
            </p>
          </div>
        ) : (
          <RailEmptyState
            icon={<FlaskConical className="h-8 w-8" aria-hidden />}
            heading="No study is open"
            description="Ask the assistant to explore a study, and the subset and its plots appear here."
          />
        )}
      </div>
    </RailPanelShell>
  );
}
